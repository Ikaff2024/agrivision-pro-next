"""Tests pour le workflow de remediation CacaoGuard.

Couvre :
- transitions de plan (approve / complete / escalate) avec gating de statut
- refus de cloture tant qu'il reste des actions PENDING/IN_PROGRESS
- CRUD RemediationAction (ajout, maj, suppression, completion avec preuves)
- gating de role (admin/agronomist pour transitions, technician autorise sur completion action)
"""
from datetime import date, timedelta

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Producer, User
from app.db.models_social import (
    ActionStatus,
    ActionType,
    Alert,
    AlertStatus,
    Child,
    Priority,
    RemediationAction,
    RemediationPlan,
    RemediationStatus,
    SchoolStatus,
    WorkFrequency,
)
from tests.conftest import TestingSessionLocal


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    })}


def _seed_full(client):
    """Cree coop + admin + technician + producer + enfant CRITICAL -> auto-plan."""
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop Workflow", country="CI")
        admin = User(email="admin.wf@test.ci", password_hash="x", role="admin", cooperative=coop)
        tech = User(email="tech.wf@test.ci", password_hash="x", role="technician", cooperative=coop)
        producer = Producer(cooperative=coop, nom_complet="Producteur WF", localite="Soubre", is_active=True)
        db.add_all([coop, admin, tech, producer])
        db.commit()
        ctx = {
            "producer_id": producer.id,
            "admin_id": admin.id,
            "admin": _auth(admin),
            "tech": _auth(tech),
        }
    finally:
        db.close()

    # Cree un enfant CRITICAL pour declencher l'auto-plan
    r = client.post("/children", json={
        "producer_id": ctx["producer_id"],
        "first_name": "Workflow",
        "last_name": "Enfant",
        "date_of_birth": "2014-01-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete", "pesticide"],
    })
    assert r.status_code == 201, r.text

    db = TestingSessionLocal()
    try:
        plan = db.query(RemediationPlan).first()
        ctx["plan_id"] = plan.id
        ctx["plan_ref"] = plan.plan_reference
        ctx["initial_status"] = plan.status
    finally:
        db.close()
    return ctx


def _make_plan_draft(plan_id: int):
    db = TestingSessionLocal()
    try:
        plan = db.query(RemediationPlan).filter(RemediationPlan.id == plan_id).first()
        plan.status = RemediationStatus.DRAFT
        db.commit()
    finally:
        db.close()


def _force_actions_completed(plan_id: int):
    db = TestingSessionLocal()
    try:
        actions = db.query(RemediationAction).filter(
            RemediationAction.remediation_plan_id == plan_id
        ).all()
        for a in actions:
            a.status = ActionStatus.COMPLETED
            a.completed_date = date.today()
            a.evidence = {"documents": ["report.pdf"]}
        db.commit()
    finally:
        db.close()


# ----------------------------------------------------------------------------
# approve
# ----------------------------------------------------------------------------

def test_approve_plan_from_draft_transitions_to_in_progress(client):
    ctx = _seed_full(client)
    _make_plan_draft(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/approve",
        json={"approval_comments": "Plan revu et valide par superviseur."},
        headers=ctx["admin"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_progress"

    db = TestingSessionLocal()
    try:
        plan = db.query(RemediationPlan).filter(RemediationPlan.id == ctx["plan_id"]).first()
        assert plan.approved_by == ctx["admin_id"]
        assert plan.approved_at is not None
        assert "valide" in plan.approval_comments
    finally:
        db.close()


def test_approve_plan_from_invalid_status_returns_409(client):
    ctx = _seed_full(client)
    # Plan deja en IN_PROGRESS (auto-creation)
    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/approve",
        json={"approval_comments": "tentative double approbation"},
        headers=ctx["admin"],
    )
    assert r.status_code == 409
    assert "in_progress" in r.json()["detail"]


def test_approve_plan_with_invalid_supervisor_returns_404(client):
    ctx = _seed_full(client)
    _make_plan_draft(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/approve",
        json={"approval_comments": "test superviseur inexistant", "supervisor_id": 99999},
        headers=ctx["admin"],
    )
    assert r.status_code == 404


def test_approve_plan_requires_admin_or_agronomist(client):
    ctx = _seed_full(client)
    _make_plan_draft(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/approve",
        json={"approval_comments": "tentative non autorisee"},
        headers=ctx["tech"],
    )
    assert r.status_code == 403


# ----------------------------------------------------------------------------
# complete
# ----------------------------------------------------------------------------

def test_complete_plan_requires_all_actions_done(client):
    ctx = _seed_full(client)
    # Actions PENDING par defaut
    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={
            "outcome": "successful",
            "outcome_description": "Tentative de cloture sans terminer les actions.",
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 409
    assert "action" in r.json()["detail"].lower()


def test_complete_plan_succeeds_after_all_actions_done(client):
    ctx = _seed_full(client)
    _force_actions_completed(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={
            "outcome": "successful",
            "outcome_description": "Enfant inscrit a l'ecole, suivi mensuel actif.",
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["outcome"] == "successful"

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(
            Alert.source_entity == "remediation_plans",
            Alert.source_id == ctx["plan_id"],
        ).first()
        assert alert.status == AlertStatus.RESOLVED
    finally:
        db.close()


def test_complete_plan_with_close_after_transitions_to_closed(client):
    ctx = _seed_full(client)
    _force_actions_completed(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={
            "outcome": "partial_success",
            "outcome_description": "Cas partiellement traite, audit final OK.",
            "close_after": True,
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_complete_invalid_outcome_rejected(client):
    ctx = _seed_full(client)
    _force_actions_completed(ctx["plan_id"])

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={"outcome": "amazing", "outcome_description": "outcome inconnu"},
        headers=ctx["admin"],
    )
    assert r.status_code == 422


# ----------------------------------------------------------------------------
# escalate
# ----------------------------------------------------------------------------

def test_escalate_plan_raises_alert_priority(client):
    ctx = _seed_full(client)
    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/escalate",
        json={"reason": "Producteur refuse acces, escalade au superviseur regional."},
        headers=ctx["admin"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "escalated"
    assert r.json()["priority"] == "urgent"

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(
            Alert.source_entity == "remediation_plans",
            Alert.source_id == ctx["plan_id"],
        ).first()
        assert alert.priority == Priority.URGENT
        assert alert.status == AlertStatus.ESCALATED
        assert alert.escalation_level >= 1
    finally:
        db.close()


def test_escalate_completed_plan_rejected(client):
    ctx = _seed_full(client)
    _force_actions_completed(ctx["plan_id"])
    client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={"outcome": "successful", "outcome_description": "Cas resolu."},
        headers=ctx["admin"],
    )

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/escalate",
        json={"reason": "tentative apres cloture"},
        headers=ctx["admin"],
    )
    assert r.status_code == 409


# ----------------------------------------------------------------------------
# Actions CRUD
# ----------------------------------------------------------------------------

def test_add_action_to_active_plan(client):
    ctx = _seed_full(client)
    before = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    n_before = len(before)

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/actions",
        json={
            "action_type": "health",
            "description": "Visite medicale annuelle de l'enfant.",
            "planned_date": str(date.today() + timedelta(days=10)),
            "responsible_organization": "Centre de sante Soubre",
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["action_type"] == "health"
    assert r.json()["status"] == "pending"

    after = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    assert len(after) == n_before + 1


def test_add_action_to_final_plan_rejected(client):
    ctx = _seed_full(client)
    _force_actions_completed(ctx["plan_id"])
    client.post(
        f"/remediation/plans/{ctx['plan_id']}/complete",
        json={"outcome": "successful", "outcome_description": "Cas resolu."},
        headers=ctx["admin"],
    )

    r = client.post(
        f"/remediation/plans/{ctx['plan_id']}/actions",
        json={
            "action_type": "other",
            "description": "Action tardive non autorisee.",
            "planned_date": str(date.today()),
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 409


def test_update_action_changes_fields(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]

    r = client.put(
        f"/remediation/actions/{action_id}",
        json={"status": "in_progress", "notes": "Demarrage du suivi."},
        headers=ctx["admin"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["notes"] == "Demarrage du suivi."


def test_update_completed_action_rejected(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]
    client.post(
        f"/remediation/actions/{action_id}/complete",
        json={"evidence": {"documents": ["proof.pdf"]}},
        headers=ctx["admin"],
    )

    r = client.put(
        f"/remediation/actions/{action_id}",
        json={"notes": "tentative apres completion"},
        headers=ctx["admin"],
    )
    assert r.status_code == 409


def test_delete_pending_action(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]

    r = client.delete(f"/remediation/actions/{action_id}", headers=ctx["admin"])
    assert r.status_code == 204


def test_delete_non_pending_action_rejected(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]
    client.put(
        f"/remediation/actions/{action_id}",
        json={"status": "in_progress"},
        headers=ctx["admin"],
    )

    r = client.delete(f"/remediation/actions/{action_id}", headers=ctx["admin"])
    assert r.status_code == 409


# ----------------------------------------------------------------------------
# Action completion
# ----------------------------------------------------------------------------

def test_complete_action_requires_evidence(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]

    r = client.post(
        f"/remediation/actions/{action_id}/complete",
        json={"evidence": {}},
        headers=ctx["admin"],
    )
    assert r.status_code == 400


def test_complete_action_succeeds_with_evidence(client):
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]

    r = client.post(
        f"/remediation/actions/{action_id}/complete",
        json={
            "evidence": {"photos": ["enrollment.jpg"], "signatures": ["parent_sig.png"]},
            "impact_assessment": "Enfant inscrit avec succes.",
        },
        headers=ctx["admin"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["completed_date"] == date.today().isoformat()
    assert "enrollment.jpg" in r.json()["evidence"]["photos"]


def test_technician_can_complete_action(client):
    """Les techniciens terrain peuvent cloturer une action (mais pas approuver un plan)."""
    ctx = _seed_full(client)
    actions = client.get(f"/remediation/plans/{ctx['plan_id']}/actions", headers=ctx["admin"]).json()
    action_id = actions[0]["id"]

    r = client.post(
        f"/remediation/actions/{action_id}/complete",
        json={"evidence": {"photos": ["field.jpg"]}},
        headers=ctx["tech"],
    )
    assert r.status_code == 200
