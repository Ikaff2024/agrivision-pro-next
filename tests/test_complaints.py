"""Tests pour le module Complaints CacaoGuard.

Couvre :
- creation anonyme (sans auth)
- generation de reference auto (CMP-YYYY-NNN)
- auto-creation d'alerte pour types/severites sensibles
- restriction d'acces list/get/update aux roles admin/agronomist
- workflow de mise a jour avec auto-dates
- escalation explicite + aggravation alerte
- redaction du reporter pour roles non-admin sur cas restricted/anonymes
- log confidentialite cree pour chaque action
"""
from datetime import date

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Producer, User
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    Complaint,
    ComplaintStatus,
    PrivacyAccessLog,
    Priority,
)
from tests.conftest import TestingSessionLocal


def _seed_minimal():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop Complaints", country="CI")
        admin = User(email="admin.cmp@test.ci", password_hash="x", role="admin", cooperative=coop)
        agronomist = User(email="agro.cmp@test.ci", password_hash="x", role="agronomist", cooperative=coop)
        technician = User(email="tech.cmp@test.ci", password_hash="x", role="technician", cooperative=coop)
        producer = Producer(cooperative=coop, nom_complet="Kouame Test", localite="Soubre", is_active=True)
        db.add_all([coop, admin, agronomist, technician, producer])
        db.commit()
        return {
            "producer_id": producer.id,
            "admin": _auth(admin),
            "agronomist": _auth(agronomist),
            "technician": _auth(technician),
        }
    finally:
        db.close()


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    })}


# ----------------------------------------------------------------------------
# Creation
# ----------------------------------------------------------------------------

def test_anonymous_complaint_creation_returns_reference(client):
    _seed_minimal()
    r = client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "high",
        "description": "Enfant observe sur plantation pendant la journee scolaire.",
        "location_description": "Plantation N5, zone Soubre",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reference"].startswith("CMP-")
    assert body["status"] == "received"
    assert "id" in body


def test_authenticated_complaint_uses_user_source(client):
    ctx = _seed_minimal()
    r = client.post(
        "/complaints",
        json={
            "complaint_type": "abuse",
            "severity": "critical",
            "description": "Suspicion de maltraitance signalee par voisin.",
            "producer_id": ctx["producer_id"],
        },
        headers=ctx["agronomist"],
    )
    assert r.status_code == 201, r.text

    db = TestingSessionLocal()
    try:
        complaint = db.query(Complaint).first()
        assert complaint is not None
        assert complaint.created_by is not None
    finally:
        db.close()


def test_reference_sequence_increments(client):
    _seed_minimal()
    refs = []
    for i in range(3):
        r = client.post("/complaints", json={
            "complaint_type": "other",
            "severity": "low",
            "description": f"Signalement test numero {i}",
        })
        refs.append(r.json()["reference"])
    # Tous distincts, sequence croissante
    assert len(set(refs)) == 3
    numbers = [int(ref.rsplit("-", 1)[1]) for ref in refs]
    assert numbers == sorted(numbers)


def test_invalid_producer_id_returns_404(client):
    _seed_minimal()
    r = client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "medium",
        "description": "Signalement avec producteur inexistant.",
        "producer_id": 99999,
    })
    assert r.status_code == 404


# ----------------------------------------------------------------------------
# Auto-alerte
# ----------------------------------------------------------------------------

def test_high_severity_creates_alert(client):
    _seed_minimal()
    r = client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "critical",
        "description": "Cas tres grave signale en urgence.",
    })
    complaint_id = r.json()["id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(
            Alert.source_entity == "complaints",
            Alert.source_id == complaint_id,
        ).first()
        assert alert is not None
        assert alert.alert_type == AlertType.COMPLAINT
        assert alert.priority == Priority.URGENT
    finally:
        db.close()


def test_trafficking_type_creates_alert_even_at_low_severity(client):
    _seed_minimal()
    r = client.post("/complaints", json={
        "complaint_type": "trafficking",
        "severity": "low",  # severite basse mais type ultra-sensible
        "description": "Signalement traite a verifier sur le terrain.",
    })
    complaint_id = r.json()["id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.source_id == complaint_id).first()
        assert alert is not None
        assert alert.alert_type == AlertType.COMPLAINT
    finally:
        db.close()


def test_low_severity_other_type_does_not_create_alert(client):
    _seed_minimal()
    r = client.post("/complaints", json={
        "complaint_type": "other",
        "severity": "low",
        "description": "Question administrative sans urgence.",
    })
    complaint_id = r.json()["id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(
            Alert.source_entity == "complaints",
            Alert.source_id == complaint_id,
        ).first()
        assert alert is None
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Acces
# ----------------------------------------------------------------------------

def test_technician_cannot_list_complaints(client):
    ctx = _seed_minimal()
    client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "medium",
        "description": "Cas a investiguer.",
    })
    r = client.get("/complaints", headers=ctx["technician"])
    assert r.status_code == 403


def test_agronomist_can_list_complaints(client):
    ctx = _seed_minimal()
    client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "medium",
        "description": "Cas a investiguer.",
    })
    r = client.get("/complaints", headers=ctx["agronomist"])
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_anonymous_reporter_redacted_for_non_admin(client):
    ctx = _seed_minimal()
    client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "high",
        "description": "Signalement sensible communautaire.",
        "reporter_name": "Madame X",
        "reporter_contact": "0102030405",
        "source": "anonymous",
    })
    # Agronomist voit redacte
    r_agro = client.get("/complaints", headers=ctx["agronomist"])
    assert r_agro.json()[0]["reporter_name"] is None
    assert r_agro.json()[0]["reporter_relationship"] == "[redacted]"

    # Admin voit clair
    r_admin = client.get("/complaints", headers=ctx["admin"])
    assert r_admin.json()[0]["reporter_name"] == "Madame X"
    assert r_admin.json()[0]["reporter_contact"] == "0102030405"


# ----------------------------------------------------------------------------
# Workflow update
# ----------------------------------------------------------------------------

def test_update_sets_investigation_dates_automatically(client):
    ctx = _seed_minimal()
    created = client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "medium",
        "description": "Cas a traiter.",
    }).json()

    # Passage a UNDER_REVIEW : initialise start_date
    r = client.put(f"/complaints/{created['id']}", json={
        "status": "under_review",
    }, headers=ctx["admin"])
    assert r.status_code == 200
    assert r.json()["investigation_start_date"] == date.today().isoformat()
    assert r.json()["investigation_end_date"] is None

    # Passage a CLOSED : initialise end_date
    r = client.put(f"/complaints/{created['id']}", json={
        "status": "substantiated",
        "findings": "Cas confirme, plan de remediation en cours.",
    }, headers=ctx["admin"])
    assert r.status_code == 200
    assert r.json()["investigation_end_date"] == date.today().isoformat()
    assert r.json()["findings"].startswith("Cas confirme")


def test_update_with_unknown_investigator_returns_404(client):
    ctx = _seed_minimal()
    created = client.post("/complaints", json={
        "complaint_type": "other",
        "severity": "low",
        "description": "Pour test investigateur inexistant.",
    }).json()

    r = client.put(f"/complaints/{created['id']}", json={
        "assigned_investigator": 99999,
    }, headers=ctx["admin"])
    assert r.status_code == 404


# ----------------------------------------------------------------------------
# Escalation
# ----------------------------------------------------------------------------

def test_escalate_complaint_aggravates_alert(client):
    ctx = _seed_minimal()
    created = client.post("/complaints", json={
        "complaint_type": "abuse",
        "severity": "high",  # cree deja une alerte
        "description": "Cas a escalader vers autorites.",
    }).json()

    r = client.post(f"/complaints/{created['id']}/escalate", json={
        "reason": "Refus de cooperation du producteur, suspicion confirmee.",
        "referred_to": "Brigade de protection des mineurs - Soubre",
    }, headers=ctx["admin"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "escalated"
    assert r.json()["referral_made"] is True
    assert "Soubre" in r.json()["referred_to"]

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.source_id == created["id"]).first()
        assert alert is not None
        assert alert.priority == Priority.URGENT
        assert alert.status == AlertStatus.ESCALATED
        assert "Refus de cooperation" in alert.message
    finally:
        db.close()


def test_escalate_creates_alert_when_none_existed(client):
    ctx = _seed_minimal()
    # Cas LOW + OTHER : pas d'alerte auto a la creation
    created = client.post("/complaints", json={
        "complaint_type": "other",
        "severity": "low",
        "description": "Cas qui devient grave en cours d'investigation.",
    }).json()

    r = client.post(f"/complaints/{created['id']}/escalate", json={
        "reason": "Nouveaux elements decouverts, escalade obligatoire.",
    }, headers=ctx["admin"])
    assert r.status_code == 200

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.source_id == created["id"]).first()
        assert alert is not None
        assert alert.priority == Priority.URGENT
        assert alert.alert_type == AlertType.COMPLAINT
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Privacy log
# ----------------------------------------------------------------------------

def test_each_complaint_action_creates_privacy_log(client):
    ctx = _seed_minimal()
    created = client.post("/complaints", json={
        "complaint_type": "child_labor",
        "severity": "medium",
        "description": "Cas en cours d'investigation.",
    }).json()
    client.get(f"/complaints/{created['id']}", headers=ctx["admin"])
    client.put(f"/complaints/{created['id']}", json={"status": "under_review"}, headers=ctx["admin"])
    client.post(f"/complaints/{created['id']}/escalate", json={"reason": "Cas verifie."}, headers=ctx["admin"])

    db = TestingSessionLocal()
    try:
        actions = (
            db.query(PrivacyAccessLog.action)
            .filter(PrivacyAccessLog.source_entity == "complaints")
            .all()
        )
        actions = [a[0] for a in actions]
        assert "create_complaint" in actions
        assert "view_complaint" in actions
        assert "update_complaint" in actions
        assert "escalate_complaint" in actions
    finally:
        db.close()
