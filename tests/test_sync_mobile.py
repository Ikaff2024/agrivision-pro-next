"""Tests pour /sync (mobile offline) CacaoGuard.

Couvre :
- /sync/pull : snapshot complet, delta depuis date, filtrage entites, scoping technicien
- /sync/push : creation visit/complaint, completion action/visit, idempotence par op_id
- conflits : visite/action deja completee retourne status=conflict
- /sync/status : last_op, applied_count, supported types
- /sync/conflict/resolve : server_wins applique, client_wins -> 501
- gating role + 401 sans auth
"""
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Plantation, Producer, User
from app.db.models_social import (
    ActionStatus,
    MonitoringVisit,
    Priority,
    RemediationAction,
    SyncOperationLog,
    VisitStatus,
    VisitType,
)
from tests.conftest import TestingSessionLocal


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    })}


def _seed_full(client):
    """Coop + admin + tech + producer + plantation + enfant CRITICAL (auto-plan + auto-action)."""
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop Sync", country="CI")
        admin = User(email="admin.sync@test.ci", password_hash="x", role="admin", cooperative=coop)
        tech = User(email="tech.sync@test.ci", password_hash="x", role="technician", cooperative=coop)
        viewer = User(email="viewer.sync@test.ci", password_hash="x", role="viewer", cooperative=coop)
        producer = Producer(cooperative=coop, nom_complet="Producteur Sync", localite="Soubre", is_active=True)
        db.add_all([coop, admin, tech, viewer, producer])
        db.commit()
        ctx = {
            "producer_id": producer.id,
            "admin_id": admin.id,
            "tech_id": tech.id,
            "coop_id": coop.id,
            "admin": _auth(admin),
            "tech": _auth(tech),
            "viewer": _auth(viewer),
        }
    finally:
        db.close()

    # Cree un enfant CRITICAL -> plan + action automatiques
    client.post("/children", json={
        "producer_id": ctx["producer_id"],
        "first_name": "Sync",
        "last_name": "Test",
        "date_of_birth": "2014-01-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete"],
    }, headers=ctx["admin"])
    return ctx


# ----------------------------------------------------------------------------
# Auth & gating
# ----------------------------------------------------------------------------

def test_pull_requires_auth(client):
    _seed_full(client)
    r = client.post("/sync/pull", json={})
    assert r.status_code == 401


def test_push_requires_auth(client):
    r = client.post("/sync/push", json={"operations": []})
    assert r.status_code == 401


def test_viewer_role_forbidden(client):
    ctx = _seed_full(client)
    r = client.post("/sync/pull", json={}, headers=ctx["viewer"])
    assert r.status_code == 403


# ----------------------------------------------------------------------------
# Pull
# ----------------------------------------------------------------------------

def test_pull_snapshot_returns_all_entities(client):
    ctx = _seed_full(client)
    r = client.post("/sync/pull", json={}, headers=ctx["admin"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert "server_time" in body
    assert body["counts"]["producers"] >= 1
    assert body["counts"]["children"] >= 1
    assert body["counts"]["remediation_plans"] >= 1
    assert body["counts"]["remediation_actions"] >= 1


def test_pull_filters_by_entities(client):
    ctx = _seed_full(client)
    r = client.post(
        "/sync/pull",
        json={"entities": ["producers", "children"]},
        headers=ctx["admin"],
    )
    body = r.json()
    assert "producers" in body
    assert "children" in body
    assert "monitoring_visits" not in body
    assert "alerts" not in body


def test_pull_unknown_entity_returns_400(client):
    ctx = _seed_full(client)
    r = client.post(
        "/sync/pull",
        json={"entities": ["bogus"]},
        headers=ctx["admin"],
    )
    assert r.status_code == 400


def test_pull_delta_excludes_old_records(client):
    ctx = _seed_full(client)
    # Date future -> rien de plus recent
    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    r = client.post(
        "/sync/pull",
        json={"last_sync_at": future, "entities": ["children"]},
        headers=ctx["admin"],
    )
    assert r.status_code == 200
    assert r.json()["counts"]["children"] == 0


# ----------------------------------------------------------------------------
# Push : create_visit
# ----------------------------------------------------------------------------

def test_push_create_visit_succeeds(client):
    ctx = _seed_full(client)
    op_id = str(uuid.uuid4())
    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": op_id,
            "op_type": "create_visit",
            "payload": {
                "producer_id": ctx["producer_id"],
                "scheduled_date": str(date.today()),
                "visit_type": "routine",
                "lead_assessor_id": ctx["tech_id"],
                "observations": "Visite terrain OK.",
            },
        }],
    }, headers=ctx["tech"])
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["server_id"] is not None


def test_push_idempotent_returns_duplicate(client):
    ctx = _seed_full(client)
    op_id = str(uuid.uuid4())
    body = {
        "operations": [{
            "op_id": op_id,
            "op_type": "create_visit",
            "payload": {
                "producer_id": ctx["producer_id"],
                "scheduled_date": str(date.today()),
            },
        }],
    }
    r1 = client.post("/sync/push", json=body, headers=ctx["tech"])
    first_server_id = r1.json()["results"][0]["server_id"]

    r2 = client.post("/sync/push", json=body, headers=ctx["tech"])
    assert r2.status_code == 200
    result = r2.json()["results"][0]
    assert result["status"] == "duplicate"
    assert result["server_id"] == first_server_id

    # Une seule visite en DB
    db = TestingSessionLocal()
    try:
        visits = db.query(MonitoringVisit).filter(
            MonitoringVisit.producer_id == ctx["producer_id"]
        ).all()
        # +1 visite (potentiellement aucune auto-creee a la base)
        assert len(visits) == 1
    finally:
        db.close()


def test_push_invalid_op_type_returns_error(client):
    ctx = _seed_full(client)
    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "bogus_op",
            "payload": {},
        }],
    }, headers=ctx["tech"])
    assert r.status_code == 200
    assert r.json()["results"][0]["status"] == "error"


def test_push_invalid_producer_returns_error(client):
    ctx = _seed_full(client)
    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "create_visit",
            "payload": {
                "producer_id": 99999,
                "scheduled_date": str(date.today()),
            },
        }],
    }, headers=ctx["tech"])
    assert r.json()["results"][0]["status"] == "error"
    assert "Producteur" in r.json()["results"][0]["error"]


# ----------------------------------------------------------------------------
# Push : complete_visit + conflit
# ----------------------------------------------------------------------------

def test_push_complete_visit_succeeds(client):
    ctx = _seed_full(client)
    # Cree une visite directement
    db = TestingSessionLocal()
    try:
        v = MonitoringVisit(
            producer_id=ctx["producer_id"],
            scheduled_date=date.today(),
            visit_type=VisitType.ROUTINE,
            priority=Priority.MEDIUM,
            lead_assessor_id=ctx["tech_id"],
            status=VisitStatus.SCHEDULED,
        )
        db.add(v)
        db.commit()
        visit_id = v.id
    finally:
        db.close()

    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "complete_visit",
            "payload": {
                "visit_id": visit_id,
                "observations": "Termine en zone reseau.",
            },
        }],
    }, headers=ctx["tech"])
    assert r.json()["results"][0]["status"] == "success"


def test_push_complete_already_completed_visit_returns_conflict(client):
    ctx = _seed_full(client)
    db = TestingSessionLocal()
    try:
        v = MonitoringVisit(
            producer_id=ctx["producer_id"],
            scheduled_date=date.today(),
            visit_type=VisitType.ROUTINE,
            priority=Priority.MEDIUM,
            lead_assessor_id=ctx["tech_id"],
            status=VisitStatus.COMPLETED,  # deja faite
            actual_date=date.today(),
        )
        db.add(v)
        db.commit()
        visit_id = v.id
    finally:
        db.close()

    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "complete_visit",
            "payload": {"visit_id": visit_id},
        }],
    }, headers=ctx["tech"])
    result = r.json()["results"][0]
    assert result["status"] == "conflict"
    assert "deja" in result["error"].lower()


# ----------------------------------------------------------------------------
# Push : create_complaint
# ----------------------------------------------------------------------------

def test_push_create_complaint_succeeds(client):
    ctx = _seed_full(client)
    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "create_complaint",
            "payload": {
                "complaint_type": "child_labor",
                "severity": "high",
                "description": "Cas observe sur le terrain ce matin tot.",
                "producer_id": ctx["producer_id"],
                "source": "field_agent",
            },
        }],
    }, headers=ctx["tech"])
    result = r.json()["results"][0]
    assert result["status"] == "success"
    assert "reference" in result["server_snapshot"]


def test_push_create_complaint_short_description_rejected(client):
    ctx = _seed_full(client)
    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "create_complaint",
            "payload": {
                "complaint_type": "other",
                "description": "court",  # < 10 char
            },
        }],
    }, headers=ctx["tech"])
    assert r.json()["results"][0]["status"] == "error"


# ----------------------------------------------------------------------------
# Push : complete_action
# ----------------------------------------------------------------------------

def test_push_complete_action_requires_evidence(client):
    ctx = _seed_full(client)
    db = TestingSessionLocal()
    try:
        action = db.query(RemediationAction).first()
        action_id = action.id
    finally:
        db.close()

    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "complete_action",
            "payload": {"action_id": action_id, "evidence": {}},
        }],
    }, headers=ctx["tech"])
    assert r.json()["results"][0]["status"] == "error"


def test_push_complete_action_succeeds_with_evidence(client):
    ctx = _seed_full(client)
    db = TestingSessionLocal()
    try:
        action = db.query(RemediationAction).first()
        action_id = action.id
    finally:
        db.close()

    r = client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "complete_action",
            "payload": {
                "action_id": action_id,
                "evidence": {"photos": ["field.jpg"]},
            },
        }],
    }, headers=ctx["tech"])
    assert r.json()["results"][0]["status"] == "success"

    db = TestingSessionLocal()
    try:
        action = db.query(RemediationAction).filter(RemediationAction.id == action_id).first()
        assert action.status == ActionStatus.COMPLETED
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------------

def test_status_reflects_last_op(client):
    ctx = _seed_full(client)
    r0 = client.get("/sync/status", headers=ctx["tech"])
    assert r0.json()["applied_ops_count"] == 0
    assert r0.json()["last_op_at"] is None

    client.post("/sync/push", json={
        "operations": [{
            "op_id": str(uuid.uuid4()),
            "op_type": "create_visit",
            "payload": {
                "producer_id": ctx["producer_id"],
                "scheduled_date": str(date.today()),
            },
        }],
    }, headers=ctx["tech"])

    r1 = client.get("/sync/status", headers=ctx["tech"])
    body = r1.json()
    assert body["applied_ops_count"] == 1
    assert body["last_op_at"] is not None
    assert "create_visit" in body["supported_op_types"]


# ----------------------------------------------------------------------------
# Conflict resolve
# ----------------------------------------------------------------------------

def test_conflict_resolve_server_wins(client):
    ctx = _seed_full(client)
    # Force un conflit : completer une visite deja completee
    db = TestingSessionLocal()
    try:
        v = MonitoringVisit(
            producer_id=ctx["producer_id"],
            scheduled_date=date.today(),
            visit_type=VisitType.ROUTINE,
            priority=Priority.MEDIUM,
            lead_assessor_id=ctx["tech_id"],
            status=VisitStatus.COMPLETED,
            actual_date=date.today(),
        )
        db.add(v)
        db.commit()
        visit_id = v.id
    finally:
        db.close()

    op_id = str(uuid.uuid4())
    client.post("/sync/push", json={
        "operations": [{
            "op_id": op_id,
            "op_type": "complete_visit",
            "payload": {"visit_id": visit_id},
        }],
    }, headers=ctx["tech"])

    r = client.post("/sync/conflict/resolve", json={
        "op_id": op_id,
        "resolution": "server_wins",
    }, headers=ctx["tech"])
    assert r.status_code == 200
    assert r.json()["applied"] is True


def test_conflict_resolve_client_wins_not_implemented(client):
    ctx = _seed_full(client)
    # Cree un log de conflit factice
    db = TestingSessionLocal()
    try:
        db.add(SyncOperationLog(
            op_id="conflict-test-id",
            user_id=ctx["tech_id"],
            op_type="complete_visit",
            entity_type="monitoring_visits",
            status="conflict",
            error_message="test",
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/sync/conflict/resolve", json={
        "op_id": "conflict-test-id",
        "resolution": "client_wins",
    }, headers=ctx["tech"])
    assert r.status_code == 501


def test_conflict_resolve_unknown_op_returns_404(client):
    ctx = _seed_full(client)
    r = client.post("/sync/conflict/resolve", json={
        "op_id": "does-not-exist",
        "resolution": "server_wins",
    }, headers=ctx["tech"])
    assert r.status_code == 404
