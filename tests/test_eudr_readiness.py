"""Tests — tableau « Prêt pour l'EUDR » (/eudr/readiness)."""
import json
from datetime import datetime, timedelta

from app.auth.auth_service import create_access_token
from app.db.models import (
    Cooperative, DeforestationCheck, Inspection, Plantation, PlantationBoundary, User,
)
from tests.conftest import TestingSessionLocal


VALID_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[[-6.59, 5.78], [-6.58, 5.78], [-6.58, 5.79], [-6.59, 5.79], [-6.59, 5.78]]],
})


def _auth(user):
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email, "role": user.role, "coop_id": user.cooperative_id,
    })}


def _gap(body, rule_id):
    return next(g for g in body["gaps"] if g["rule_id"] == rule_id)


def _seed_two_plantations():
    """P1 conforme (6/6) ; P2 sans polygone ni contrôle déforestation."""
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop readiness", country="CI"); db.add(coop); db.flush()
        admin = User(email="admin.ready@test.ci", password_hash="x", role="admin", cooperative_id=coop.id)
        db.add(admin); db.flush()

        p1 = Plantation(name="P1 conforme", owner_name="O1", country="CI", region="Soubre",
                        latitude=5.785, longitude=-6.585, hectares=1.0, cooperative_id=coop.id)
        db.add(p1); db.flush()
        db.add(PlantationBoundary(plantation_id=p1.id, geojson=VALID_POLYGON, area_hectares=1.05,
                                  points_count=5, method="manual"))
        db.add(Inspection(plantation_id=p1.id, type="EXTERNE", date=datetime.utcnow() - timedelta(days=20)))
        db.add(DeforestationCheck(plantation_id=p1.id, verdict="clear", source="gfw",
                                  check_date=datetime.utcnow()))

        p2 = Plantation(name="P2 a delimiter", owner_name="O2", country="CI", region="Soubre",
                        latitude=5.785, longitude=-6.585, hectares=1.0, cooperative_id=coop.id)
        db.add(p2); db.flush()
        db.add(Inspection(plantation_id=p2.id, type="EXTERNE", date=datetime.utcnow() - timedelta(days=20)))
        # P2 : pas de polygone, pas de contrôle déforestation

        db.commit()
        return _auth(admin), p2.id
    finally:
        db.close()


def test_readiness_aggregates_gaps(client):
    auth, p2_id = _seed_two_plantations()
    r = client.get("/eudr/readiness", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total"] == 2
    assert body["ready"] == 1           # seul P1 est conforme
    assert body["ready_pct"] == 50.0

    # P2 bloque sur : polygone, superficie (géométrie absente), déforestation
    assert _gap(body, "polygon_valid")["count"] == 1
    assert _gap(body, "no_deforestation")["count"] == 1
    assert _gap(body, "area_matches")["count"] == 1
    # P1 et P2 ont une inspection récente et aucun blocage
    assert _gap(body, "recent_inspection")["count"] == 0
    assert _gap(body, "no_active_block")["count"] == 0

    # La parcelle à délimiter est bien listée, avec une action recommandée.
    poly_gap = _gap(body, "polygon_valid")
    assert any(p["id"] == p2_id for p in poly_gap["plantations"])
    assert poly_gap["action"]


def test_readiness_empty_coop(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop ready vide", country="CI"); db.add(coop); db.flush()
        admin = User(email="admin.readyempty@test.ci", password_hash="x", role="admin", cooperative_id=coop.id)
        db.add(admin); db.commit()
        auth = _auth(admin)
    finally:
        db.close()
    body = client.get("/eudr/readiness", headers=auth).json()
    assert body["total"] == 0
    assert body["ready_pct"] == 0.0
    assert len(body["gaps"]) == len(["polygon_valid", "no_deforestation", "recent_inspection",
                                     "no_active_block", "area_matches", "gps_in_cocoa_zone"])


def test_readiness_requires_auth(client):
    assert client.get("/eudr/readiness").status_code == 401


def test_readiness_viewer_forbidden(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop ready viewer", country="CI"); db.add(coop); db.flush()
        viewer = User(email="viewer.ready@test.ci", password_hash="x", role="viewer", cooperative_id=coop.id)
        db.add(viewer); db.commit()
        auth = _auth(viewer)
    finally:
        db.close()
    assert client.get("/eudr/readiness", headers=auth).status_code == 403
