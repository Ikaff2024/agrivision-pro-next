"""Tests pour les endpoints EUDR-01a."""
import json
from datetime import datetime, timedelta

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import (
    Cooperative,
    DeforestationCheck,
    Inspection,
    Plantation,
    PlantationBoundary,
    Producer,
    User,
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


def _seed_user_and_plantation(role="admin", with_polygon=True, with_inspection=True,
                              with_deforestation=True):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop EUDR-routes", country="CI")
        db.add(coop); db.flush()
        user = User(email=f"{role}.eudr@test.ci", password_hash="x", role=role, cooperative_id=coop.id)
        producer = Producer(cooperative_id=coop.id, nom_complet="P", is_active=True)
        db.add_all([user, producer]); db.flush()
        p = Plantation(
            name="Test EUDR", owner_name="Owner", country="CI", region="Soubre",
            latitude=5.785, longitude=-6.585, hectares=1.0,
            cooperative_id=coop.id, producer_id=producer.id,
        )
        db.add(p); db.flush()
        if with_polygon:
            db.add(PlantationBoundary(
                plantation_id=p.id, geojson=VALID_POLYGON, area_hectares=1.05,
                points_count=5, method="manual",
            ))
        if with_inspection:
            db.add(Inspection(plantation_id=p.id, type="EXTERNE",
                              date=datetime.utcnow() - timedelta(days=30)))
        if with_deforestation:
            db.add(DeforestationCheck(
                plantation_id=p.id, verdict="clear", source="manual",
                check_date=datetime.utcnow(),
            ))
        db.commit()
        return p.id, _auth(user)
    finally:
        db.close()


# ----------------------------------------------------------------------------
# /plantations/{id}/eudr-score
# ----------------------------------------------------------------------------

def test_eudr_score_perfect_plantation_returns_6(client):
    pid, auth = _seed_user_and_plantation()
    r = client.get(f"/plantations/{pid}/eudr-score", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] == 6
    assert body["status"] == "conforme"
    assert body["badge_color"] == "green"
    assert len(body["rules"]) == 6
    for rule in body["rules"]:
        assert rule["passed"] is True


def test_eudr_score_no_polygon(client):
    pid, auth = _seed_user_and_plantation(with_polygon=False, with_inspection=False,
                                          with_deforestation=False)
    r = client.get(f"/plantations/{pid}/eudr-score", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # polygon:F, area:F, gps:T, recent_inspection:F, no_block:T, no_deforestation:F => 2/6
    assert body["score"] == 2
    assert len(body["rules"]) == 6
    assert body["status"] == "non_conforme"  # 2/6 = 33% (< 40%)


def test_record_deforestation_check_clear_raises_score(client):
    """Enregistrer un controle 'clear' fait passer la regle R6 (EUDR-01b)."""
    pid, auth = _seed_user_and_plantation(with_deforestation=False)
    before = client.get(f"/plantations/{pid}/eudr-score", headers=auth).json()["score"]
    r = client.post(f"/plantations/{pid}/deforestation-check",
                    json={"verdict": "clear", "source": "hansen_gfc"}, headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["check"]["verdict"] == "clear"
    assert body["eudr_score"]["score"] == before + 1


def test_record_deforestation_check_invalid_verdict_422(client):
    pid, auth = _seed_user_and_plantation()
    r = client.post(f"/plantations/{pid}/deforestation-check",
                    json={"verdict": "n_importe_quoi"}, headers=auth)
    assert r.status_code == 422


def test_deforestation_check_viewer_forbidden(client):
    pid, _ = _seed_user_and_plantation()
    db = TestingSessionLocal()
    try:
        viewer = User(email="viewer.defo@test.ci", password_hash="x", role="viewer",
                      cooperative_id=1)
        db.add(viewer); db.commit()
        auth = _auth(viewer)
    finally:
        db.close()
    r = client.post(f"/plantations/{pid}/deforestation-check",
                    json={"verdict": "clear"}, headers=auth)
    assert r.status_code == 403


def test_eudr_score_unknown_plantation_returns_404(client):
    pid, auth = _seed_user_and_plantation()
    r = client.get("/plantations/99999/eudr-score", headers=auth)
    assert r.status_code == 404


def test_eudr_score_requires_auth(client):
    pid, _ = _seed_user_and_plantation()
    r = client.get(f"/plantations/{pid}/eudr-score")
    assert r.status_code == 401


# ----------------------------------------------------------------------------
# /plantations/{id}/eudr-status (badge condensé)
# ----------------------------------------------------------------------------

def test_eudr_status_returns_badge(client):
    pid, auth = _seed_user_and_plantation()
    r = client.get(f"/plantations/{pid}/eudr-status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert "status" in body
    assert "badge_color" in body
    assert "rules" not in body  # version condensée


# ----------------------------------------------------------------------------
# /eudr/cooperative-summary
# ----------------------------------------------------------------------------

def test_cooperative_summary_aggregates(client):
    pid, auth = _seed_user_and_plantation()
    r = client.get("/eudr/cooperative-summary", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["conforme"] == 1
    assert body["with_polygon"] == 1
    assert body["compliance_rate_pct"] == 100.0


def test_cooperative_summary_viewer_forbidden(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="C", country="CI")
        db.add(coop); db.flush()
        viewer = User(email="viewer.eudr@test.ci", password_hash="x", role="viewer", cooperative_id=coop.id)
        db.add(viewer); db.commit()
        auth = _auth(viewer)
    finally:
        db.close()
    r = client.get("/eudr/cooperative-summary", headers=auth)
    assert r.status_code == 403


# ----------------------------------------------------------------------------
# /eudr/plantations (liste triée)
# ----------------------------------------------------------------------------

def test_list_plantations_sorted_by_risk(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop list", country="CI"); db.add(coop); db.flush()
        admin = User(email="admin.list@test.ci", password_hash="x", role="admin", cooperative_id=coop.id)
        db.add(admin); db.flush()
        # P1 : conforme (polygone + inspection récente + GPS valide)
        p1 = Plantation(name="A-conforme", owner_name="X", country="CI", latitude=5.0, longitude=-6.5,
                        hectares=1.0, cooperative_id=coop.id)
        db.add(p1); db.flush()
        db.add(PlantationBoundary(plantation_id=p1.id, geojson=VALID_POLYGON, area_hectares=1.0, points_count=5))
        db.add(Inspection(plantation_id=p1.id, type="EXTERNE", date=datetime.utcnow() - timedelta(days=10)))
        # P2 : non_conforme (rien)
        p2 = Plantation(name="B-non_conforme", owner_name="X", country="CI", latitude=20.0, longitude=10.0,
                        hectares=None, cooperative_id=coop.id)
        db.add(p2)
        db.commit()
        auth = _auth(admin)
    finally:
        db.close()
    r = client.get("/eudr/plantations?sort=risk", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # Tri par risque = non_conforme en premier
    assert body["count"] == 2
    assert body["plantations"][0]["eudr_status"] == "non_conforme"
    assert body["plantations"][1]["eudr_status"] == "conforme"


def test_list_plantations_sort_by_name(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop sort", country="CI"); db.add(coop); db.flush()
        admin = User(email="admin.sort@test.ci", password_hash="x", role="admin", cooperative_id=coop.id)
        db.add(admin); db.flush()
        for name in ("Zeta", "Alpha", "Mu"):
            db.add(Plantation(name=name, owner_name="X", country="CI", latitude=5.0, longitude=-6.5,
                              hectares=1.0, cooperative_id=coop.id))
        db.commit()
        auth = _auth(admin)
    finally:
        db.close()
    r = client.get("/eudr/plantations?sort=name", headers=auth)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["plantations"]]
    assert names == sorted(names, key=str.lower)


def test_list_plantations_scoping_other_coop(client):
    """Un admin ne voit que les plantations de sa coopérative."""
    db = TestingSessionLocal()
    try:
        coop1 = Cooperative(name="Coop 1", country="CI"); db.add(coop1); db.flush()
        coop2 = Cooperative(name="Coop 2", country="CI"); db.add(coop2); db.flush()
        admin = User(email="admin.scope@test.ci", password_hash="x", role="admin", cooperative_id=coop1.id)
        db.add(admin); db.flush()
        db.add(Plantation(name="P-coop1", owner_name="X", country="CI", latitude=5.0, longitude=-6.5,
                          hectares=1.0, cooperative_id=coop1.id))
        db.add(Plantation(name="P-coop2", owner_name="X", country="CI", latitude=5.0, longitude=-6.5,
                          hectares=1.0, cooperative_id=coop2.id))
        db.commit()
        auth = _auth(admin)
    finally:
        db.close()
    r = client.get("/eudr/plantations", headers=auth)
    body = r.json()
    assert body["count"] == 1
    assert body["plantations"][0]["name"] == "P-coop1"
