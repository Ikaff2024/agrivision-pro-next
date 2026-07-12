"""
Endpoints télédétection avancée : indices (NDVI/NDMI), séries temporelles,
signal de déforestation. S'appuie sur l'abstraction `app.satellite.provider`
(fallback simulation sans clé, bascule Copernicus/GFW dès configuration).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, User
from app.satellite.provider import (
    get_deforestation_for_geometry,
    get_deforestation_signal,
    get_indices,
    get_timeseries,
    provider_status,
)

router = APIRouter(prefix="/satellite", tags=["Satellite avancé"])


def _geometry_centroid(geom: dict | None) -> tuple[float, float] | None:
    """Point representatif (centre) d'un polygone GeoJSON -> (lat, lon).

    Moyenne des sommets de l'anneau exterieur : suffisant pour choisir un point
    d'echantillonnage a l'interieur d'une parcelle (bien plus fiable que le point
    GPS stocke, parfois pose sur une piste/trouee -> faux "sol nu"). None si la
    geometrie est inexploitable.
    """
    if not isinstance(geom, dict):
        return None
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if not coords:
        return None
    ring = None
    if gtype == "Polygon":
        ring = coords[0] if coords else None
    elif gtype == "MultiPolygon":
        ring = coords[0][0] if coords and coords[0] else None
    if not ring:
        return None
    pts = [p for p in ring if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(pts) > 1 and pts[0] == pts[-1]:  # ignore le sommet de fermeture duplique
        pts = pts[:-1]
    if not pts:
        return None
    lon = sum(float(p[0]) for p in pts) / len(pts)
    lat = sum(float(p[1]) for p in pts) / len(pts)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (round(lat, 6), round(lon, 6))


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


class PrecheckRequest(BaseModel):
    """Pré-contrôle EUDR d'une parcelle NON encore enregistrée."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    # Optionnel : polygone GeoJSON exact de la parcelle (plus precis que le point).
    geometry: dict | None = None


def _precheck_verdict(defo: dict) -> dict:
    """Traduit un signal de déforestation en verdict d'éligibilité EUDR (GO/NO-GO)."""
    simulated = (defo.get("source") == "simulation")
    alerts = int(defo.get("alerts_count") or 0)
    loss = bool(defo.get("loss_detected"))
    if loss or alerts > 0:
        return {
            "eligible": False,
            "verdict": "NON_ELIGIBLE",
            "level": "high",
            "title": "Achat déconseillé — déforestation détectée",
            "message": (
                f"{alerts} alerte(s) de déforestation depuis {defo.get('since', '2020-12-31')} "
                "sur cette zone. La parcelle est à risque de non-conformité EUDR : "
                "n'achetez pas / n'intégrez pas sans vérification terrain approfondie."
            ),
        }
    if simulated:
        return {
            "eligible": None,
            "verdict": "INDETERMINE",
            "level": "medium",
            "title": "Vérification réelle indisponible",
            "message": (
                "Le contrôle satellite de déforestation n'est pas activé (mode simulation). "
                "Résultat non probant pour l'EUDR — configurez GFW_API_KEY pour un verdict réel."
            ),
        }
    return {
        "eligible": True,
        "verdict": "ELIGIBLE",
        "level": "low",
        "title": "Feu vert — aucune déforestation détectée",
        "message": (
            f"Aucune alerte de déforestation depuis {defo.get('since', '2020-12-31')} "
            "sur cette zone. Parcelle éligible à l'achat / à l'intégration (sous réserve "
            "des autres critères EUDR : géolocalisation, traçabilité)."
        ),
    }


def _land_cover_note(lat, lng) -> dict | None:
    """NDVI au point : signale si la zone NE RESSEMBLE PAS à une parcelle cultivée.

    Garde-fou anti-« faux feu vert » : à Bingerville (urbain) la déforestation est
    à juste titre nulle, mais ce n'est pas une plantation. On le dit clairement.
    Uniquement sur données RÉELLES (pas en simulation, qui n'est pas fiable au lieu).
    """
    if lat is None or lng is None:
        return None
    try:
        idx = get_indices(lat, lng)
    except Exception:  # noqa: BLE001
        return None
    if idx.get("source") == "simulation":
        return None
    ndvi = idx.get("ndvi")
    if idx.get("ndvi_status") == "INDETERMINE":
        return {
            "implausible": True,
            "ndvi": ndvi,
            "message": (
                f"Couvert végétal très faible ici (NDVI {ndvi}) : zone urbaine, sol nu ou "
                "plan d'eau — cela ne ressemble pas à une parcelle cultivée. Vérifiez que "
                "les coordonnées correspondent bien à la plantation."
            ),
        }
    return {"implausible": False, "ndvi": ndvi}


@router.post("/precheck")
def deforestation_precheck(
    req: PrecheckRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Pré-contrôle EUDR RAPIDE d'une parcelle *avant* de l'acheter ou de l'enregistrer.

    Ne nécessite aucune plantation en base : on interroge directement la
    déforestation (polygone exact si fourni, sinon zone ~1 km autour du point) et
    on renvoie un verdict d'éligibilité clair (GO / NO-GO / indéterminé).
    """
    geom = req.geometry if isinstance(req.geometry, dict) else None
    if geom and geom.get("type") == "Feature":
        geom = geom.get("geometry")
    lat, lng = req.latitude, req.longitude
    if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
        defo = get_deforestation_for_geometry(geom)
        cen = _geometry_centroid(geom)
        if cen:
            lat, lng = cen
    else:
        defo = get_deforestation_signal(req.latitude, req.longitude)

    verdict = _precheck_verdict(defo)
    # Plausibilité du couvert : un "Feu vert" sur une zone urbaine/sol nu est trompeur.
    land = _land_cover_note(lat, lng)
    if land and land.get("implausible") and verdict.get("eligible") is True:
        verdict = {
            **verdict,
            "level": "medium",
            "title": "Zone à vérifier — ne ressemble pas à une parcelle",
            "message": (
                land["message"] + " (Aucune alerte de déforestation depuis "
                f"{defo.get('since', '2020-12-31')}, mais le couvert ne correspond pas à une culture.)"
            ),
        }
    return {
        "latitude": req.latitude,
        "longitude": req.longitude,
        "deforestation": defo,
        "land_cover": land,
        **verdict,
    }


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

    # Geometrie de la parcelle (si delimitee).
    boundary = plantation.boundary  # relation 1-1 (PlantationBoundary)
    geom = None
    if boundary and boundary.geojson:
        try:
            geom = json.loads(boundary.geojson)
            if isinstance(geom, dict) and geom.get("type") == "Feature":
                geom = geom.get("geometry")
        except Exception:
            geom = None

    # Point d'echantillonnage : on privilegie le CENTRE du polygone (plus
    # representatif de la parcelle que le point GPS stocke), sinon le point GPS.
    centroid = _geometry_centroid(geom)
    if centroid is not None:
        lat, lon = centroid
        sample_source = "polygon_centroid"
    elif plantation.latitude is not None and plantation.longitude is not None:
        lat, lon = plantation.latitude, plantation.longitude
        sample_source = "gps_point"
    else:
        raise HTTPException(
            status_code=400,
            detail="Plantation sans coordonnées GPS ni parcelle délimitée.",
        )

    # Déforestation : sur le POLYGONE EXACT de la parcelle si délimitée (plus juste
    # pour l'EUDR), sinon sur une zone ~1 km autour du point d'echantillonnage.
    deforestation = None
    if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
        try:
            deforestation = get_deforestation_for_geometry(geom)
        except Exception:
            deforestation = None
    if deforestation is None:
        deforestation = get_deforestation_signal(lat, lon)

    return {
        "plantation_id": plantation.id,
        "plantation_name": plantation.name,
        "latitude": lat,
        "longitude": lon,
        "has_boundary": bool(boundary and boundary.geojson),
        "sample_source": sample_source,
        "indices": get_indices(lat, lon),
        "ndvi_timeseries": get_timeseries(lat, lon, index="ndvi", months=months),
        "ndmi_timeseries": get_timeseries(lat, lon, index="ndmi", months=months),
        "deforestation": deforestation,
    }
