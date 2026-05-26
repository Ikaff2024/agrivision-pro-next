from datetime import date, datetime, timedelta
import sys
import types

import pytest

from app.db.models import Cooperative, FarmForceAssessment, Harvest, Plantation, Producer, User
from app.auth.auth_service import create_access_token
from tests.conftest import TestingSessionLocal


@pytest.fixture
def mock_weasyprint(monkeypatch):
    class MockHTML:
        last_html = ""

        def __init__(self, string="", **kwargs):
            self.string = string
            MockHTML.last_html = string

        def write_pdf(self):
            return b"%PDF-1.4\n%fake-cacaoguard-pdf\n%%EOF"

    fake_module = types.ModuleType("weasyprint")
    fake_module.HTML = MockHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_module)
    return MockHTML


def _seed_producer_and_user():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop CacaoGuard", country="Cote d'Ivoire")
        user = User(
            email="agent.cacaoguard@test.ci",
            password_hash="x",
            role="admin",
            cooperative=coop,
        )
        producer = Producer(
            cooperative=coop,
            nom_complet="Kouassi Test",
            localite="Soubré",
            section="A",
            is_active=True,
        )
        db.add_all([coop, user, producer])
        db.commit()
        return producer.id, user.id
    finally:
        db.close()


def _seed_user(role="technician", email="agent.tech@test.ci"):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name=f"Coop {role}", country="CI")
        user = User(email=email, password_hash="x", role=role, cooperative=coop)
        db.add_all([coop, user])
        db.commit()
        return {
            "Authorization": "Bearer " + create_access_token({
                "sub": user.email,
                "role": user.role,
                "coop_id": user.cooperative_id,
            })
        }
    finally:
        db.close()


def test_create_child_scores_risk_and_creates_alert(client):
    producer_id, _user_id = _seed_producer_and_user()

    response = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Awa",
        "last_name": "Kouassi",
        "date_of_birth": "2014-01-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete_use", "pesticide_application"],
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["risk_level"] in ["high", "critical"]
    assert data["risk_score"] >= 60

    alerts = client.get("/children/alerts").json()
    assert len(alerts) == 1
    assert alerts[0]["source_id"] == data["id"]

    plans = client.get("/remediation/plans").json()
    assert len(plans) == 1
    assert plans[0]["child_id"] == data["id"]
    assert plans[0]["status"] == "in_progress"

    compliance = client.get("/compliance/traceability").json()
    assert compliance["summary"]["active_blocks"] == 1
    assert compliance["active_blocks"][0]["related_case_id"] == data["id"]


def test_children_static_routes_are_not_captured_by_child_id(client):
    producer_id, _user_id = _seed_producer_and_user()
    client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Yao",
        "last_name": "Koffi",
        "date_of_birth": "2012-05-01",
        "gender": "M",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    })

    stats = client.get("/children/stats/summary")
    alerts = client.get("/children/alerts")

    assert stats.status_code == 200, stats.text
    assert alerts.status_code == 200, alerts.text
    assert stats.json()["total_children"] == 1


def test_list_producers_for_cacaoguard_forms(client):
    producer_id, _user_id = _seed_producer_and_user()

    response = client.get("/producers?limit=20")

    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == producer_id
    assert data[0]["nom_complet"] == "Kouassi Test"
    assert data[0]["localite"] == "Soubré"


def test_create_risk_assessment_updates_child_and_dashboard(client):
    producer_id, user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Kouadio",
        "last_name": "NGuessan",
        "date_of_birth": "2011-03-10",
        "gender": "M",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    }).json()

    response = client.post("/children/assessments", json={
        "child_id": child["id"],
        "assessment_type": "follow_up",
        "overall_risk_score": 82,
        "overall_risk_level": "critical",
        "risk_factors": {"work": 35, "school": 20, "age": 20},
        "notes": "Cas prioritaire",
        "assessor_id": user_id,
    })

    assert response.status_code == 201, response.text

    updated = client.get(f"/children/{child['id']}").json()
    assert updated["risk_level"] == "critical"
    assert updated["risk_score"] == 82

    summary = client.get("/cacaoguard/summary")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["brand"] == "CacaoGuard"
    assert data["total_producers"] == 1
    assert data["total_children"] == 1
    assert data["high_risk_children"] == 1
    assert data["active_alerts"] == 3
    assert data["traceability_blocks"] == 1
    assert data["active_remediation_plans"] == 1


def test_monitoring_visit_can_be_planned_and_completed(client):
    producer_id, _user_id = _seed_producer_and_user()

    response = client.post("/monitoring/visits", json={
        "producer_id": producer_id,
        "scheduled_date": "2026-06-01",
        "visit_type": "follow_up",
        "priority": "high",
        "visit_location": "Soubré - GPS 5.78,-6.60",
        "checklist_data": {
            "children_observed": True,
            "parent_interview": True,
            "school_verified": False,
            "dangerous_tasks_checked": True,
        },
        "observations": "Visite programmee",
        "visit_location": "5.780000,-6.600000",
        "gps_accuracy": 12.5,
        "consent_given": True,
        "photos": [{"reference": "IMG_TEST_001.jpg", "consent": True}],
        "producer_signature_data": {"signed_by": "Kouassi Test"},
        "assessor_signature_data": {"signed_by": "Agent Test"},
    })

    assert response.status_code == 201, response.text
    visit = response.json()
    assert visit["producer_id"] == producer_id
    assert visit["status"] == "scheduled"
    assert visit["consent_given"] is True
    assert visit["photos"][0]["reference"] == "IMG_TEST_001.jpg"
    assert visit["producer_signature_data"]["signed_by"] == "Kouassi Test"
    assert visit["producer_signature_data"]["payload_hash"]
    assert visit["producer_signature_data"]["method"] == "typed_name"

    complete = client.post(f"/monitoring/visits/{visit['id']}/complete", json={
        "actual_date": "2026-06-01",
        "visit_location": "Soubré - GPS 5.78,-6.60",
        "checklist_data": {
            "children_observed": True,
            "parent_interview": True,
            "school_verified": True,
            "dangerous_tasks_checked": False,
        },
        "observations": "Aucune tache dangereuse observee",
        "dangerous_tasks_observed": [],
        "immediate_actions_taken": "Sensibilisation parent realisee",
        "consent_given": True,
        "photos": [{"reference": "IMG_TEST_002.jpg", "consent": True}],
        "producer_signature_data": {"signed_by": "Kouassi Test"},
        "assessor_signature_data": {"signed_by": "Agent Test"},
    })

    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    assert complete.json()["photos"][0]["reference"] == "IMG_TEST_002.jpg"
    assert complete.json()["assessor_signature_data"]["payload_hash"]


def test_remediation_progress_can_be_added(client):
    producer_id, _user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Aya",
        "last_name": "Kouame",
        "date_of_birth": "2013-02-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "regular",
        "dangerous_tasks_performed": ["heavy_load", "machete_use"],
    }).json()
    plan = client.get("/remediation/plans").json()[0]
    assert plan["child_id"] == child["id"]

    response = client.post(f"/remediation/plans/{plan['id']}/progress", json={
        "note": "Kit scolaire remis et rendez-vous ecole planifie.",
        "status": "in_progress",
        "resources_provided": {"school_kit": True},
    })

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["monthly_progress"][0]["note"].startswith("Kit scolaire")
    assert updated["resources_provided"]["school_kit"] is True


def test_traceability_block_lists_impacted_harvests(client):
    producer_id, _user_id = _seed_producer_and_user()
    db = TestingSessionLocal()
    try:
        producer = db.query(Producer).filter(Producer.id == producer_id).first()
        plantation = Plantation(
            name="Parcelle CacaoGuard",
            owner_name=producer.nom_complet,
            country="CI",
            cooperative_id=producer.cooperative_id,
            producer_id=producer.id,
        )
        db.add(plantation)
        db.flush()
        db.add(Harvest(
            plantation_id=plantation.id,
            harvest_date=datetime(2026, 5, 10),
            quantity_kg=450,
            quality="Bonne",
            season="petite",
            numero_recu_achat="REC-CG-001",
        ))
        db.commit()
    finally:
        db.close()

    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Koffi",
        "last_name": "Audit",
        "date_of_birth": "2012-01-01",
        "gender": "M",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete_use", "heavy_load", "pesticide_application"],
    }).json()
    assert child["risk_level"] == "critical"

    compliance = client.get("/compliance/traceability")
    assert compliance.status_code == 200, compliance.text
    data = compliance.json()
    assert data["summary"]["active_blocks"] == 1
    assert data["summary"]["impacted_batches"] == 1
    assert data["impacted_batches"][0]["receipt"] == "REC-CG-001"

    block_id = data["active_blocks"][0]["id"]
    resolved = client.post(f"/compliance/blocks/{block_id}/resolve", json={
        "resolution_notes": "Cas resolu et preuves validees.",
    })
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"


def test_due_diligence_report_summarizes_evidence(client):
    producer_id, _user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Amani",
        "last_name": "Rapport",
        "date_of_birth": "2012-06-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete_use", "heavy_load"],
    }).json()
    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            total_revenue_cfa=100_000,
            total_cost_cfa=130_000,
            profit_cfa=-30_000,
            family_labor_days=20,
            hired_labor_days=4,
            return_per_family_day_cfa=-1500,
        ))
        db.commit()
    finally:
        db.close()

    response = client.get("/compliance/report")

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["report_type"] == "CacaoGuard due diligence"
    assert report["coverage"]["children"] == 1
    assert report["indicators"]["active_remediation_plans"] == 1
    assert report["indicators"]["active_traceability_blocks"] == 1
    assert report["critical_cases"][0]["child_id"] == child["id"]
    assert "monitoring_visits" in report["audit_evidence"]
    assert "ai_inconsistencies" in report
    assert "ai_inconsistencies" in report["indicators"]
    assert report["indicators"]["farmforce_assessments"] == 1
    assert report["indicators"]["farmforce_negative_profit_assessments"] == 1
    assert report["recent_farmforce_assessments"][0]["profit_cfa"] == -30000
    assert "farmforce_assessments" in report["audit_evidence"]

    summary = client.get("/cacaoguard/summary").json()
    assert summary["farmforce_assessments"] == 1
    assert summary["farmforce_negative_profit_assessments"] == 1


def test_lightweight_ai_detects_inconsistencies_and_creates_alert(client):
    producer_id, _user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Aya",
        "last_name": "Incoherence",
        "date_of_birth": "2013-01-01",
        "gender": "F",
        "school_status": "enrolled",
        "school_name": "Ecole Test",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": [],
    }).json()
    visit = client.post("/monitoring/visits", json={
        "producer_id": producer_id,
        "scheduled_date": str(date.today()),
        "visit_type": "follow_up",
        "priority": "high",
        "checklist_data": {"children_observed": True},
        "consent_given": False,
        "photos": [{"reference": "PHOTO_WITHOUT_CONSENT.jpg"}],
    }).json()
    client.post(f"/monitoring/visits/{visit['id']}/complete", json={
        "actual_date": str(date.today()),
        "checklist_data": {"children_observed": True},
        "dangerous_tasks_observed": ["machete_use"],
        "photos": [{"reference": "PHOTO_WITHOUT_CONSENT.jpg"}],
        "consent_given": False,
    })

    response = client.get("/ai/inconsistencies?create_alerts=true")

    assert response.status_code == 200, response.text
    data = response.json()
    codes = {finding["code"] for finding in data["findings"]}
    assert "school_work_conflict" in codes
    assert "school_dangerous_tasks_observed" in codes
    assert "photos_without_consent" in codes
    assert any(finding["entity_id"] == child["id"] for finding in data["findings"])

    alerts = client.get("/alerts").json()
    assert any(alert["alert_type"] == "audit_failure" for alert in alerts)

    report = client.get("/compliance/report").json()
    assert report["indicators"]["ai_inconsistencies"] >= 3
    assert report["indicators"]["ai_critical_inconsistencies"] >= 1


def test_due_diligence_report_pdf_generates_official_file(client, mock_weasyprint):
    producer_id, _user_id = _seed_producer_and_user()
    client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Amani",
        "last_name": "PDF",
        "date_of_birth": "2012-06-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete_use", "heavy_load"],
    })

    response = client.get("/compliance/report.pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "Rapport_CacaoGuard_Due_Diligence" in response.headers["content-disposition"]
    assert "AgriVision Pro / CacaoGuard" in mock_weasyprint.last_html
    assert "Due diligence" in mock_weasyprint.last_html


def test_training_session_attendance_and_report(client):
    producer_id, _user_id = _seed_producer_and_user()

    response = client.post("/training/sessions", json={
        "title": "Sensibilisation travail des enfants",
        "training_type": "child_protection",
        "scheduled_date": "2026-06-15",
        "location": "Salle cooperative",
        "village": "Soubre",
        "expected_participants": 25,
        "topics_covered": ["Age minimum", "Taches dangereuses", "Scolarisation"],
        "materials_used": {"quiz": True, "supports": True},
    })

    assert response.status_code == 201, response.text
    session = response.json()
    assert session["status"] == "planned"
    assert session["expected_participants"] == 25

    attendance = client.post(f"/training/sessions/{session['id']}/attendance", json={
        "participants": [
            {
                "producer_id": producer_id,
                "name": "Kouassi Test",
                "signature": True,
                "evaluation_score": 86,
            }
        ],
        "post_test_scores": {"average": 86},
        "effectiveness_rating": 4.5,
        "status": "completed",
    })

    assert attendance.status_code == 200, attendance.text
    updated = attendance.json()
    assert updated["status"] == "completed"
    assert updated["actual_participants"] == 1
    assert updated["participants"][0]["signature"] is True

    report = client.get("/compliance/report").json()
    assert report["indicators"]["training_sessions_total"] == 1
    assert report["indicators"]["training_sessions_completed"] == 1
    assert report["indicators"]["training_participants"] == 1
    assert "training_sessions" in report["audit_evidence"]
    assert "monitoring_visits_with_photos" in report["indicators"]


def test_alert_checks_create_and_escalate_overdue_items(client):
    producer_id, _user_id = _seed_producer_and_user()
    visit = client.post("/monitoring/visits", json={
        "producer_id": producer_id,
        "scheduled_date": str(date.today() - timedelta(days=10)),
        "visit_type": "follow_up",
        "priority": "high",
    }).json()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Yao",
        "last_name": "Retard",
        "date_of_birth": "2012-01-01",
        "gender": "M",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete_use", "heavy_load"],
    }).json()

    db = TestingSessionLocal()
    try:
        from app.db.models_social import (
            ActionStatus,
            BlockStatus,
            RemediationAction,
            RemediationPlan,
            TraceabilityBlock,
        )

        plan = db.query(RemediationPlan).filter(RemediationPlan.child_id == child["id"]).first()
        plan.expected_completion_date = date.today() - timedelta(days=9)
        action = db.query(RemediationAction).filter(RemediationAction.remediation_plan_id == plan.id).first()
        action.planned_date = date.today() - timedelta(days=8)
        block = db.query(TraceabilityBlock).filter(TraceabilityBlock.producer_id == producer_id).first()
        block.expected_resolution_date = date.today() - timedelta(days=8)
        db.commit()
        plan_id = plan.id
        action_id = action.id
        block_id = block.id
    finally:
        db.close()

    response = client.post("/alerts/run-checks?escalation_after_days=7")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["reviewed_items"] == 4
    assert data["created_alerts"] == 2
    assert data["escalated_alerts"] == 4
    sources = {(alert["source_entity"], alert["source_id"]) for alert in data["alerts"]}
    assert ("monitoring_visits", visit["id"]) in sources
    assert ("remediation_plans", plan_id) in sources
    assert ("remediation_actions", action_id) in sources
    assert ("traceability_blocks", block_id) in sources

    alerts = client.get("/alerts").json()
    assert any(alert["status"] == "escalated" for alert in alerts)

    db = TestingSessionLocal()
    try:
        assert db.query(RemediationPlan).filter(RemediationPlan.id == plan_id).first().status.value == "escalated"
        assert db.query(RemediationAction).filter(RemediationAction.id == action_id).first().status == ActionStatus.OVERDUE
        assert db.query(TraceabilityBlock).filter(TraceabilityBlock.id == block_id).first().status == BlockStatus.ESCALATED
    finally:
        db.close()


def test_technician_cannot_run_alert_checks(client):
    headers = _seed_user(role="technician", email="tech.alerts@test.ci")

    response = client.post("/alerts/run-checks", headers=headers)

    assert response.status_code == 403


def test_privacy_access_logs_child_reads_and_report_access(client):
    producer_id, _user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Audit",
        "last_name": "Privacy",
        "date_of_birth": "2013-01-01",
        "gender": "F",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    }).json()

    child_response = client.get(f"/children/{child['id']}")
    assert child_response.status_code == 200

    report_response = client.get("/compliance/report")
    assert report_response.status_code == 200
    assert "privacy_access_logs" in report_response.json()["indicators"]

    logs = client.get("/privacy/access-logs").json()
    actions = {log["action"] for log in logs}
    assert "view_child" in actions
    assert "view_due_diligence_report" in actions
    child_log = next(log for log in logs if log["action"] == "view_child")
    assert child_log["source_id"] == child["id"]
    assert child_log["redacted"] is False


def test_privacy_logs_capture_redacted_technician_access(client):
    producer_id, _user_id = _seed_producer_and_user()
    client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Redacted",
        "last_name": "Audit",
        "date_of_birth": "2013-01-01",
        "gender": "M",
        "birth_certificate_number": "ACT-999",
        "school_status": "never_enrolled",
        "school_name": "Ecole Test",
        "is_working_on_farm": True,
        "work_frequency": "regular",
    })
    technician_headers = _seed_user(role="technician", email="tech.privacy@test.ci")

    children = client.get("/children", headers=technician_headers)
    assert children.status_code == 200
    assert children.json()[0]["privacy_redacted"] is True

    logs = client.get("/privacy/access-logs").json()
    redacted_log = next(log for log in logs if log["action"] == "list_children")
    assert redacted_log["user_role"] == "technician"
    assert redacted_log["redacted"] is True
    assert redacted_log["metadata"]["count"] == 1


def test_technician_cannot_view_privacy_access_logs(client):
    headers = _seed_user(role="technician", email="tech.privacy.logs@test.ci")

    response = client.get("/privacy/access-logs", headers=headers)

    assert response.status_code == 403


def test_technician_gets_redacted_child_data_and_no_report_access(client):
    producer_id, _user_id = _seed_producer_and_user()
    client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Secret",
        "last_name": "Enfant",
        "date_of_birth": "2013-07-01",
        "gender": "F",
        "birth_certificate_number": "ACT-123",
        "school_status": "never_enrolled",
        "school_name": "Ecole Test",
        "is_working_on_farm": True,
        "work_frequency": "regular",
        "dangerous_tasks_performed": ["machete_use"],
    })
    headers = _seed_user(role="technician", email="tech.cacaoguard@test.ci")

    children = client.get("/children", headers=headers)
    assert children.status_code == 200, children.text
    child = children.json()[0]
    assert child["privacy_redacted"] is True
    assert child["last_name"] == "Confidentiel"
    assert child["birth_certificate_number"] is None
    assert child["school_name"] is None
    assert child["dangerous_tasks_performed"] == []

    report = client.get("/compliance/report", headers=headers)
    assert report.status_code == 403


def test_technician_cannot_update_child_or_view_remediation(client):
    producer_id, _user_id = _seed_producer_and_user()
    child = client.post("/children", json={
        "producer_id": producer_id,
        "first_name": "Awa",
        "last_name": "Role",
        "date_of_birth": "2014-01-01",
        "gender": "F",
        "school_status": "never_enrolled",
        "is_working_on_farm": True,
        "work_frequency": "regular",
    }).json()
    headers = _seed_user(role="technician", email="tech2.cacaoguard@test.ci")

    update = client.put(f"/children/{child['id']}", headers=headers, json={
        "school_status": "enrolled",
    })
    assert update.status_code == 403

    plans = client.get("/remediation/plans", headers=headers)
    assert plans.status_code == 403
