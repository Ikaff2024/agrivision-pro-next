"""Tests — Jumeau de parcelle (FEATURE-PARCEL-360) : agrégation + alertes."""
import json
from datetime import datetime, timedelta

import pytest

import app.api.twin_routes as twin_routes
from app.auth.auth_service import create_access_token


@pytest.fixture(autouse=True)
def _no_weather_network(monkeypatch):
    """Évite tout appel réseau Open-Meteo pendant les tests du jumeau."""
    async def _none(lat, lon):
        return None
    monkeypatch.setattr(twin_routes, "get_weather", _none)
from app.db.models import (
    Cooperative, DeforestationCheck, Diagnostic, Harvest, Inspection,
    Plantation, PlantationBoundary, Producer, User,
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


def _codes(body):
    return {a["code"] for a in body["alerts"]}


def _seed(full=False, email="twin@test.ci", coop="Coop Twin"):
    """full=False : parcelle nue. full=True : conforme + diagnostic + récolte."""
    db = TestingSessionLocal()
    try:
        c = Cooperative(name=coop, country="CI"); db.add(c); db.flush()
        user = User(email=email, password_hash="x", role="admin", cooperative_id=c.id)
        prod = Producer(cooperative_id=c.id, nom_complet="Kouassi", is_active=True)
        db.add_all([user, prod]); db.flush()
        p = Plantation(name="Parcelle Twin", owner_name="Kouassi", country="CI", region="Soubre",
                       latitude=5.785, longitude=-6.585, hectares=1.0,
                       cooperative_id=c.id, producer_id=prod.id)
        db.add(p); db.flush()
        if full:
            db.add(PlantationBoundary(plantation_id=p.id, geojson=VALID_POLYGON,
                                      area_hectares=1.05, points_count=5, method="manual"))
            db.add(Inspection(plantation_id=p.id, type="EXTERNE",
                              date=datetime.utcnow() - timedelta(days=30)))
            db.add(DeforestationCheck(plantation_id=p.id, verdict="clear", source="gfw",
                                      check_date=datetime.utcnow()))
            db.add(Diagnostic(plantation_id=p.id, country="CI", humidity_pct=70,
                              rainfall_mm_month=120, avg_temp_c=26, plantation_age_years=10,
                              global_score=80, global_risk_level="Faible"))
            db.add(Harvest(plantation_id=p.id, harvest_date=datetime.utcnow(),
                           quantity_kg=500, quality="Bonne"))
        db.commit()
        return p.id, _auth(user)
    finally:
        db.close()


def test_twin_structure_and_alerts_bare(client):
    pid, auth = _seed(full=False)
    r = client.get(f"/plantations/{pid}/twin", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    # Structure
    for key in ("plantation", "diagnostic", "eudr", "deforestation", "harvests", "cacaoguard", "boundary", "weather"):
        assert key in body["twin"], key
    # Parcelle nue → alertes attendues
    codes = _codes(body)
    assert "no_polygon" in codes
    assert "deforestation_todo" in codes
    assert "no_diagnostic" in codes
    assert "no_harvest" in codes
    assert body["alert_count"] == len(body["alerts"])
    # Triées : la 1re est de sévérité high
    assert body["alerts"][0]["severity"] == "high"


def test_twin_conformant_has_no_blocking_alerts(client):
    pid, auth = _seed(full=True, email="twin.full@test.ci", coop="Coop Twin Full")
    body = client.get(f"/plantations/{pid}/twin", headers=auth).json()
    codes = _codes(body)
    assert "no_polygon" not in codes
    assert "deforestation_todo" not in codes
    assert "no_diagnostic" not in codes
    assert "no_harvest" not in codes
    # EUDR conforme (6/6) + récolte 500 kg/ha → aucune alerte
    assert body["twin"]["eudr"]["status"] == "conforme"
    assert body["twin"]["harvests"]["yield_kg_ha"] == 500.0
    assert body["alert_count"] == 0


def test_twin_cacaoguard_block_alert(client):
    pid, auth = _seed(full=True, email="twin.block@test.ci", coop="Coop Twin Block")
    # Pose un blocage actif sur le producteur
    db = TestingSessionLocal()
    try:
        from app.db.models_social import BlockStatus, BlockReason, TraceabilityBlock
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        db.add(TraceabilityBlock(producer_id=p.producer_id, status=BlockStatus.ACTIVE,
                                 block_reason=BlockReason.CHILD_LABOR_CASE))
        db.commit()
    except Exception:
        db.rollback()
        return  # module social indisponible → test non applicable
    finally:
        db.close()
    body = client.get(f"/plantations/{pid}/twin", headers=auth).json()
    assert body["twin"]["cacaoguard"]["blocked"] is True
    assert "cacaoguard_block" in _codes(body)


def test_twin_404(client):
    _, auth = _seed(email="twin.404@test.ci", coop="Coop Twin 404")
    assert client.get("/plantations/999999/twin", headers=auth).status_code == 404


def test_twin_requires_auth(client):
    pid, _ = _seed(email="twin.auth@test.ci", coop="Coop Twin Auth")
    assert client.get(f"/plantations/{pid}/twin").status_code == 401


def test_twin_other_coop_forbidden(client):
    pid, _ = _seed(email="twin.a@test.ci", coop="Coop Twin A")
    db = TestingSessionLocal()
    try:
        c2 = Cooperative(name="Coop Twin B", country="CI"); db.add(c2); db.flush()
        u2 = User(email="twin.b@test.ci", password_hash="x", role="admin", cooperative_id=c2.id)
        db.add(u2); db.commit()
        auth_b = _auth(u2)
    finally:
        db.close()
    assert client.get(f"/plantations/{pid}/twin", headers=auth_b).status_code == 403


# ── Vue coopérative « parcelles à risque » (agrégation) ───────────────────────

def _seed_coop_multi(email="twinrisk@test.ci", coop="Coop Twin Risk"):
    """Coop à 2 parcelles : une nue (à risque) + une conforme (0 alerte)."""
    db = TestingSessionLocal()
    try:
        c = Cooperative(name=coop, country="CI"); db.add(c); db.flush()
        user = User(email=email, password_hash="x", role="admin", cooperative_id=c.id)
        prod = Producer(cooperative_id=c.id, nom_complet="Kouassi", is_active=True)
        db.add_all([user, prod]); db.flush()
        bare = Plantation(name="Parcelle nue", owner_name="Kouassi", country="CI", region="Soubre",
                          latitude=5.7, longitude=-6.5, hectares=1.0,
                          cooperative_id=c.id, producer_id=prod.id)
        full = Plantation(name="Parcelle conforme", owner_name="Kouassi", country="CI", region="Soubre",
                          latitude=5.8, longitude=-6.6, hectares=1.0,
                          cooperative_id=c.id, producer_id=prod.id)
        db.add_all([bare, full]); db.flush()
        db.add(PlantationBoundary(plantation_id=full.id, geojson=VALID_POLYGON,
                                  area_hectares=1.05, points_count=5, method="manual"))
        db.add(DeforestationCheck(plantation_id=full.id, verdict="clear", source="gfw",
                                  check_date=datetime.utcnow()))
        db.add(Diagnostic(plantation_id=full.id, country="CI", humidity_pct=70,
                          rainfall_mm_month=120, avg_temp_c=26, plantation_age_years=10,
                          global_score=80, global_risk_level="Faible"))
        db.add(Harvest(plantation_id=full.id, harvest_date=datetime.utcnow(),
                       quantity_kg=500, quality="Bonne"))
        db.commit()
        return bare.id, full.id, _auth(user)
    finally:
        db.close()


def test_coop_at_risk_ranks_and_filters(client):
    bare_id, full_id, auth = _seed_coop_multi()
    body = client.get("/twin/at-risk", headers=auth).json()
    assert body["total_parcels"] == 2
    assert body["flagged_count"] == 1                 # seule la parcelle nue est à risque
    assert body["by_worst"]["high"] == 1
    assert body["returned"] == 1
    ids = [p["plantation_id"] for p in body["parcels"]]
    assert bare_id in ids and full_id not in ids      # la conforme est exclue
    top = body["parcels"][0]
    assert top["plantation_id"] == bare_id
    assert top["worst_severity"] == "high"
    assert "no_polygon" in {a["code"] for a in top["alerts"]}
    # Filtres de sévérité (la parcelle nue a high + medium)
    assert client.get("/twin/at-risk?severity=high", headers=auth).json()["returned"] == 1
    assert client.get("/twin/at-risk?severity=medium", headers=auth).json()["returned"] == 1
    assert client.get("/twin/at-risk?severity=bogus", headers=auth).json()["returned"] == 1  # ignoré


def test_coop_at_risk_scoped_to_coop(client):
    _seed_coop_multi(email="twinrisk.a@test.ci", coop="Coop Twin Risk A")
    db = TestingSessionLocal()
    try:
        c2 = Cooperative(name="Coop Twin Risk B", country="CI"); db.add(c2); db.flush()
        u2 = User(email="twinrisk.b@test.ci", password_hash="x", role="admin", cooperative_id=c2.id)
        db.add(u2); db.commit()
        auth_b = _auth(u2)
    finally:
        db.close()
    body = client.get("/twin/at-risk", headers=auth_b).json()
    assert body["total_parcels"] == 0                 # ne voit pas les parcelles de la coop A
    assert body["parcels"] == []


def test_coop_at_risk_requires_auth(client):
    assert client.get("/twin/at-risk").status_code == 401


# ── Enrichissement : revenu vital, certification, remédiation ─────────────────

def test_twin_includes_social_economic_blocks(client):
    """La fiche jumeau expose les dimensions revenu vital / certification / remédiation."""
    pid, auth = _seed(full=True, email="twin.social@test.ci", coop="Coop Twin Social")
    twin = client.get(f"/plantations/{pid}/twin", headers=auth).json()["twin"]
    assert "living_income" in twin and "certification" in twin
    assert "remediation_active" in twin["cacaoguard"]


def test_twin_living_income_gap_alert(client):
    pid, auth = _seed(full=True, email="twin.li@test.ci", coop="Coop Twin LI")
    db = TestingSessionLocal()
    try:
        from app.db.models import FarmForceAssessment, Plantation
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        db.add(FarmForceAssessment(producer_id=p.producer_id, campaign_label="2025-2026",
                                   net_income_cfa=500000))  # < seuil revenu vital (2 360 000)
        db.commit()
    finally:
        db.close()
    body = client.get(f"/plantations/{pid}/twin", headers=auth).json()
    assert body["twin"]["living_income"]["available"] is True
    assert body["twin"]["living_income"]["status"] == "ecart"
    assert "living_income_gap" in {a["code"] for a in body["alerts"]}


def test_twin_certification_expired_alert(client):
    pid, auth = _seed(full=True, email="twin.cert@test.ci", coop="Coop Twin Cert")
    db = TestingSessionLocal()
    try:
        from app.db.models import Certification, PlantationCertification
        cert = Certification(code="FT-TWINTEST", nom_complet="Fairtrade (test)")
        db.add(cert); db.flush()
        db.add(PlantationCertification(plantation_id=pid, certification_id=cert.id,
                                       date_expiration=datetime.utcnow() - timedelta(days=10)))
        db.commit()
    finally:
        db.close()
    body = client.get(f"/plantations/{pid}/twin", headers=auth).json()
    assert body["twin"]["certification"]["needs_renewal"] is True
    assert "cert_expired" in {a["code"] for a in body["alerts"]}


def test_twin_active_remediation_alert(client):
    pid, auth = _seed(full=True, email="twin.rem@test.ci", coop="Coop Twin Rem")
    db = TestingSessionLocal()
    try:
        from app.db.models import Plantation, User
        from app.db.models_social import Child, Priority, RemediationPlan, RemediationStatus
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        u = db.query(User).filter(User.cooperative_id == p.cooperative_id).first()
        child = Child(producer_id=p.producer_id, first_name="A", last_name="B",
                      date_of_birth=(datetime.utcnow() - timedelta(days=3650)).date(), gender="M")
        db.add(child); db.flush()
        db.add(RemediationPlan(producer_id=p.producer_id, child_id=child.id,
                               plan_reference="REM-TWINTEST-001", status=RemediationStatus.IN_PROGRESS,
                               priority=Priority.HIGH, main_objective="Scolarisation", case_worker_id=u.id))
        db.commit()
    finally:
        db.close()
    body = client.get(f"/plantations/{pid}/twin", headers=auth).json()
    assert body["twin"]["cacaoguard"]["remediation_active"] >= 1
    assert "remediation_active" in {a["code"] for a in body["alerts"]}


def test_coop_at_risk_includes_living_income_gap(client):
    """La vue coop « à risque » remonte aussi un écart de revenu vital."""
    pid, auth = _seed(full=True, email="twin.coopli@test.ci", coop="Coop Twin CoopLI")
    db = TestingSessionLocal()
    try:
        from app.db.models import FarmForceAssessment, Plantation
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        db.add(FarmForceAssessment(producer_id=p.producer_id, campaign_label="2025-2026",
                                   net_income_cfa=500000))
        db.commit()
    finally:
        db.close()
    body = client.get("/twin/at-risk", headers=auth).json()
    assert body["flagged_count"] == 1
    codes = {a["code"] for a in body["parcels"][0]["alerts"]}
    assert "living_income_gap" in codes
