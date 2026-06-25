"""Géo-horodatage anti-fraude de la collecte terrain (visites, enquêtes).

Mutualisé par tous les formulaires terrain : à la validation, on enregistre le
GPS capté par l'appareil + l'heure SERVEUR (non falsifiable), et on le compare au
**lieu attendu** (GPS connu du producteur / de la parcelle). Verdict :

- ``verified``     : GPS présent, à ≤ seuil du lieu attendu.
- ``far``          : GPS présent mais trop loin du lieu attendu (suspect).
- ``no_fix``       : aucun GPS capté (et pas de motif) → à vérifier.
- ``overridden``   : aucun GPS, mais motif explicite fourni (tracé, audité).
- ``no_reference`` : GPS capté mais aucun lieu attendu connu → non vérifiable.

Politique « capture + signalement » : on ne BLOQUE pas (le hors-ligne / mauvais
signal est fréquent au champ), on REND VISIBLE et auditable. cf. retours terrain.
"""
from __future__ import annotations

import math
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import FieldGeostamp


def max_distance_m() -> float:
    """Seuil de distance (m) au-delà duquel une visite est marquée « hors zone »."""
    try:
        return float(os.getenv("GEOSTAMP_MAX_DISTANCE_M", "500"))
    except ValueError:
        return 500.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance en mètres entre deux points GPS (formule de haversine)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def compute_status(captured_lat, captured_lng, expected_lat, expected_lng,
                   override_reason=None, threshold_m=None):
    """Renvoie (geo_status, distance_m|None) selon la politique ci-dessus."""
    threshold = threshold_m if threshold_m is not None else max_distance_m()
    if captured_lat is None or captured_lng is None:
        return ("overridden" if (override_reason or "").strip() else "no_fix"), None
    if expected_lat is None or expected_lng is None:
        return "no_reference", None
    d = haversine_m(captured_lat, captured_lng, expected_lat, expected_lng)
    return ("verified" if d <= threshold else "far"), round(d, 1)


def record_geostamp(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    cooperative_id: Optional[int] = None,
    captured_lat: Optional[float] = None,
    captured_lng: Optional[float] = None,
    accuracy: Optional[float] = None,
    client_reported_at=None,
    expected_lat: Optional[float] = None,
    expected_lng: Optional[float] = None,
    recorded_by: Optional[str] = None,
    override_reason: Optional[str] = None,
    threshold_m: Optional[float] = None,
) -> FieldGeostamp:
    """Crée et enregistre un géo-horodatage pour une entité terrain.

    `flush` seulement (le commit appartient à l'appelant, dans la même transaction
    que la visite/enquête créée ou complétée).
    """
    status, distance = compute_status(
        captured_lat, captured_lng, expected_lat, expected_lng, override_reason, threshold_m
    )
    gs = FieldGeostamp(
        cooperative_id=cooperative_id,
        entity_type=entity_type,
        entity_id=entity_id,
        captured_latitude=captured_lat,
        captured_longitude=captured_lng,
        captured_accuracy_m=accuracy,
        client_reported_at=client_reported_at,
        expected_latitude=expected_lat,
        expected_longitude=expected_lng,
        distance_m=distance,
        geo_status=status,
        override_reason=(override_reason or None),
        recorded_by=recorded_by,
    )
    db.add(gs)
    db.flush()
    return gs


def geostamp_dict(gs: Optional[FieldGeostamp]) -> Optional[dict]:
    if not gs:
        return None
    return {
        "geo_status": gs.geo_status,
        "distance_m": gs.distance_m,
        "captured_latitude": gs.captured_latitude,
        "captured_longitude": gs.captured_longitude,
        "captured_accuracy_m": gs.captured_accuracy_m,
        "captured_at": gs.captured_at.isoformat() if gs.captured_at else None,
        "override_reason": gs.override_reason,
        "recorded_by": gs.recorded_by,
    }


def latest_for(db: Session, entity_type: str, entity_id: int) -> Optional[FieldGeostamp]:
    """Dernier géo-horodatage connu pour une entité (pour afficher le badge)."""
    return (
        db.query(FieldGeostamp)
        .filter(FieldGeostamp.entity_type == entity_type, FieldGeostamp.entity_id == entity_id)
        .order_by(FieldGeostamp.captured_at.desc(), FieldGeostamp.id.desc())
        .first()
    )


def latest_map(db: Session, entity_type: str, entity_ids: list) -> dict:
    """{entity_id: FieldGeostamp} — le plus récent par entité, pour enrichir une liste."""
    if not entity_ids:
        return {}
    rows = (
        db.query(FieldGeostamp)
        .filter(FieldGeostamp.entity_type == entity_type, FieldGeostamp.entity_id.in_(entity_ids))
        .order_by(FieldGeostamp.captured_at.desc(), FieldGeostamp.id.desc())
        .all()
    )
    out: dict = {}
    for gs in rows:
        out.setdefault(gs.entity_id, gs)   # premier vu = plus récent (tri desc)
    return out
