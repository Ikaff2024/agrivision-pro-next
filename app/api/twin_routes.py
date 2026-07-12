"""Jumeau numérique de parcelle (FEATURE-PARCEL-360).

GET /plantations/{id}/twin : vue agrégée (diagnostic, EUDR, déforestation,
agroforesterie, récoltes, CacaoGuard, délimitation) + alertes par règles.
Lecture seule, scope coopérative.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, Producer, User
from app.services.child_risk import assess_producer_child_risk, build_coop_child_risk
from app.services.geo import build_coop_overlaps, find_overlaps, validate_geometry
from app.services.twin import build_coop_risk, build_twin, compute_alerts
from app.services.weather import get_weather

router = APIRouter(tags=["Jumeau de parcelle"])

# Rôles autorisés à consulter le risque enfant (donnée sensible de protection).
_CHILD_RISK_ROLES = {"admin", "agronomist", "gestionnaire", "technician"}


@router.get("/twin/at-risk")
async def get_coop_twin_at_risk(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None, description="Filtrer : high|medium|low"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vue coopérative : parcelles classées par risque (alertes du jumeau agrégées).

    Scopée à la coopérative de l'utilisateur. Calcul batché → scalable jusqu'à
    des milliers de parcelles. Liste priorisée (parcelles à traiter d'abord).
    """
    sev = severity if severity in ("high", "medium", "low") else None
    return build_coop_risk(
        db, current_user.cooperative_id, limit=limit, offset=offset, severity=sev,
    )


@router.get("/plantations/{plantation_id}/twin")
async def get_plantation_twin(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Jumeau d'une parcelle : agrégation des signaux existants + alertes actionnables."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if current_user.cooperative_id is not None and plantation.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre coopérative.")

    twin = build_twin(db, plantation)
    # Météo courante (Open-Meteo, best-effort) — complète la vue 360°.
    twin["weather"] = await get_weather(plantation.latitude, plantation.longitude)
    alerts = compute_alerts(twin)
    return {"twin": twin, "alerts": alerts, "alert_count": len(alerts)}


# ── Palier 2 : risque précoce de travail d'enfant (aide à l'enquête) ─────────

@router.get("/twin/child-risk/at-risk")
async def get_coop_child_risk(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    level: Optional[str] = Query(None, description="Filtrer : eleve|moyen|faible"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ménages classés par PRIORITÉ D'ENQUÊTE (risque précoce de travail d'enfant).

    Indicateur EXPLICABLE (facteurs affichés), scopé à la coopérative. Aide à la
    décision : il priorise les visites, il ne rend AUCUN verdict automatique.
    """
    if current_user.role not in _CHILD_RISK_ROLES:
        raise HTTPException(status_code=403, detail="Réservé aux rôles de protection (direction/agent).")
    lvl = level if level in ("eleve", "moyen", "faible") else None
    return build_coop_child_risk(
        db, current_user.cooperative_id, limit=limit, offset=offset, level=lvl,
    )


@router.get("/producers/{producer_id}/child-risk")
async def get_producer_child_risk(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Risque précoce d'un ménage (vue fiche producteur), avec les facteurs contributifs."""
    if current_user.role not in _CHILD_RISK_ROLES:
        raise HTTPException(status_code=403, detail="Réservé aux rôles de protection (direction/agent).")
    producer = db.query(Producer).filter(Producer.id == producer_id).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    if current_user.cooperative_id is not None and producer.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Producteur d'une autre coopérative.")
    return assess_producer_child_risk(db, producer)


# ── Analyse géométrique (validité + chevauchement / double-mapping) ───────────

@router.get("/geo/overlaps")
async def get_coop_overlaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paires de parcelles qui se CHEVAUCHENT dans la coopérative (double-mapping).

    Scopé à la coopérative. Renvoie `available=False` si le module géo (shapely)
    n'est pas disponible côté serveur.
    """
    return build_coop_overlaps(db, current_user.cooperative_id)


@router.get("/plantations/{plantation_id}/geo-check")
async def get_plantation_geo_check(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contrôle géométrique d'une parcelle : validité du polygone + chevauchements."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if current_user.cooperative_id is not None and plantation.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre coopérative.")
    boundary = plantation.boundary
    validity = (validate_geometry(boundary.geojson) if boundary
                else {"available": True, "valid": False, "reason": "Parcelle non délimitée."})
    return {"validity": validity, **find_overlaps(db, plantation)}


# ── Export SIG (GeoJSON / KML / Shapefile) ────────────────────────────────────

def _attachment(content, media_type: str, filename: str) -> Response:
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/geo/export.geojson")
async def export_geojson_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export GeoJSON des parcelles de la coopérative (format EUDR). Cloisonné."""
    from app.services.geo_export import coop_slug, export_geojson
    fc = export_geojson(db, current_user.cooperative_id)
    return _attachment(json.dumps(fc, ensure_ascii=False), "application/geo+json",
                       f"parcelles_{coop_slug(db, current_user.cooperative_id)}.geojson")


@router.get("/geo/export.kml")
async def export_kml_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export KML des parcelles (Google Earth). Cloisonné."""
    from app.services.geo_export import coop_slug, export_kml
    kml = export_kml(db, current_user.cooperative_id)
    return _attachment(kml, "application/vnd.google-earth.kml+xml",
                       f"parcelles_{coop_slug(db, current_user.cooperative_id)}.kml")


@router.get("/geo/export.shp.zip")
async def export_shapefile_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export Shapefile (zip) des parcelles — certificateurs / outils SIG. Cloisonné."""
    from app.services.geo_export import coop_slug, export_shapefile_zip
    data = export_shapefile_zip(db, current_user.cooperative_id)
    if data is None:
        raise HTTPException(status_code=503, detail="Module Shapefile indisponible côté serveur.")
    return _attachment(data, "application/zip",
                       f"parcelles_{coop_slug(db, current_user.cooperative_id)}.shp.zip")
