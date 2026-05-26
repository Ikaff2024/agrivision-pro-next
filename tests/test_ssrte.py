from app.db.models import Cooperative, Plantation, Producer, User
from tests.conftest import TestingSessionLocal


def _seed_producer_and_plantation():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop SSRTE", country="CI")
        producer = Producer(
            cooperative=coop,
            nom_complet="Kouadio SSRTE",
            code_yeyasso="SSRTE-001",
            localite="Yeyasso",
            section="Section A",
            is_active=True,
        )
        plantation = Plantation(
            name="Parcelle SSRTE",
            owner_name="Kouadio SSRTE",
            country="Cote d'Ivoire",
            region="Yeyasso",
            hectares=3.2,
            cooperative=coop,
            producer=producer,
        )
        user = User(
            email="ssrte.admin@test.ci",
            password_hash="x",
            role="admin",
            cooperative=coop,
            is_active=True,
        )
        db.add_all([coop, producer, plantation, user])
        db.commit()
        return producer.id, plantation.id
    finally:
        db.close()


def test_ssrte_community_profile_can_be_created(client):
    response = client.post("/ssrte/communities", json={
        "locality": "Yeyasso",
        "section": "Section A",
        "interview_date": "2026-05-26",
        "respondent_name": "Chef village",
        "respondent_role": "Leader communautaire",
        "school_available": True,
        "nearest_school_distance_km": 1.5,
        "has_child_protection_committee": True,
        "risks_identified": ["descolarisation", "travaux dangereux"],
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["locality"] == "Yeyasso"
    assert data["school_available"] is True


def test_ssrte_household_profile_scores_risk(client):
    producer_id, _ = _seed_producer_and_plantation()

    response = client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "interview_date": "2026-05-26",
        "household_size": 8,
        "children_count": 4,
        "school_age_children_count": 3,
        "enrolled_children_count": 1,
        "vulnerabilities": ["revenu faible", "maladie"],
        "child_work_declarations": [
            {"child": "A", "task": "machette", "dangerous": True},
            {"child": "B", "task": "ramassage cabosses"},
        ],
        "school_constraints": ["distance", "frais scolaires"],
        "consent_given": True,
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["producer_id"] == producer_id
    assert data["risk_score"] >= 60
    assert data["risk_level"] in {"high", "critical"}


def test_ssrte_plantation_visit_creates_alert_on_suspicion(client):
    _, plantation_id = _seed_producer_and_plantation()

    response = client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "visit_date": "2026-05-26",
        "checklist_data": {"children_observed": True, "tasks_checked": True},
        "children_observed": [{"name": "A", "age": 13, "observation": "present sur parcelle"}],
        "dangerous_tasks_observed": ["machette"],
        "suspected_child_labor": True,
        "consent_given": True,
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["plantation_id"] == plantation_id
    assert data["producer_id"] is not None
    assert data["suspected_child_labor"] is True

    alerts = client.get("/alerts?source_entity=ssrte_plantation_visits")
    assert alerts.status_code == 200
    assert any(a["source_entity"] == "ssrte_plantation_visits" for a in alerts.json())

    compliance = client.get("/compliance/traceability")
    assert compliance.status_code == 200
    blocks = compliance.json()["active_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["block_reason"] == "child_labor_case"
    assert "SSRTE" in blocks[0]["block_description"]


def test_ssrte_summary_counts_forms(client):
    producer_id, plantation_id = _seed_producer_and_plantation()
    client.post("/ssrte/communities", json={"locality": "Yeyasso"})
    client.post("/ssrte/households", json={"producer_id": producer_id})
    client.post("/ssrte/plantation-visits", json={"plantation_id": plantation_id})

    summary = client.get("/ssrte/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["community_profiles"] == 1
    assert data["household_profiles"] == 1
    assert data["plantation_visits"] == 1


def test_ssrte_forms_are_in_due_diligence_report(client):
    producer_id, plantation_id = _seed_producer_and_plantation()
    client.post("/ssrte/communities", json={"locality": "Yeyasso"})
    client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "school_age_children_count": 2,
        "enrolled_children_count": 1,
        "child_work_declarations": [{"child": "A", "task": "machette", "dangerous": True}],
    })
    client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "suspected_child_labor": True,
        "dangerous_tasks_observed": ["machette"],
    })

    report = client.get("/compliance/report")
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["indicators"]["ssrte_community_profiles"] == 1
    assert data["indicators"]["ssrte_household_profiles"] == 1
    assert data["indicators"]["ssrte_plantation_visits"] == 1
    assert data["indicators"]["ssrte_suspected_child_labor_visits"] == 1
    assert "ssrte_plantation_visits" in data["audit_evidence"]
    assert len(data["recent_ssrte_households"]) == 1
    assert len(data["recent_ssrte_plantation_visits"]) == 1
