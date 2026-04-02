import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cacao_engine.engine import run_engine
from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.db.database import get_db
from app.db.models import Diagnostic, Plantation, User
from app.auth.auth_service import get_current_user
from app.ml.image_diagnosis import analyze_leaf_image
from app.satellite.ndvi_service import get_ndvi
from app.recommendations import build_recommendations

router = APIRouter()


class PlantationCreate(BaseModel):
    name: str
    owner_name: str
    country: str
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hectares: Optional[float] = None


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
def health_check():
    return {"status": "ok"}


# ─── Plantations ─────────────────────────────────────────────────────────────

@router.post("/plantations")
def create_plantation(
    plantation: PlantationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if not current_user.cooperative_id:
        raise HTTPException(
            status_code=400,
            detail="Votre compte n'est associé à aucune coopérative.",
        )

    new_plantation = Plantation(
        name=plantation.name,
        owner_name=plantation.owner_name,
        country=plantation.country,
        region=plantation.region,
        latitude=plantation.latitude,
        longitude=plantation.longitude,
        hectares=plantation.hectares,
        cooperative_id=current_user.cooperative_id,  # toujours rattachée
    )
    db.add(new_plantation)
    db.commit()
    db.refresh(new_plantation)
    return new_plantation


@router.get("/plantations")
def get_plantations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/plantations/{plantation_id}")
def get_plantation(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    diagnostics = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .all()
    )
    return {"plantation": plantation, "diagnostics": diagnostics}



@router.delete("/plantations/{plantation_id}")
def delete_plantation(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime une plantation et ses diagnostics associés. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Supprimer les diagnostics associés d'abord
    db.query(Diagnostic).filter(Diagnostic.plantation_id == plantation_id).delete()
    db.delete(plantation)
    db.commit()

    return {"message": f"Plantation '{plantation.name}' supprimée avec succès."}

# ─── Diagnostic agronomique ───────────────────────────────────────────────────

@router.post("/cacao/diagnostic", response_model=None)
def diagnostic_endpoint(
    plantation_id: int,
    inputs: CacaoInputs,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    report: EngineReport = run_engine(inputs)

    new_diagnostic = Diagnostic(
        plantation_id=plantation_id,
        country=inputs.country,
        region=inputs.region,
        humidity_pct=inputs.humidity_pct,
        rainfall_mm_month=inputs.rainfall_mm_month,
        avg_temp_c=inputs.avg_temp_c,
        plantation_age_years=inputs.plantation_age_years,
        shade_tree_density_pct=inputs.shade_tree_density_pct,
        global_score=report.global_score,
        global_risk_level=report.global_risk_level,
    )
    db.add(new_diagnostic)
    db.commit()
    db.refresh(new_diagnostic)
    # Générer les recommandations actionnables
    rec_list = build_recommendations(
        module_results=[
            {"module_name": m.module_name, "score": m.score, "reasons": m.reasons}
            for m in report.module_results
        ],
        inputs={
            "humidity_pct":           inputs.humidity_pct,
            "rainfall_mm_month":      inputs.rainfall_mm_month,
            "avg_temp_c":             inputs.avg_temp_c,
            "shade_tree_density_pct": inputs.shade_tree_density_pct,
            "plantation_age_years":   inputs.plantation_age_years,
        },
        global_score=report.global_score,
        global_risk=report.global_risk_level,
    )

    return {
        "global_score":      report.global_score,
        "global_risk_level": report.global_risk_level,
        "module_results":    [
            {"module_name": m.module_name, "score": m.score,
             "risk_level": m.risk_level, "reasons": m.reasons}
            for m in report.module_results
        ],
        "recommendations":   rec_list,
        "diagnostic_id":     new_diagnostic.id,
    }



@router.get("/diagnostics/{diagnostic_id}/recommendations")
def get_diagnostic_recommendations(
    diagnostic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne les recommandations actionnables pour un diagnostic existant."""
    diag = db.query(Diagnostic).filter(
        Diagnostic.id == diagnostic_id,
    ).first()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable.")

    # Recalculer les recs depuis les données stockées
    rec_list = build_recommendations(
        module_results=[],  # pas de module_results en DB, on utilise les inputs
        inputs={
            "humidity_pct":           diag.humidity_pct,
            "rainfall_mm_month":      diag.rainfall_mm_month,
            "avg_temp_c":             diag.avg_temp_c,
            "shade_tree_density_pct": None,
            "plantation_age_years":   None,
        },
        global_score=diag.global_score,
        global_risk=diag.global_risk_level,
    )
    return rec_list

# ─── Historique diagnostics ───────────────────────────────────────────────────

@router.get("/diagnostics")
def get_diagnostics(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Diagnostic)
        .join(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/diagnostics/{diagnostic_id}")
def get_diagnostic(
    diagnostic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    diag = (
        db.query(Diagnostic)
        .join(Plantation)
        .filter(
            Diagnostic.id == diagnostic_id,
            Plantation.cooperative_id == current_user.cooperative_id,
        )
        .first()
    )
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable.")
    return diag


@router.get("/plantations/{plantation_id}/history")
def get_plantation_history(
    plantation_id: int,
    limit: Optional[int] = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    query = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .order_by(Diagnostic.created_at.desc())
    )
    if limit:
        query = query.limit(limit)

    return [
        {
            "date": d.created_at.strftime("%Y-%m-%d") if d.created_at else None,
            "score": d.global_score,
            "risk_level": d.global_risk_level,
        }
        for d in query.all()
    ]


# ─── Carte ────────────────────────────────────────────────────────────────────

def _latest_diag_by_plantation(plantation_ids: list, db: Session) -> dict:
    """
    Retourne le dernier diagnostic de chaque plantation en UNE SEULE requête.
    Évite le problème N+1 (1 requête par plantation en boucle).
    """
    if not plantation_ids:
        return {}
    # Sous-requête : date max du dernier diagnostic par plantation
    subq = (
        db.query(
            Diagnostic.plantation_id,
            func.max(Diagnostic.created_at).label("max_at"),
        )
        .filter(Diagnostic.plantation_id.in_(plantation_ids))
        .group_by(Diagnostic.plantation_id)
        .subquery()
    )
    # Jointure pour récupérer les lignes complètes
    latest_diags = (
        db.query(Diagnostic)
        .join(
            subq,
            (Diagnostic.plantation_id == subq.c.plantation_id)
            & (Diagnostic.created_at == subq.c.max_at),
        )
        .all()
    )
    return {d.plantation_id: d for d in latest_diags}


@router.get("/map/plantations")
def get_map_plantations(
    risk_level: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantations = (
        db.query(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .all()
    )
    latest_map = _latest_diag_by_plantation([p.id for p in plantations], db)
    results = []
    for p in plantations:
        latest = latest_map.get(p.id)
        if not latest:
            continue
        if risk_level and latest.global_risk_level != risk_level:
            continue
        results.append({
            "id": p.id,
            "name": p.name,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "risk_level": latest.global_risk_level,
            "score": latest.global_score,
        })
    return results


@router.get("/map/stats")
def get_map_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantations = (
        db.query(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .all()
    )
    latest_map = _latest_diag_by_plantation([p.id for p in plantations], db)
    high = medium = low = 0
    for p in plantations:
        latest = latest_map.get(p.id)
        if latest:
            if latest.global_risk_level == "HIGH":
                high += 1
            elif latest.global_risk_level == "MEDIUM":
                medium += 1
            elif latest.global_risk_level == "LOW":
                low += 1

    return {
        "total_plantations": len(plantations),
        "high_risk_plantations": high,
        "medium_risk_plantations": medium,
        "low_risk_plantations": low,
    }


# ─── Image / ML ──────────────────────────────────────────────────────────────

@router.post("/diagnostic/image")
async def diagnostic_image(
    file: UploadFile = File(...),
    plantation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "technician"}:
        raise HTTPException(status_code=403, detail="Rôle technicien requis.")

    # Vérifier la plantation avant de traiter l'image
    if plantation_id is not None:
        plantation = db.query(Plantation).filter(
            Plantation.id == plantation_id,
            Plantation.cooperative_id == current_user.cooperative_id,
        ).first()
        if not plantation:
            raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Lecture en mémoire — pas d'écriture disque (filesystem éphémère sur Railway)
    contents = await file.read()

    # Exécution du module ML (stub pour l'instant)
    # NOTE : le stub ignore le contenu — on lui passe le nom de fichier pour
    # compatibilité avec la signature existante de analyze_leaf_image.
    import tempfile
    with tempfile.NamedTemporaryFile(delete=True, suffix=".jpg") as tmp:
        tmp.write(contents)
        tmp.flush()
        diagnosis_result = analyze_leaf_image(tmp.name)

    # On ne persiste PAS les diagnostics image en DB :
    # ils n'ont pas de données climatiques réelles (humidity, rainfall, temp)
    # et corrupraient les statistiques agronomiques du dashboard.
    # Quand le vrai modèle ML sera intégré, un type de diagnostic dédié sera créé.

    return diagnosis_result


# ─── Satellite NDVI ───────────────────────────────────────────────────────────

@router.get("/satellite/ndvi")
def get_ndvi_endpoint(
    latitude: float,
    longitude: float,
    current_user: User = Depends(get_current_user),
):
    return get_ndvi(latitude, longitude)


@router.get("/plantations/{plantation_id}/satellite")
def get_plantation_satellite_analysis(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    if plantation.latitude is None or plantation.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Coordonnées GPS manquantes pour cette plantation.",
        )

    ndvi_result = get_ndvi(plantation.latitude, plantation.longitude)
    return {
        "plantation_id": plantation.id,
        "ndvi": ndvi_result["ndvi"],
        "vegetation_status": ndvi_result["vegetation_status"],
    }


# ─── Admin — Gestion des membres ─────────────────────────────────────────────

class UpdateRoleRequest(BaseModel):
    role: str  # "admin" | "agronomist" | "technician"

VALID_ROLES = {"admin", "agronomist", "technician"}


@router.get("/admin/members")
def get_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste tous les membres de la coopérative. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    members = (
        db.query(User)
        .filter(User.cooperative_id == current_user.cooperative_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "email": m.email,
            "role": m.role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "is_current_user": m.id == current_user.id,
        }
        for m in members
    ]


@router.put("/admin/members/{user_id}/role")
def update_member_role(
    user_id: int,
    req: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change le rôle d'un membre. Admin uniquement. Un admin ne peut pas dégrader son propre rôle."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rôle invalide : {req.role}.")

    # Empêcher l'admin de se dégrader lui-même (évite de perdre le dernier admin)
    if user_id == current_user.id and req.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas modifier votre propre rôle.",
        )

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    member.role = req.role
    db.commit()
    db.refresh(member)
    return {"id": member.id, "email": member.email, "role": member.role}


@router.delete("/admin/members/{user_id}")
def remove_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime un membre de la coopérative. Admin uniquement. Ne peut pas se supprimer soi-même."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas supprimer votre propre compte.",
        )

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    db.delete(member)
    db.commit()
    return {"message": f"Membre {member.email} supprimé avec succès."}
