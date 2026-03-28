import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cacao_engine.engine import run_engine
from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.db.database import get_db
from app.db.models import Diagnostic, Plantation, User
from app.auth.auth_service import get_current_user
from app.ml.image_diagnosis import analyze_leaf_image
from app.satellite.ndvi_service import get_ndvi

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
    return report


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
    results = []
    for p in plantations:
        latest = (
            db.query(Diagnostic)
            .filter(Diagnostic.plantation_id == p.id)
            .order_by(Diagnostic.created_at.desc())
            .first()
        )
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
    high = medium = low = 0
    for p in plantations:
        latest = (
            db.query(Diagnostic)
            .filter(Diagnostic.plantation_id == p.id)
            .order_by(Diagnostic.created_at.desc())
            .first()
        )
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

    os.makedirs("uploads", exist_ok=True)
    file_location = f"uploads/{file.filename}"

    try:
        with open(file_location, "wb+") as f:
            f.write(await file.read())

        diagnosis_result = analyze_leaf_image(file_location)

        if plantation_id is not None:
            plantation = db.query(Plantation).filter(
                Plantation.id == plantation_id,
                Plantation.cooperative_id == current_user.cooperative_id,
            ).first()
            if not plantation:
                raise HTTPException(status_code=404, detail="Plantation introuvable.")

            new_diagnostic = Diagnostic(
                plantation_id=plantation_id,
                country=plantation.country,
                region=plantation.region,
                humidity_pct=0.0,
                rainfall_mm_month=0.0,
                avg_temp_c=0.0,
                global_score=diagnosis_result["confidence"] * 100,
                global_risk_level=diagnosis_result["severity"],
            )
            db.add(new_diagnostic)
            db.commit()
            db.refresh(new_diagnostic)

    finally:
        # Nettoyage garanti même en cas d'erreur
        if os.path.exists(file_location):
            os.remove(file_location)

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
