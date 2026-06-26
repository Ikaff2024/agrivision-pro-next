"""Géo-horodatage anti-fraude — intégration aux formulaires terrain (Phase A).

Vérifie que la complétion d'une visite monitoring et la création d'une visite
SSRTE enregistrent un géo-horodatage et exposent le verdict (`geo`) dans la
réponse, selon le GPS capté vs le lieu attendu (producteur / parcelle).
"""
from app.db.models import Plantation, Producer, User
from tests.conftest import TestingSessionLocal


def _coop_id(email="admin@fixture.ci"):
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().cooperative_id
    finally:
        db.close()


def _producer(coop_id, lat=5.78, lng=-6.59):
    db = TestingSessionLocal()
    try:
        prod = Producer(nom_complet="Prod Geo", cooperative_id=coop_id, is_active=True,
                        latitude=lat, longitude=lng)
        db.add(prod)
        db.commit()
        return prod.id
    finally:
        db.close()


def _plantation(coop_id, lat=5.78, lng=-6.59):
    db = TestingSessionLocal()
    try:
        prod = Producer(nom_complet="Prod Geo P", cooperative_id=coop_id, is_active=True)
        db.add(prod)
        db.flush()
        p = Plantation(name="Geo P", owner_name="O", country="CI", region="Soubre",
                       latitude=lat, longitude=lng, hectares=1.0,
                       cooperative_id=coop_id, producer_id=prod.id)
        db.add(p)
        db.commit()
        return p.id
    finally:
        db.close()


# ── SSRTE (création) ─────────────────────────────────────────────────────────
def test_ssrte_visit_geostamp_verified(client, auth_headers):
    pid = _plantation(_coop_id())
    r = client.post("/ssrte/plantation-visits", json={
        "plantation_id": pid, "interviewer_name": "Agent",
        "captured_latitude": 5.7801, "captured_longitude": -6.5899,
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["geo"]["geo_status"] == "verified"


def test_ssrte_visit_geostamp_far(client, auth_headers):
    pid = _plantation(_coop_id())
    r = client.post("/ssrte/plantation-visits", json={
        "plantation_id": pid, "interviewer_name": "Agent",
        "captured_latitude": 5.90, "captured_longitude": -6.59,   # ~2.4 km du lieu attendu
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["geo"]["geo_status"] == "far"


def test_ssrte_visit_geostamp_no_fix(client, auth_headers):
    pid = _plantation(_coop_id())
    r = client.post("/ssrte/plantation-visits", json={
        "plantation_id": pid, "interviewer_name": "Agent",   # aucun GPS capté
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["geo"]["geo_status"] == "no_fix"


# ── Monitoring (complétion) ──────────────────────────────────────────────────
def test_monitoring_complete_geostamp_verified(client, auth_headers):
    pid = _producer(_coop_id())
    cv = client.post("/monitoring/visits", json={
        "producer_id": pid, "scheduled_date": "2026-06-16",
    }, headers=auth_headers)
    assert cv.status_code == 201, cv.text
    vid = cv.json()["id"]
    r = client.post(f"/monitoring/visits/{vid}/complete", json={
        "actual_date": "2026-06-16", "checklist_data": {},
        "captured_latitude": 5.7802, "captured_longitude": -6.5901,
    }, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["geo"]["geo_status"] == "verified"


# ── Diagnostic agronomique (Phase B) ─────────────────────────────────────────
_INPUTS = {
    "country": "Côte d'Ivoire", "region": "Soubré",
    "humidity_pct": 65.0, "rainfall_mm_month": 120.0, "avg_temp_c": 24.0,
    "plantation_age_years": 15.0, "shade_tree_density_pct": 35.0,
}


def test_diagnostic_geostamp_verified(client, auth_headers):
    pid = _plantation(_coop_id())
    r = client.post(
        f"/cacao/diagnostic?plantation_id={pid}"
        f"&captured_latitude=5.7802&captured_longitude=-6.5901",
        json=_INPUTS, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["geo"]["geo_status"] == "verified"


def test_diagnostic_geostamp_no_fix(client, auth_headers):
    pid = _plantation(_coop_id())
    r = client.post(f"/cacao/diagnostic?plantation_id={pid}", json=_INPUTS, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["geo"]["geo_status"] == "no_fix"


# ── Évaluation de risque enfant (Phase B) ────────────────────────────────────
def _child(coop_id, lat=5.78, lng=-6.59):
    """Crée un producteur géolocalisé + un enfant, renvoie child_id."""
    pid = _producer(coop_id, lat=lat, lng=lng)
    db = TestingSessionLocal()
    try:
        from app.db.models_social import Child, SchoolStatus
        c = Child(producer_id=pid, first_name="Geo", last_name="Enfant",
                  date_of_birth=__import__("datetime").date(2014, 1, 1),
                  gender="F", school_status=SchoolStatus.ENROLLED, is_active=True)
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def test_risk_assessment_geostamp_verified(client, auth_headers):
    cid = _child(_coop_id())
    r = client.post("/children/assessments", json={
        "child_id": cid, "overall_risk_score": 20.0, "overall_risk_level": "low",
        "captured_latitude": 5.7801, "captured_longitude": -6.5899,
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["geo"]["geo_status"] == "verified"


def test_risk_assessment_geostamp_far(client, auth_headers):
    cid = _child(_coop_id())
    r = client.post("/children/assessments", json={
        "child_id": cid, "overall_risk_score": 20.0, "overall_risk_level": "low",
        "captured_latitude": 5.90, "captured_longitude": -6.59,
    }, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["geo"]["geo_status"] == "far"
