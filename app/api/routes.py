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

    # ── Couche 2 Agroforesterie : substituer l'ombrage si inventaire disponible ──
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


# ════════════════════════════════════════════════════════════════
# ─── Agroforesterie ──────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════

from app.db.models import AgroforestryRecord

# ── Bibliothèque d'espèces — coefficients agronomiques & carbone ──────────────
# carbon_factor : tCO₂ stockée par arbre par an (allométrie simplifiée FAO/IPCC)
# shade_factor  : contribution à l'ombrage par arbre (arbres/ha → % ombrage)
SPECIES_LIBRARY = [
    # Légumineuses fixatrices d'azote (ombrage rapide)
    {"name":"Gliricidia sepium",    "local":"Gliricidi",    "layer":"intermediate", "carbon_factor":0.012, "shade_factor":0.8,  "category":"Légumineuse"},
    {"name":"Leucaena leucocephala","local":"Leucéna",      "layer":"intermediate", "carbon_factor":0.010, "shade_factor":0.7,  "category":"Légumineuse"},
    {"name":"Erythrina spp.",       "local":"Érythrine",    "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.9,  "category":"Légumineuse"},
    {"name":"Albizzia adianthifolia","local":"Albizzia",    "layer":"superior",     "carbon_factor":0.025, "shade_factor":1.0,  "category":"Légumineuse"},
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
    {"name":"Terminalia superba",   "local":"Fraké",        "layer":"superior",     "carbon_factor":0.038, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Ceiba pentandra",      "local":"Fromager",     "layer":"superior",     "carbon_factor":0.042, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Khaya senegalensis",   "local":"Khaya",        "layer":"superior",     "carbon_factor":0.040, "shade_factor":1.0,  "category":"Timber"},
    # Palmiers / divers
    {"name":"Elaeis guineensis",    "local":"Palmier à huile","layer":"superior",   "carbon_factor":0.020, "shade_factor":0.85, "category":"Divers"},
    {"name":"Cocos nucifera",       "local":"Cocotier",     "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.8,  "category":"Divers"},
    {"name":"Tectona grandis",      "local":"Teck",         "layer":"superior",     "carbon_factor":0.035, "shade_factor":0.9,  "category":"Timber"},
]

def _compute_metrics(records) -> dict:
    """
    Calcule les métriques agroforestières à partir des enregistrements.
    - shade_score      : % d'ombrage estimé (0-100)
    - diversity_score  : score de diversité floristique (0-100)
    - carbon_stock_tco2_ha : stock carbone estimé (tCO₂/ha)
    - conformity_score : score global de conformité agroforestière (0-100)
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
        age = r.avg_age_years or 5          # défaut 5 ans si non renseigné
        total_trees += density
        species_seen.add(r.species_name)

        lib = species_lib.get(r.species_name)
        cf = lib["carbon_factor"] if lib else 0.010   # défaut générique
        sf = lib["shade_factor"]  if lib else 0.6

        # Facteur âge : croît jusqu'à 2.0 à 30 ans (log)
        import math
        age_factor = min(2.0, 0.4 + (math.log1p(age) / math.log1p(30)) * 1.6)

        shade_sum  += density * sf
        carbon_sum += density * cf * age_factor

    # Ombrage : 40 arbres/ha de plein couvert = 100% ombrage (règle empirique cacao)
    shade_score = min(100, round(shade_sum / 40 * 100))

    # Diversité : 1 espèce = 10pts, chaque espèce suppl. +12pts, plafonné 100
    species_count = len(species_seen)
    diversity_score = min(100, 10 + (species_count - 1) * 12) if species_count else 0

    # Carbone : plafonné à 5 tCO₂/ha (valeur réaliste pour agroforesterie cacao)
    carbon_score = min(100, round(carbon_sum / 5 * 100))

    # Conformité globale : ombrage 40% + diversité 30% + carbone 30%
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


class AgroforestryCreate(BaseModel):
    species_name: str
    local_name: Optional[str] = None
    layer: Optional[str] = None
    count_per_hectare: float
    avg_age_years: Optional[float] = None
    notes: Optional[str] = None


@router.get("/species-library")
def get_species_library(current_user: User = Depends(get_current_user)):
    """Retourne la bibliothèque des espèces agroforestières."""
    return SPECIES_LIBRARY


@router.get("/plantations/{plantation_id}/agroforestry")
def get_agroforestry(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne l'inventaire agroforestier d'une plantation + métriques calculées."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    records = db.query(AgroforestryRecord).filter(
        AgroforestryRecord.plantation_id == plantation_id
    ).order_by(AgroforestryRecord.recorded_at.desc()).all()

    metrics = _compute_metrics(records)

    return {
        "plantation_id": plantation_id,
        "plantation_name": plantation.name,
        "hectares": plantation.hectares,
        "records": [
            {
                "id": r.id,
                "species_name": r.species_name,
                "local_name": r.local_name,
                "layer": r.layer,
                "count_per_hectare": r.count_per_hectare,
                "avg_age_years": r.avg_age_years,
                "notes": r.notes,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in records
        ],
        "metrics": metrics,
    }


@router.post("/plantations/{plantation_id}/agroforestry", status_code=201)
def add_agroforestry_record(
    plantation_id: int,
    data: AgroforestryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajoute une espèce à l'inventaire agroforestier d'une plantation."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    record = AgroforestryRecord(
        plantation_id=plantation_id,
        species_name=data.species_name,
        local_name=data.local_name,
        layer=data.layer,
        count_per_hectare=data.count_per_hectare,
        avg_age_years=data.avg_age_years,
        notes=data.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "message": "Espèce ajoutée avec succès."}


@router.delete("/agroforestry/{record_id}", status_code=200)
def delete_agroforestry_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime un enregistrement agroforestier. Admin uniquement."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    record = db.query(AgroforestryRecord).join(Plantation).filter(
        AgroforestryRecord.id == record_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")

    db.delete(record)
    db.commit()
    return {"message": "Enregistrement supprimé."}


@router.get("/agroforestry/summary")
def get_agroforestry_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bilan agroforestier global de la coopérative.
    Retourne le stock carbone agrégé et les scores moyens.
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

    return {
        "total_carbon_tco2": round(total_carbon, 1),
        "total_trees_estimated": round(total_trees),
        "avg_conformity_score": avg_conformity,
        "plantations_with_inventory": len(conformity_scores),
        "total_plantations": len(plantations),
        "unique_species_count": len(species_all),
    }
