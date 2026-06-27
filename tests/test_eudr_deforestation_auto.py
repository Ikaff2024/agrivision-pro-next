"""Tests — contrôle de déforestation AUTOMATIQUE (GFW → EUDR R6).

Le provider satellite est mocké pour des verdicts déterministes (pas d'appel réseau).
"""
import json
from datetime import datetime, timedelta

from app.auth.auth_service import create_access_token
from app.db.models import (
    Cooperative, DeforestationCheck, Inspection, Plantation, PlantationBoundary, Producer, User,
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


def _seed(role="admin", with_polygon=True):
    """Parcelle conforme SAUF la déforestation (aucun contrôle) => score 4/5."""
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name=f"Coop defo-auto {role}-{with_polygon}", country="CI")
        db.add(coop); db.flush()
        user = User(email=f"{role}.defoauto.{with_polygon}@test.ci", password_hash="x",
                    role=role, cooperative_id=coop.id)
        producer = Producer(cooperative_id=coop.id, nom_complet="P", is_active=True)
        db.add_all([user, producer]); db.flush()
        p = Plantation(
            name="Parcelle defo", owner_name="Owner", country="CI", region="Soubre",
            latitude=5.785, longitude=-6.585, hectares=1.0,
            cooperative_id=coop.id, producer_id=producer.id,
        )
        db.add(p); db.flush()
        if with_polygon:
            db.add(PlantationBoundary(
                plantation_id=p.id, geojson=VALID_POLYGON, area_hectares=1.05,
                points_count=5, method="manual",
            ))
        db.add(Inspection(plantation_id=p.id, type="EXTERNE",
                          date=datetime.utcnow() - timedelta(days=30)))
        db.commit()
        return p.id, _auth(user)
    finally:
        db.close()


def _mock_signal(monkeypatch, **overrides):
    signal = {
        "loss_detected": False, "alerts_count": 0, "since": "2020-12-31",
        "scope": "parcel", "source": "global-forest-watch", "note": "n",
    }
    signal.update(overrides)
    monkeypatch.setattr(
        "app.satellite.provider.get_deforestation_for_geometry",
        lambda geometry: signal,
    )


# ── Mapping verdict ───────────────────────────────────────────────────────────

def test_auto_clear_passes_r6(client, monkeypatch):
    pid, auth = _seed()
    _mock_signal(monkeypatch, loss_detected=False, source="global-forest-watch")
    before = client.get(f"/plantations/{pid}/eudr-score", headers=auth).json()["score"]
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["check"]["verdict"] == "clear"
    assert body["check"]["source"] == "gfw"
    assert body["auto"] is True
    assert body["eudr_score"]["score"] == before + 1   # R6 bascule à PASSE


def test_auto_detected_fails_r6(client, monkeypatch):
    pid, auth = _seed()
    _mock_signal(monkeypatch, loss_detected=True, alerts_count=4, source="global-forest-watch")
    before = client.get(f"/plantations/{pid}/eudr-score", headers=auth).json()["score"]
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["check"]["verdict"] == "deforestation_detected"
    assert body["eudr_score"]["score"] == before  # R6 reste à ÉCHEC
    r6 = [x for x in body["eudr_score"]["rules"] if x["rule_id"] == "no_deforestation"][0]
    assert r6["passed"] is False


def test_auto_simulation_is_inconclusive(client, monkeypatch):
    """Sans clé GFW (source=simulation) : jamais de faux 'clear' -> inconclusive."""
    pid, auth = _seed()
    _mock_signal(monkeypatch, loss_detected=False, source="simulation")
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["check"]["verdict"] == "inconclusive"
    assert body["check"]["source"] == "gfw_simulation"
    r6 = [x for x in body["eudr_score"]["rules"] if x["rule_id"] == "no_deforestation"][0]
    assert r6["passed"] is False


# ── Garde-fous ──────────────────────────────────────────────────────────────

def test_auto_requires_polygon_400(client, monkeypatch):
    pid, auth = _seed(with_polygon=False)
    _mock_signal(monkeypatch)
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 400
    assert "polygone" in r.json()["detail"].lower()


def test_auto_persists_check(client, monkeypatch):
    pid, auth = _seed()
    _mock_signal(monkeypatch, source="global-forest-watch")
    client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    db = TestingSessionLocal()
    try:
        checks = db.query(DeforestationCheck).filter(
            DeforestationCheck.plantation_id == pid).all()
        assert len(checks) == 1
        assert checks[0].source == "gfw"
    finally:
        db.close()


def test_auto_check_updates_eudr_cache(client, monkeypatch):
    """Le contrôle auto met à jour le CACHE EUDR (colonnes eudr_*), sinon la liste
    et le résumé EUDR (qui lisent le cache) restent figés après vérif satellite/NDVI."""
    pid, auth = _seed()  # 4/5 au départ (déforestation non vérifiée)
    _mock_signal(monkeypatch, loss_detected=False, source="global-forest-watch")
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 201, r.text
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        assert p.eudr_computed_at is not None
        assert p.eudr_score == 5                    # déforestation désormais OK → 5/5
        assert p.eudr_status == "conforme"
        assert "no_deforestation" not in (p.eudr_rules_failed or [])
    finally:
        db.close()


def test_auto_viewer_forbidden_403(client, monkeypatch):
    pid, _ = _seed()
    db = TestingSessionLocal()
    try:
        viewer = User(email="viewer.defoauto@test.ci", password_hash="x", role="viewer",
                      cooperative_id=1)
        db.add(viewer); db.commit()
        auth = _auth(viewer)
    finally:
        db.close()
    _mock_signal(monkeypatch)
    r = client.post(f"/plantations/{pid}/deforestation-check/auto", headers=auth)
    assert r.status_code == 403


def test_auto_unknown_plantation_404(client, monkeypatch):
    _, auth = _seed()
    _mock_signal(monkeypatch)
    r = client.post("/plantations/999999/deforestation-check/auto", headers=auth)
    assert r.status_code == 404
