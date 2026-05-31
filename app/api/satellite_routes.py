"""
Endpoints télédétection avancée : indices (NDVI/NDMI), séries temporelles,
signal de déforestation. S'appuie sur l'abstraction `app.satellite.provider`
(fallback simulation sans clé, bascule Copernicus/GFW dès configuration).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, User
from app.satellite.provider import (
    get_deforestation_signal,
    get_indices,
    get_timeseries,
    provider_status,
)

router = APIRouter(prefix="/satellite", tags=["Satellite avancé"])


@router.get("/status")
def satellite_status(current_user: User = Depends(get_current_user)):
    """Indique quels fournisseurs satellite sont configurés."""
    return provider_status()


@router.get("/indices")
def indices(
    latitude: float = Query(...),
    longitude: float = Query(...),
    current_user: User = Depends(get_current_user),
):
    """NDVI + NDMI + statuts pour un point."""
    return get_indices(latitude, longitude)


@router.get("/timeseries")
def timeseries(
    latitude: float = Query(...),
    longitude: float = Query(...),
    index: str = Query("ndvi"),
    months: int = Query(12, ge=1, le=36),
    current_user: User = Depends(get_current_user),
):
    """Série temporelle mensuelle d'un indice (ndvi|ndmi)."""
    return get_timeseries(latitude, longitude, index=index, months=months)


@router.get("/deforestation")
def deforestation(
    latitude: float = Query(...),
    longitude: float = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Signal de déforestation (alertes) pour un point."""
    return get_deforestation_signal(latitude, longitude)


def _accessible_plantation(plantation_id: int, db: Session, user: User) -> Plantation:
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if user.cooperative_id is not None and plantation.cooperative_id != user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre coopérative.")
    return plantation


@router.get("/plantations/{plantation_id}/advanced")
def plantation_advanced(
    plantation_id: int,
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyse satellite avancée d'une plantation : indices courants (NDVI/NDMI),
    séries temporelles NDVI & NDMI, et signal de déforestation. Cloisonné coop.
    """
    plantation = _accessible_plantation(plantation_id, db, current_user)
    if plantation.latitude is None or plantation.longitude is None:
        raise HTTPException(status_code=400, detail="Plantation sans coordonnées GPS.")

    lat, lon = plantation.latitude, plantation.longitude
    return {
        "plantation_id": plantation.id,
        "plantation_name": plantation.name,
        "latitude": lat,
        "longitude": lon,
        "indices": get_indices(lat, lon),
        "ndvi_timeseries": get_timeseries(lat, lon, index="ndvi", months=months),
        "ndmi_timeseries": get_timeseries(lat, lon, index="ndmi", months=months),
        "deforestation": get_deforestation_signal(lat, lon),
    }
