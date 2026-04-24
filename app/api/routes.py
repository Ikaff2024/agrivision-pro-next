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
from app.db.models import Diagnostic, Plantation, User, Harvest
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
    plant_count: Optional[int] = None


# â”€â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/health")
def health_check():
    return {"status": "ok"}


# â”€â”€â”€ Plantations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            detail="Votre compte n'est associÃ© Ã  aucune coopÃ©rative.",
        )

    new_plantation = Plantation(
        name=plantation.name,
        owner_name=plantation.owner_name,
        country=plantation.country,
        region=plantation.region,
        latitude=plantation.latitude,
        longitude=plantation.longitude,
        hectares=plantation.hectares,
        plant_count=plantation.plant_count,
        cooperative_id=current_user.cooperative_id,  # toujours rattachÃ©e
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
    """Supprime une plantation et ses diagnostics associÃ©s. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Supprimer les diagnostics associÃ©s d'abord
    db.query(Diagnostic).filter(Diagnostic.plantation_id == plantation_id).delete()
    db.delete(plantation)
    db.commit()

    return {"message": f"Plantation '{plantation.name}' supprimÃ©e avec succÃ¨s."}

# â”€â”€â”€ Diagnostic agronomique â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/cacao/diagnostic", response_model=None)
def diagnostic_endpoint(
    plantation_id: int,
    inputs: CacaoInputs,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="RÃ´le agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # â”€â”€ Couche 2 Agroforesterie : substituer l'ombrage si inventaire disponible â”€â”€
    agro_records = db.query(AgroforestryRecord).filter(
        AgroforestryRecord.plantation_id == plantation_id
    ).all()
    if agro_records:
        SHADE_FACTORS = {
            "Gliricidia sepium": 0.8,  "Leucaena leucocephala": 0.7,
            "Erythrina spp.": 0.9,     "Albizzia adianthifolia": 1.0,
            "Musa spp.": 0.4,          "Persea americana": 0.8,
            "Mangifera indica": 1.0,   "Citrus sinensis": 0.6,
            "Dacryodes edulis": 0.75,  "Cola nitida": 0.7,
            "Carica papaya": 0.3,      "Milicia excelsa": 1.0,
            "Terminalia superba": 1.0, "Ceiba pentandra": 1.0,
            "Khaya senegalensis": 1.0, "Elaeis guineensis": 0.85,
            "Cocos nucifera": 0.8,     "Tectona grandis": 0.9,
        }
        shade_sum = sum(
            (r.count_per_hectare or 0) * SHADE_FACTORS.get(r.species_name, 0.6)
            for r in agro_records
        )
        computed_shade = min(100.0, round(shade_sum / 40 * 100, 1))
        inputs = CacaoInputs(
            country=inputs.country,
            region=inputs.region,
            humidity_pct=inputs.humidity_pct,
            rainfall_mm_month=inputs.rainfall_mm_month,
            avg_temp_c=inputs.avg_temp_c,
            plantation_age_years=inputs.plantation_age_years,
            shade_tree_density_pct=computed_shade,
        )

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
    # GÃ©nÃ©rer les recommandations actionnables
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

    # Recalculer les recs depuis les donnÃ©es stockÃ©es
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

# â”€â”€â”€ Historique diagnostics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€â”€ Carte â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _latest_diag_by_plantation(plantation_ids: list, db: Session) -> dict:
    """
    Retourne le dernier diagnostic de chaque plantation en UNE SEULE requÃªte.
    Ã‰vite le problÃ¨me N+1 (1 requÃªte par plantation en boucle).
    """
    if not plantation_ids:
        return {}
    # Sous-requÃªte : date max du dernier diagnostic par plantation
    subq = (
        db.query(
            Diagnostic.plantation_id,
            func.max(Diagnostic.created_at).label("max_at"),
        )
        .filter(Diagnostic.plantation_id.in_(plantation_ids))
        .group_by(Diagnostic.plantation_id)
        .subquery()
    )
    # Jointure pour rÃ©cupÃ©rer les lignes complÃ¨tes
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


# â”€â”€â”€ Image / ML â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/diagnostic/image")
async def diagnostic_image(
    file: UploadFile = File(...),
    plantation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "technician"}:
        raise HTTPException(status_code=403, detail="RÃ´le technicien requis.")

    # VÃ©rifier la plantation avant de traiter l'image
    if plantation_id is not None:
        plantation = db.query(Plantation).filter(
            Plantation.id == plantation_id,
            Plantation.cooperative_id == current_user.cooperative_id,
        ).first()
        if not plantation:
            raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Lecture en mÃ©moire â€” pas d'Ã©criture disque (filesystem Ã©phÃ©mÃ¨re sur Railway)
    contents = await file.read()

    # ExÃ©cution du module ML (stub pour l'instant)
    # NOTE : le stub ignore le contenu â€” on lui passe le nom de fichier pour
    # compatibilitÃ© avec la signature existante de analyze_leaf_image.
    import tempfile
    with tempfile.NamedTemporaryFile(delete=True, suffix=".jpg") as tmp:
        tmp.write(contents)
        tmp.flush()
        diagnosis_result = analyze_leaf_image(tmp.name)

    # On ne persiste PAS les diagnostics image en DB :
    # ils n'ont pas de donnÃ©es climatiques rÃ©elles (humidity, rainfall, temp)
    # et corrupraient les statistiques agronomiques du dashboard.
    # Quand le vrai modÃ¨le ML sera intÃ©grÃ©, un type de diagnostic dÃ©diÃ© sera crÃ©Ã©.

    return diagnosis_result


# â”€â”€â”€ Satellite NDVI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            detail="CoordonnÃ©es GPS manquantes pour cette plantation.",
        )

    ndvi_result = get_ndvi(plantation.latitude, plantation.longitude)
    return {
        "plantation_id": plantation.id,
        "ndvi": ndvi_result["ndvi"],
        "vegetation_status": ndvi_result["vegetation_status"],
    }


# â”€â”€â”€ Admin â€” Gestion des membres â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class UpdateRoleRequest(BaseModel):
    role: str  # "admin" | "agronomist" | "technician"

VALID_ROLES = {"admin", "agronomist", "technician"}


@router.get("/admin/members")
def get_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste tous les membres de la coopÃ©rative. Admin uniquement."""
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
            "is_active": m.is_active,
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
    """Change le rÃ´le d'un membre. Admin uniquement. Un admin ne peut pas dÃ©grader son propre rÃ´le."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"RÃ´le invalide : {req.role}.")

    # EmpÃªcher l'admin de se dÃ©grader lui-mÃªme (Ã©vite de perdre le dernier admin)
    if user_id == current_user.id and req.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas modifier votre propre rÃ´le.",
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
    """Supprime un membre de la coopÃ©rative. Admin uniquement. Ne peut pas se supprimer soi-mÃªme."""
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
    return {"message": f"Membre {member.email} supprimÃ© avec succÃ¨s."}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ Agroforesterie â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

from app.db.models import AgroforestryRecord, Cooperative, PlantationBoundary
from app.ai_advisor import get_ai_advice

# â”€â”€ BibliothÃ¨que d'espÃ¨ces â€” coefficients agronomiques & carbone â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# carbon_factor : tCOâ‚‚ stockÃ©e par arbre par an (allomÃ©trie simplifiÃ©e FAO/IPCC)
# shade_factor  : contribution Ã  l'ombrage par arbre (arbres/ha â†’ % ombrage)
SPECIES_LIBRARY = [
    # LÃ©gumineuses fixatrices d'azote (ombrage rapide)
    {"name":"Gliricidia sepium",    "local":"Gliricidi",    "layer":"intermediate", "carbon_factor":0.012, "shade_factor":0.8,  "category":"LÃ©gumineuse"},
    {"name":"Leucaena leucocephala","local":"LeucÃ©na",      "layer":"intermediate", "carbon_factor":0.010, "shade_factor":0.7,  "category":"LÃ©gumineuse"},
    {"name":"Erythrina spp.",       "local":"Ã‰rythrine",    "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.9,  "category":"LÃ©gumineuse"},
    {"name":"Albizzia adianthifolia","local":"Albizzia",    "layer":"superior",     "carbon_factor":0.025, "shade_factor":1.0,  "category":"LÃ©gumineuse"},
    # Fruitiers
    {"name":"Musa spp.",            "local":"Bananier",     "layer":"understory",   "carbon_factor":0.004, "shade_factor":0.4,  "category":"Fruitier"},
    {"name":"Persea americana",     "local":"Avocatier",    "layer":"intermediate", "carbon_factor":0.015, "shade_factor":0.8,  "category":"Fruitier"},
    {"name":"Mangifera indica",     "local":"Manguier",     "layer":"superior",     "carbon_factor":0.022, "shade_factor":1.0,  "category":"Fruitier"},
    {"name":"Citrus sinensis",      "local":"Oranger",      "layer":"intermediate", "carbon_factor":0.010, "shade_factor":0.6,  "category":"Fruitier"},
    {"name":"Dacryodes edulis",     "local":"Safoutier",    "layer":"intermediate", "carbon_factor":0.014, "shade_factor":0.75, "category":"Fruitier"},
    {"name":"Cola nitida",          "local":"Colatier",     "layer":"intermediate", "carbon_factor":0.012, "shade_factor":0.7,  "category":"Fruitier"},
    {"name":"Carica papaya",        "local":"Papayer",      "layer":"understory",   "carbon_factor":0.003, "shade_factor":0.3,  "category":"Fruitier"},
    # Timber / bois d'oeuvre
    {"name":"Milicia excelsa",      "local":"Iroko",        "layer":"superior",     "carbon_factor":0.045, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Terminalia superba",   "local":"FrakÃ©",        "layer":"superior",     "carbon_factor":0.038, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Ceiba pentandra",      "local":"Fromager",     "layer":"superior",     "carbon_factor":0.042, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Khaya senegalensis",   "local":"Khaya",        "layer":"superior",     "carbon_factor":0.040, "shade_factor":1.0,  "category":"Timber"},
    # Palmiers / divers
    {"name":"Elaeis guineensis",    "local":"Palmier Ã  huile","layer":"superior",   "carbon_factor":0.020, "shade_factor":0.85, "category":"Divers"},
    {"name":"Cocos nucifera",       "local":"Cocotier",     "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.8,  "category":"Divers"},
    {"name":"Tectona grandis",      "local":"Teck",         "layer":"superior",     "carbon_factor":0.035, "shade_factor":0.9,  "category":"Timber"},
]

def _compute_metrics(records) -> dict:
    """
    Calcule les mÃ©triques agroforestiÃ¨res Ã  partir des enregistrements.
    - shade_score      : % d'ombrage estimÃ© (0-100)
    - diversity_score  : score de diversitÃ© floristique (0-100)
    - carbon_stock_tco2_ha : stock carbone estimÃ© (tCOâ‚‚/ha)
    - conformity_score : score global de conformitÃ© agroforestiÃ¨re (0-100)
    """
    if not records:
        return {
            "shade_score": 0, "diversity_score": 0,
            "carbon_stock_tco2_ha": 0.0, "conformity_score": 0,
            "total_trees_per_ha": 0, "species_count": 0
        }

    species_lib = {s["name"]: s for s in SPECIES_LIBRARY}

    total_trees = 0.0
    shade_sum = 0.0
    carbon_sum = 0.0
    species_seen = set()

    for r in records:
        density = r.count_per_hectare or 0
        age = 5  # dÃ©faut fixe (avg_age_years non en base)
        total_trees += density
        species_seen.add(r.species_name)

        lib = species_lib.get(r.species_name)
        cf = lib["carbon_factor"] if lib else 0.010   # dÃ©faut gÃ©nÃ©rique
        sf = lib["shade_factor"]  if lib else 0.6

        # Facteur Ã¢ge : croÃ®t jusqu'Ã  2.0 Ã  30 ans (log)
        import math
        age_factor = min(2.0, 0.4 + (math.log1p(age) / math.log1p(30)) * 1.6)

        shade_sum  += density * sf
        carbon_sum += density * cf * age_factor

    # Ombrage : 40 arbres/ha de plein couvert = 100% ombrage (rÃ¨gle empirique cacao)
    shade_score = min(100, round(shade_sum / 40 * 100))

    # DiversitÃ© : 1 espÃ¨ce = 10pts, chaque espÃ¨ce suppl. +12pts, plafonnÃ© 100
    species_count = len(species_seen)
    diversity_score = min(100, 10 + (species_count - 1) * 12) if species_count else 0

    # Carbone : plafonnÃ© Ã  5 tCOâ‚‚/ha (valeur rÃ©aliste pour agroforesterie cacao)
    carbon_score = min(100, round(carbon_sum / 5 * 100))

    # ConformitÃ© globale : ombrage 40% + diversitÃ© 30% + carbone 30%
    conformity_score = round(shade_score * 0.4 + diversity_score * 0.3 + carbon_score * 0.3)

    return {
        "shade_score": shade_score,
        "diversity_score": diversity_score,
        "carbon_stock_tco2_ha": round(carbon_sum, 2),
        "carbon_score": carbon_score,
        "conformity_score": conformity_score,
        "total_trees_per_ha": round(total_trees, 1),
        "species_count": species_count,
    }



def _build_recommendations(metrics: dict, records: list) -> list:
    recos = []
    shade    = metrics["shade_score"]
    div      = metrics["diversity_score"]
    carbon   = metrics["carbon_score"]
    conf     = metrics["conformity_score"]
    trees    = metrics["total_trees_per_ha"]
    sp_count = metrics["species_count"]

    # Ombrage
    if shade == 0:
        recos.append({"priority":"high","icon":"ðŸŒ³","title":"Aucun arbre d'ombrage enregistrÃ©",
            "action":"Planter en urgence des arbres d'ombrage a croissance rapide : Gliricidia sepium ou Musa spp. (Bananier) â€” objectif minimum 20 arbres/ha."})
    elif shade < 35:
        recos.append({"priority":"high","icon":"ðŸŒ¿","title":"Ombrage insuffisant â€” stress thermique possible",
            "action":f"Densite actuelle : {trees} arbres/ha. Planter 15 a 20 arbres/ha supplementaires de Gliricidia ou Erythrina pour atteindre l'optimal (20-50%)."})
    elif shade > 75:
        recos.append({"priority":"medium","icon":"âœ‚ï¸","title":"Ombrage excessif â€” risque fongique",
            "action":"Canopee trop dense (> 75%). Elaguer les arbres d'ombrage pour ameliorer la circulation d'air et reduire les risques de pourriture des cabosses."})
    else:
        recos.append({"priority":"low","icon":"âœ…","title":"Ombrage optimal",
            "action":"Densite d'ombrage dans la plage ideale (20-75%). Maintenir les pratiques actuelles."})

    # Diversite
    if sp_count == 1:
        recos.append({"priority":"medium","icon":"ðŸŒ±","title":"Diversite floristique faible â€” 1 seule espece",
            "action":"Introduire 2 a 3 especes complementaires. Recommandations : Persea americana (Avocatier) pour les revenus + Gliricidia sepium pour la fixation d'azote."})
    elif sp_count == 2:
        recos.append({"priority":"low","icon":"ðŸŒ¿","title":"Diversite a ameliorer",
            "action":"Objectif : 3 especes minimum pour la conformite EUDR. Ajouter une espece de strate superieure (Iroko, Manguier) pour ameliorer le score carbone."})
    elif sp_count >= 3:
        recos.append({"priority":"low","icon":"âœ…","title":"Bonne diversite floristique",
            "action":f"{sp_count} especes enregistrees. Continuer a diversifier avec des essences a fort potentiel carbone pour renforcer la certification."})

    # Carbone
    if 0 < carbon < 20:
        recos.append({"priority":"medium","icon":"ðŸŒ","title":"Stock carbone tres faible",
            "action":"Planter des essences a fort potentiel carbone : Milicia excelsa (Iroko), Ceiba pentandra (Fromager), Khaya senegalensis. Objectif : 1 tCO2/ha minimum."})
    elif carbon < 50:
        recos.append({"priority":"low","icon":"ðŸ“ˆ","title":"Stock carbone en developpement",
            "action":"Augmenter la densite d'arbres a longue duree de vie (Iroko, Frake, Khaya) pour accelerer la sequestration carbone et acceder aux financements climatiques."})

    # Conformite globale
    if conf < 35:
        recos.append({"priority":"high","icon":"âš ï¸","title":"Non conforme aux standards EUDR",
            "action":"Score de conformite critique. Votre plantation ne repond pas encore aux exigences EUDR. Appliquer en priorite les recommandations ombrage et diversite."})
    elif conf < 65:
        recos.append({"priority":"medium","icon":"ðŸ“‹","title":"Conformite partielle â€” ameliorations necessaires",
            "action":"Des progres ont ete faits mais des ajustements sont requis. Concentrez-vous sur le point ayant le score le plus faible."})
    else:
        recos.append({"priority":"low","icon":"ðŸ†","title":"Plantation conforme aux standards agroforestiers",
            "action":"Excellent niveau de conformite. Cette plantation peut etre presentee aux acheteurs et certifications EUDR/Rainforest Alliance."})

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recos.sort(key=lambda x: priority_order.get(x["priority"], 3))
    return recos

class AgroforestryCreate(BaseModel):
    species_name: str
    local_name: Optional[str] = None
    layer: Optional[str] = None
    count_per_hectare: float
    avg_age_years: Optional[float] = None
    notes: Optional[str] = None


@router.get("/species-library")
def get_species_library(current_user: User = Depends(get_current_user)):
    """Retourne la bibliothÃ¨que des espÃ¨ces agroforestiÃ¨res."""
    return SPECIES_LIBRARY




@router.put("/plantations/{plantation_id}/plants")
def update_plant_count(
    plantation_id: int,
    plant_count: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met a jour le nombre de plants d'une plantation."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if plant_count < 0:
        raise HTTPException(status_code=400, detail="Nombre de plants invalide.")

    plantation.plant_count = plant_count
    db.commit()

    result = {"plant_count": plant_count, "plantation_id": plantation_id}
    if plantation.hectares and plantation.hectares > 0:
        density = round(plant_count / plantation.hectares)
        result["density_per_ha"] = density
        if density < 800:
            result["alert_level"] = "warning"
            result["alert"] = f"Densite insuffisante ({density} pieds/ha). Minimum CCC : 800 pieds/ha."
        elif density > 1200:
            result["alert_level"] = "info"
            result["alert"] = f"Densite elevee ({density} pieds/ha). Eclaircissage possible."
        else:
            result["alert_level"] = "success"
            result["alert"] = f"Densite optimale ({density} pieds/ha). Conforme CCC."
        result["production_min_kg"] = round(plant_count * 0.4)
        result["production_max_kg"] = round(plant_count * 0.6)
    return result


@router.get("/plantations/{plantation_id}/agroforestry")
def get_agroforestry(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne l'inventaire agroforestier d'une plantation + mÃ©triques calculÃ©es."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    records = db.query(AgroforestryRecord).filter(
        AgroforestryRecord.plantation_id == plantation_id
    ).all()

    metrics = _compute_metrics(records)
    recommendations = _build_recommendations(metrics, records) if records else []

    return {
        "plantation_id": plantation_id,
        "plantation_name": plantation.name,
        "hectares": plantation.hectares,
        "records": [
            {
                "id": r.id,
                "species_name": r.species_name,
                "count_per_hectare": r.count_per_hectare,
            }
            for r in records
        ],
        "metrics": metrics,
        "recommendations": recommendations,
    }


@router.post("/plantations/{plantation_id}/agroforestry", status_code=201)
def add_agroforestry_record(
    plantation_id: int,
    data: AgroforestryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajoute une espÃ¨ce Ã  l'inventaire agroforestier d'une plantation."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="RÃ´le agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    record = AgroforestryRecord(
        plantation_id=plantation_id,
        species_name=data.species_name,
        count_per_hectare=data.count_per_hectare,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "message": "EspÃ¨ce ajoutÃ©e avec succÃ¨s."}


@router.delete("/agroforestry/{record_id}", status_code=200)
def delete_agroforestry_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime un enregistrement agroforestier. Admin uniquement."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="RÃ´le agronome requis.")

    record = db.query(AgroforestryRecord).join(Plantation).filter(
        AgroforestryRecord.id == record_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")

    db.delete(record)
    db.commit()
    return {"message": "Enregistrement supprimÃ©."}


@router.get("/agroforestry/summary")
def get_agroforestry_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bilan agroforestier global de la coopÃ©rative.
    Retourne le stock carbone agrÃ©gÃ© et les scores moyens.
    """
    plantations = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id
    ).all()

    total_carbon = 0.0
    total_trees = 0.0
    conformity_scores = []
    species_all = set()

    for p in plantations:
        records = db.query(AgroforestryRecord).filter(
            AgroforestryRecord.plantation_id == p.id
        ).all()
        if not records:
            continue
        m = _compute_metrics(records)
        ha = p.hectares or 1.0
        total_carbon += m["carbon_stock_tco2_ha"] * ha
        total_trees += m["total_trees_per_ha"] * ha
        conformity_scores.append(m["conformity_score"])
        for r in records:
            species_all.add(r.species_name)

    avg_conformity = round(sum(conformity_scores) / len(conformity_scores)) if conformity_scores else 0

    coop = db.query(Cooperative).filter(
        Cooperative.id == current_user.cooperative_id
    ).first()
    cooperative_name = coop.name if coop else "Cooperative"

    return {
        "cooperative_name": cooperative_name,
        "total_carbon_tco2": round(total_carbon, 1),
        "total_trees_estimated": round(total_trees),
        "avg_conformity_score": avg_conformity,
        "plantations_with_inventory": len(conformity_scores),
        "total_plantations": len(plantations),
        "unique_species_count": len(species_all),
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ Suspension â€” Niveau 1 (Admin coopÃ©rative) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.put("/admin/members/{user_id}/suspend")
def suspend_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suspend un membre de la coopÃ©rative. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas suspendre votre propre compte.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if not member.is_active:
        raise HTTPException(status_code=400, detail="Ce membre est dÃ©jÃ  suspendu.")

    member.is_active = False
    db.commit()
    return {"message": f"Compte {member.email} suspendu.", "user_id": member.id, "is_active": False}


@router.put("/admin/members/{user_id}/activate")
def activate_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """RÃ©active un membre suspendu. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if member.is_active:
        raise HTTPException(status_code=400, detail="Ce membre est dÃ©jÃ  actif.")

    member.is_active = True
    db.commit()
    return {"message": f"Compte {member.email} rÃ©activÃ©.", "user_id": member.id, "is_active": True}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ Suspension â€” Niveau 2 (IKAFFANAN LTD â€” propriÃ©taire plateforme) â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

from fastapi import Header

def _check_owner_key(x_owner_key: Optional[str] = Header(None)):
    """VÃ©rifie la clÃ© propriÃ©taire IKAFFANAN LTD."""
    owner_key = os.getenv("OWNER_API_KEY")
    if not owner_key:
        raise HTTPException(status_code=503, detail="OWNER_API_KEY non configurÃ©e sur le serveur.")
    if x_owner_key != owner_key:
        raise HTTPException(status_code=401, detail="ClÃ© propriÃ©taire invalide.")


@router.get("/owner/cooperatives")
def list_cooperatives(
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Liste toutes les coopÃ©ratives. RÃ©servÃ© IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coops = db.query(Cooperative).order_by(Cooperative.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "members_count": len(c.users),
        }
        for c in coops
    ]


@router.put("/owner/cooperatives/{coop_id}/suspend")
def suspend_cooperative(
    coop_id: int,
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Suspend une coopÃ©rative entiÃ¨re. RÃ©servÃ© IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="CoopÃ©rative introuvable.")
    if not coop.is_active:
        raise HTTPException(status_code=400, detail="CoopÃ©rative dÃ©jÃ  suspendue.")
    coop.is_active = False
    db.commit()
    return {"message": f"CoopÃ©rative '{coop.name}' suspendue.", "coop_id": coop.id, "is_active": False}


@router.put("/owner/cooperatives/{coop_id}/activate")
def activate_cooperative(
    coop_id: int,
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """RÃ©active une coopÃ©rative suspendue. RÃ©servÃ© IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="CoopÃ©rative introuvable.")
    if coop.is_active:
        raise HTTPException(status_code=400, detail="CoopÃ©rative dÃ©jÃ  active.")
    coop.is_active = True
    db.commit()
    return {"message": f"CoopÃ©rative '{coop.name}' rÃ©activÃ©e.", "coop_id": coop.id, "is_active": True}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ Dashboard PropriÃ©taire â€” Statistiques globales IKAFFANAN LTD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.get("/owner/stats")
def owner_stats(
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Statistiques globales de la plateforme. Reserve IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)

    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago  = now - timedelta(days=7)

    # Totaux globaux
    total_coops       = db.query(Cooperative).count()
    active_coops      = db.query(Cooperative).filter(Cooperative.is_active == True).count()
    total_users       = db.query(User).count()
    total_plantations = db.query(Plantation).count()
    total_diagnostics = db.query(Diagnostic).count()

    # Activite recente
    diags_last_30d = db.query(Diagnostic).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).count()
    diags_last_7d = db.query(Diagnostic).filter(
        Diagnostic.created_at >= seven_days_ago
    ).count()

    # CoopÃ©ratives sans activite depuis 30j
    active_coop_ids = db.query(Diagnostic.plantation_id).join(
        Plantation, Diagnostic.plantation_id == Plantation.id
    ).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).subquery()

    all_coop_ids = db.query(Plantation.cooperative_id).distinct().all()
    all_coop_ids_set = {r[0] for r in all_coop_ids if r[0]}

    active_via_diag = db.query(Plantation.cooperative_id).join(
        Diagnostic, Diagnostic.plantation_id == Plantation.id
    ).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).distinct().all()
    active_via_diag_set = {r[0] for r in active_via_diag if r[0]}
    inactive_coop_count = len(all_coop_ids_set - active_via_diag_set)

    # Stats par cooperative
    coops = db.query(Cooperative).order_by(Cooperative.created_at.desc()).all()
    coop_stats = []
    for c in coops:
        n_users = db.query(User).filter(User.cooperative_id == c.id).count()
        n_plantations = db.query(Plantation).filter(Plantation.cooperative_id == c.id).count()
        n_diags = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(Plantation.cooperative_id == c.id).count()
        n_diags_30d = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(
            Plantation.cooperative_id == c.id,
            Diagnostic.created_at >= thirty_days_ago
        ).count()
        last_diag = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(
            Plantation.cooperative_id == c.id
        ).order_by(Diagnostic.created_at.desc()).first()

        coop_stats.append({
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "users_count": n_users,
            "plantations_count": n_plantations,
            "diagnostics_total": n_diags,
            "diagnostics_last_30d": n_diags_30d,
            "last_activity": last_diag.created_at.isoformat() if last_diag and last_diag.created_at else None,
            "status": "active" if n_diags_30d > 0 else ("new" if c.created_at and c.created_at >= thirty_days_ago else "inactive"),
        })

    # Distribution des risques globale
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    latest_diags = db.query(Diagnostic).order_by(Diagnostic.created_at.desc()).limit(500).all()
    seen_plantations = set()
    for d in latest_diags:
        if d.plantation_id not in seen_plantations:
            seen_plantations.add(d.plantation_id)
            risk_counts[d.global_risk_level] = risk_counts.get(d.global_risk_level, 0) + 1

    return {
        "generated_at": now.isoformat(),
        "summary": {
            "total_cooperatives": total_coops,
            "active_cooperatives": active_coops,
            "suspended_cooperatives": total_coops - active_coops,
            "inactive_cooperatives_30d": inactive_coop_count,
            "total_users": total_users,
            "total_plantations": total_plantations,
            "total_diagnostics": total_diagnostics,
            "diagnostics_last_30d": diags_last_30d,
            "diagnostics_last_7d": diags_last_7d,
        },
        "risk_distribution": risk_counts,
        "cooperatives": coop_stats,
    }


@router.put("/admin/members/{user_id}/reset-password")
def reset_member_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reinitialise le mot de passe d'un membre.
    Retourne un mot de passe temporaire a communiquer au membre.
    Admin uniquement.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas reinitialiser votre propre mot de passe.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    # Generer un mot de passe temporaire lisible (format : Mot-XXXX)
    import random, string
    adjectives = ["Cacao", "Foret", "Soleil", "Pluie", "Terre", "Arbre", "Canne", "Feuil"]
    adj = random.choice(adjectives)
    digits = ''.join(random.choices(string.digits, k=4))
    temp_password = f"{adj}-{digits}"

    from app.auth.auth_service import get_password_hash
    member.password_hash = get_password_hash(temp_password)
    db.commit()

    return {
        "message": f"Mot de passe de {member.email} reinitialise.",
        "temp_password": temp_password,
        "user_id": member.id,
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ Conseil IA Agronome â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@router.post("/plantations/{plantation_id}/ai-advice")
async def plantation_ai_advice(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    GÃ©nÃ¨re un conseil agronomique IA complet pour une plantation.
    AgrÃ¨ge : diagnostic, agroforesterie, boundary â†’ appel Claude API.
    """
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    latest_diag = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .order_by(Diagnostic.created_at.desc())
        .first()
    )
    agro_records = (
        db.query(AgroforestryRecord)
        .filter(AgroforestryRecord.plantation_id == plantation_id)
        .all()
    )
    boundary = (
        db.query(PlantationBoundary)
        .filter(PlantationBoundary.plantation_id == plantation_id)
        .first()
    )

    plantation_dict = {
        "id": plantation.id, "name": plantation.name,
        "owner_name": plantation.owner_name, "country": plantation.country,
        "region": plantation.region, "hectares": plantation.hectares, "plant_count": plantation.plant_count,
    }
    diag_dict = {
        "global_score": latest_diag.global_score,
        "global_risk_level": latest_diag.global_risk_level,
        "humidity_pct": latest_diag.humidity_pct,
        "rainfall_mm_month": latest_diag.rainfall_mm_month,
        "avg_temp_c": latest_diag.avg_temp_c,
        "plantation_age_years": latest_diag.plantation_age_years,
        "shade_tree_density_pct": latest_diag.shade_tree_density_pct,
    } if latest_diag else None
    agro_list = [
        {"species_name": r.species_name, "count_per_hectare": r.count_per_hectare}
        for r in agro_records
    ]
    boundary_dict = (
        {"has_boundary": True, "area_hectares": boundary.area_hectares}
        if boundary else {"has_boundary": False}
    )

    result = await get_ai_advice(plantation_dict, diag_dict, agro_list, boundary_dict)
    return result


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# â”€â”€â”€ DÃ©limitation de parcelles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

import json as json_module
import math as math_module

def _calculate_area_hectares(coordinates: list) -> float:
    """
    Calcule la superficie d'un polygone en hectares via la formule de Shoelace
    adaptÃ©e aux coordonnÃ©es gÃ©ographiques (approximation sphÃ©rique).
    PrÃ©cision suffisante pour des parcelles < 100 ha.
    """
    if not coordinates or len(coordinates) < 3:
        return 0.0
    
    # Facteur de conversion : 1 degrÃ© â‰ˆ 111 320 mÃ¨tres Ã  l'Ã©quateur
    R = 6371000  # rayon de la Terre en mÃ¨tres
    
    def to_rad(deg):
        return deg * math_module.pi / 180
    
    n = len(coordinates)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        lat1 = to_rad(coordinates[i][1])
        lat2 = to_rad(coordinates[j][1])
        lng1 = to_rad(coordinates[i][0])
        lng2 = to_rad(coordinates[j][0])
        area += (lng2 - lng1) * (2 + math_module.sin(lat1) + math_module.sin(lat2))
    
    area = abs(area) * R * R / 2
    return round(area / 10000, 4)  # mÂ² â†’ hectares


class BoundaryCreate(BaseModel):
    geojson: str          # GeoJSON string du polygone
    method: str = "manual"  # "manual" | "gps_track"


@router.post("/plantations/{plantation_id}/boundary", status_code=201)
def save_boundary(
    plantation_id: int,
    data: BoundaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sauvegarde ou met Ã  jour les limites d'une plantation."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Valider et parser le GeoJSON
    try:
        geo = json_module.loads(data.geojson)
        coords = geo.get("coordinates", [[]])[0]  # premier anneau du polygone
        if len(coords) < 3:
            raise ValueError("Polygone invalide")
    except Exception:
        raise HTTPException(status_code=400, detail="GeoJSON invalide.")

    # Calculer la superficie
    area = _calculate_area_hectares(coords)
    points_count = len(coords)

    # Mettre Ã  jour ou crÃ©er
    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()

    if boundary:
        boundary.geojson = data.geojson
        boundary.area_hectares = area
        boundary.method = data.method
        boundary.points_count = points_count
    else:
        boundary = PlantationBoundary(
            plantation_id=plantation_id,
            geojson=data.geojson,
            area_hectares=area,
            method=data.method,
            points_count=points_count,
        )
        db.add(boundary)

    # Mettre Ã  jour les hectares de la plantation si pas encore renseignÃ©s
    if not plantation.hectares:
        plantation.hectares = area

    db.commit()
    db.refresh(boundary)

    return {
        "id": boundary.id,
        "plantation_id": plantation_id,
        "area_hectares": area,
        "points_count": points_count,
        "method": data.method,
        "message": f"DÃ©limitation sauvegardÃ©e â€” {area} ha calculÃ©s automatiquement."
    }


@router.get("/plantations/{plantation_id}/boundary")
def get_boundary(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne les limites d'une plantation."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()

    if not boundary:
        return {"has_boundary": False}

    return {
        "has_boundary": True,
        "id": boundary.id,
        "geojson": boundary.geojson,
        "area_hectares": boundary.area_hectares,
        "points_count": boundary.points_count,
        "method": boundary.method,
        "created_at": boundary.created_at.isoformat() if boundary.created_at else None,
    }


@router.delete("/plantations/{plantation_id}/boundary")
def delete_boundary(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime les limites d'une plantation."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()
    if not boundary:
        raise HTTPException(status_code=404, detail="Aucune dÃ©limitation trouvÃ©e.")

    db.delete(boundary)
    db.commit()
    return {"message": "DÃ©limitation supprimÃ©e."}


# ════════════════════════════════════════════════════════════════════════════
# ─── Recoltes (Harvests) ────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

from datetime import datetime, date as date_type


VALID_QUALITIES = {"Bonne", "Moyenne", "Defauts"}


class HarvestCreate(BaseModel):
    harvest_date: datetime
    quantity_kg: float
    quality: str
    price_per_kg_fcfa: Optional[float] = None
    notes: Optional[str] = None
    is_historical: bool = False


class HarvestUpdate(BaseModel):
    harvest_date: Optional[datetime] = None
    quantity_kg: Optional[float] = None
    quality: Optional[str] = None
    price_per_kg_fcfa: Optional[float] = None
    notes: Optional[str] = None


def compute_season(d) -> str:
    """
    Determine la saison cacao en Cote d'Ivoire :
    - "grande"      : octobre a janvier (mois 10, 11, 12, 1)
    - "petite"      : avril a juin (mois 4, 5, 6)
    - "intersaison" : autres mois (fevrier, mars, juillet, aout, septembre)
    """
    if d is None:
        return "intersaison"
    m = d.month if hasattr(d, "month") else d
    if m in (10, 11, 12, 1):
        return "grande"
    if m in (4, 5, 6):
        return "petite"
    return "intersaison"


def _check_plantation_access(plantation_id: int, db: Session, current_user: User) -> Plantation:
    """Verifie que la plantation existe et appartient a la cooperative de l'utilisateur."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    return plantation


@router.post("/plantations/{plantation_id}/harvests", status_code=201)
def create_harvest(
    plantation_id: int,
    harvest: HarvestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cree une nouvelle recolte. Reserve aux roles admin et agronomist."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Role agronome ou admin requis.")

    _check_plantation_access(plantation_id, db, current_user)

    if harvest.quality not in VALID_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Qualite invalide. Valeurs acceptees : {sorted(VALID_QUALITIES)}",
        )
    if harvest.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="La quantite doit etre superieure a 0.")
    if harvest.price_per_kg_fcfa is not None and harvest.price_per_kg_fcfa < 0:
        raise HTTPException(status_code=400, detail="Le prix ne peut pas etre negatif.")

    new_harvest = Harvest(
        plantation_id=plantation_id,
        harvest_date=harvest.harvest_date,
        quantity_kg=harvest.quantity_kg,
        quality=harvest.quality,
        price_per_kg_fcfa=harvest.price_per_kg_fcfa,
        season=compute_season(harvest.harvest_date),
        notes=harvest.notes,
        is_historical=harvest.is_historical,
        created_by_user_id=current_user.id,
    )
    db.add(new_harvest)
    db.commit()
    db.refresh(new_harvest)
    return new_harvest


@router.get("/plantations/{plantation_id}/harvests")
def list_harvests(
    plantation_id: int,
    year: Optional[int] = None,
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les recoltes d'une plantation, triees par date decroissante."""
    _check_plantation_access(plantation_id, db, current_user)

    query = db.query(Harvest).filter(Harvest.plantation_id == plantation_id)

    if year is not None:
        query = query.filter(func.extract("year", Harvest.harvest_date) == year)
    if season is not None:
        if season not in ("grande", "petite", "intersaison"):
            raise HTTPException(status_code=400, detail="Saison invalide.")
        query = query.filter(Harvest.season == season)

    return query.order_by(Harvest.harvest_date.desc()).all()


@router.get("/plantations/{plantation_id}/harvests/stats")
def harvest_stats(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Statistiques agregees des recoltes d'une plantation :
    - total_kg_all_time
    - total_kg_current_year
    - count_total
    - by_season : { "grande": kg, "petite": kg, "intersaison": kg } pour l'annee en cours
    - by_year   : [ { "year": 2025, "total_kg": ... }, ... ]
    """
    _check_plantation_access(plantation_id, db, current_user)

    harvests = db.query(Harvest).filter(Harvest.plantation_id == plantation_id).all()

    if not harvests:
        return {
            "total_kg_all_time": 0,
            "total_kg_current_year": 0,
            "count_total": 0,
            "by_season": {"grande": 0, "petite": 0, "intersaison": 0},
            "by_year": [],
        }

    current_year = datetime.now().year

    total_all = sum(h.quantity_kg for h in harvests)
    total_current_year = sum(
        h.quantity_kg for h in harvests if h.harvest_date.year == current_year
    )

    by_season = {"grande": 0.0, "petite": 0.0, "intersaison": 0.0}
    for h in harvests:
        if h.harvest_date.year == current_year and h.season in by_season:
            by_season[h.season] += h.quantity_kg

    years_dict = {}
    for h in harvests:
        y = h.harvest_date.year
        years_dict[y] = years_dict.get(y, 0) + h.quantity_kg
    by_year = [
        {"year": y, "total_kg": round(kg, 2)}
        for y, kg in sorted(years_dict.items(), reverse=True)
    ]

    return {
        "total_kg_all_time": round(total_all, 2),
        "total_kg_current_year": round(total_current_year, 2),
        "count_total": len(harvests),
        "by_season": {k: round(v, 2) for k, v in by_season.items()},
        "by_year": by_year,
    }


@router.put("/harvests/{harvest_id}")
def update_harvest(
    harvest_id: int,
    update: HarvestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Modifie une recolte existante. Reserve aux admin et agronomist."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Role agronome ou admin requis.")

    harvest = db.query(Harvest).filter(Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Recolte introuvable.")

    _check_plantation_access(harvest.plantation_id, db, current_user)

    if update.quality is not None and update.quality not in VALID_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Qualite invalide. Valeurs acceptees : {sorted(VALID_QUALITIES)}",
        )
    if update.quantity_kg is not None and update.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="La quantite doit etre superieure a 0.")
    if update.price_per_kg_fcfa is not None and update.price_per_kg_fcfa < 0:
        raise HTTPException(status_code=400, detail="Le prix ne peut pas etre negatif.")

    if update.harvest_date is not None:
        harvest.harvest_date = update.harvest_date
        harvest.season = compute_season(update.harvest_date)
    if update.quantity_kg is not None:
        harvest.quantity_kg = update.quantity_kg
    if update.quality is not None:
        harvest.quality = update.quality
    if update.price_per_kg_fcfa is not None:
        harvest.price_per_kg_fcfa = update.price_per_kg_fcfa
    if update.notes is not None:
        harvest.notes = update.notes

    db.commit()
    db.refresh(harvest)
    return harvest


@router.delete("/harvests/{harvest_id}")
def delete_harvest(
    harvest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime une recolte. Reserve aux admins."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    harvest = db.query(Harvest).filter(Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Recolte introuvable.")

    _check_plantation_access(harvest.plantation_id, db, current_user)

    db.delete(harvest)
    db.commit()
    return {"message": "Recolte supprimee avec succes."}
