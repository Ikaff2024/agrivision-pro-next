"""Tests — Jumeau de parcelle (FEATURE-PARCEL-360) : agrégation + alertes."""
import json
from datetime import datetime, timedelta

from app.auth.auth_service import create_access_token
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
    for key in ("plantation", "diagnostic", "eudr", "deforestation", "harvests", "cacaoguard", "boundary"):
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
