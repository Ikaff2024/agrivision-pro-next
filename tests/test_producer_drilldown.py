"""Tests pour les endpoints producer drill-down CacaoGuard."""
from datetime import date

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Producer, User
from app.db.models_social import (
    BlockReason,
    BlockStatus,
    Complaint,
    ComplaintSeverity,
    ComplaintStatus,
    ComplaintType,
    RiskLevel,
    SchoolStatus,
    TraceabilityBlock,
    WorkFrequency,
)
from tests.conftest import TestingSessionLocal


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    })}


def _seed(client):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop DD", country="CI")
        admin = User(email="admin.dd@test.ci", password_hash="x", role="admin", cooperative=coop)
        tech = User(email="tech.dd@test.ci", password_hash="x", role="technician", cooperative=coop)
        p1 = Producer(cooperative=coop, nom_complet="Producteur Un", localite="Soubre", is_active=True)
        p2 = Producer(cooperative=coop, nom_complet="Producteur Deux", localite="Soubre", is_active=True)
        db.add_all([coop, admin, tech, p1, p2])
        db.commit()
        ctx = {
            "p1": p1.id,
            "p2": p2.id,
            "admin": _auth(admin),
            "tech": _auth(tech),
            "admin_id": admin.id,
        }
    finally:
        db.close()

    # 2 enfants pour p1 — un CRITICAL (declenche plan + block), un sain
    client.post("/children", json={
        "producer_id": ctx["p1"],
        "first_name": "Awa",
        "last_name": "Critical",
        "date_of_birth": "2014-01-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete", "pesticide"],
    })
    client.post("/children", json={
        "producer_id": ctx["p1"],
        "first_name": "Ali",
        "last_name": "Safe",
        "date_of_birth": "2013-06-01",
        "gender": "M",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    })
    # 1 enfant pour p2 — pour verifier l'isolation par producteur
    client.post("/children", json={
        "producer_id": ctx["p2"],
        "first_name": "Yao",
        "last_name": "Autre",
        "date_of_birth": "2015-03-01",
        "gender": "M",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    })

    # Une plainte sur p1 (seed direct DB pour ne pas dependre du module CG-1.1)
    db = TestingSessionLocal()
    try:
        db.add(Complaint(
            complaint_reference="CMP-TEST-001",
            source="test",
            complaint_type=ComplaintType.CHILD_LABOR,
            severity=ComplaintSeverity.HIGH,
            description="Signalement terrain a verifier.",
            producer_id=ctx["p1"],
            status=ComplaintStatus.RECEIVED,
        ))
        db.commit()
    finally:
        db.close()

    return ctx


# ----------------------------------------------------------------------------
# /producers/{id}/children
# ----------------------------------------------------------------------------

def test_list_children_returns_only_producer_children(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p1']}/children", headers=ctx["admin"])
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2

    r2 = client.get(f"/producers/{ctx['p2']}/children", headers=ctx["admin"])
    assert len(r2.json()) == 1


def test_children_redacted_for_technician(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p1']}/children", headers=ctx["tech"])
    assert r.status_code == 200
    for child in r.json():
        assert child["privacy_redacted"] is True
        assert child["last_name"] == "Confidentiel"


def test_children_unknown_producer_returns_404(client):
    _seed(client)
    r = client.get("/producers/99999/children")
    assert r.status_code == 404


# ----------------------------------------------------------------------------
# /producers/{id}/assessments
# ----------------------------------------------------------------------------

def test_list_assessments_filters_by_producer(client):
    ctx = _seed(client)
    # Cree une evaluation sur l'enfant critical de p1
    children = client.get(f"/producers/{ctx['p1']}/children", headers=ctx["admin"]).json()
    critical_child = next(c for c in children if c["risk_level"] == "critical")
    client.post("/children/assessments", json={
        "child_id": critical_child["id"],
        "assessment_type": "follow_up",
        "overall_risk_score": 75,
        "overall_risk_level": "high",
        "risk_factors": {"work": 30},
    }, headers=ctx["admin"])

    r = client.get(f"/producers/{ctx['p1']}/assessments", headers=ctx["admin"])
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["overall_risk_level"] == "high"


# ----------------------------------------------------------------------------
# /producers/{id}/remediation-plans
# ----------------------------------------------------------------------------

def test_list_remediation_plans_returns_only_producer_plans(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p1']}/remediation-plans", headers=ctx["admin"])
    assert r.status_code == 200
    # Au moins le plan auto-cree pour l'enfant CRITICAL
    assert len(r.json()) >= 1
    for p in r.json():
        assert p["producer_id"] == ctx["p1"]


def test_remediation_plans_technician_forbidden(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p1']}/remediation-plans", headers=ctx["tech"])
    assert r.status_code == 403


# ----------------------------------------------------------------------------
# /producers/{id}/complaints
# ----------------------------------------------------------------------------

def test_list_producer_complaints(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p1']}/complaints", headers=ctx["admin"])
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["severity"] == "high"


# ----------------------------------------------------------------------------
# /producers/{id}/traceability-status
# ----------------------------------------------------------------------------

def test_traceability_status_with_active_block(client):
    ctx = _seed(client)
    # L'enfant CRITICAL declenche un block automatique
    r = client.get(f"/producers/{ctx['p1']}/traceability-status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_blocked"] is True
    assert body["active_blocks_count"] >= 1


def test_traceability_status_clean_producer(client):
    ctx = _seed(client)
    r = client.get(f"/producers/{ctx['p2']}/traceability-status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_blocked"] is False
    assert body["active_blocks_count"] == 0


# ----------------------------------------------------------------------------
# /producers/{id}/calculate-risk
# ----------------------------------------------------------------------------

def test_calculate_risk_aggregates_children(client):
    ctx = _seed(client)
    r = client.post(f"/producers/{ctx['p1']}/calculate-risk", headers=ctx["admin"])
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["children_count"] == 2
    assert body["aggregate_risk_level"] == "critical"  # le pire des 2 enfants
    assert body["children_at_high_or_critical"] >= 1
    assert body["active_traceability_blocks"] >= 1
    assert body["open_complaints"] == 1
    assert body["requires_intervention"] is True


def test_calculate_risk_clean_producer(client):
    ctx = _seed(client)
    r = client.post(f"/producers/{ctx['p2']}/calculate-risk", headers=ctx["admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["children_count"] == 1
    assert body["active_traceability_blocks"] == 0
    assert body["open_complaints"] == 0
    assert body["requires_intervention"] is False


def test_calculate_risk_role_gating(client):
    ctx = _seed(client)
    # Test seulement avec un user authentifie non autorise (viewer-like)
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).first()
        viewer = User(email="viewer.dd@test.ci", password_hash="x", role="viewer", cooperative=coop)
        db.add(viewer)
        db.commit()
        viewer_auth = _auth(viewer)
    finally:
        db.close()
    r = client.post(f"/producers/{ctx['p1']}/calculate-risk", headers=viewer_auth)
    assert r.status_code == 403


def test_producer_drilldown_is_cooperative_scoped(client):
    """Cloisonnement : l'admin d'une autre coop ne voit ni le producteur ni ses données."""
    ctx = _seed(client)  # p1 dans 'Coop DD'
    db = TestingSessionLocal()
    try:
        other = Cooperative(name="Coop DD Etrangere", country="CI")
        intruder = User(email="intrus.dd@test.ci", password_hash="x", role="admin", cooperative=other)
        db.add_all([other, intruder])
        db.commit()
        hdr = _auth(intruder)
    finally:
        db.close()

    p1 = ctx["p1"]
    for path in (
        f"/producers/{p1}",
        f"/producers/{p1}/children",
        f"/producers/{p1}/assessments",
        f"/producers/{p1}/remediation-plans",
        f"/producers/{p1}/complaints",
    ):
        assert client.get(path, headers=hdr).status_code == 404, path
    # La liste des producteurs de l'intrus est vide.
    assert client.get("/producers", headers=hdr).json() == []
