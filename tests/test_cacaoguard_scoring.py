"""Tests dedies a la methodologie de scoring CacaoGuard v2.0 (6 facteurs).

Couvre :
- les 3 nouveaux facteurs (economic / geographic / history)
- le bornement par facteur
- l'endpoint POST /children/{id}/calculate-risk
- la stamp methodology_version sur RiskAssessment
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.db.models import Cooperative, FarmForceAssessment, Producer, User
from app.auth.auth_service import create_access_token
from app.db.models_social import (
    AssessmentStatus,
    AssessmentType,
    Child,
    RiskAssessment,
    RiskLevel,
    SchoolStatus,
    SsrteCommunityProfile,
    WorkFrequency,
)
from tests.conftest import TestingSessionLocal


def _seed_producer(localite: str | None = None) -> tuple[int, int]:
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop Scoring", country="CI")
        user = User(email="score@test.ci", password_hash="x", role="admin", cooperative=coop)
        producer = Producer(
            cooperative=coop,
            nom_complet="Producteur Scoring",
            localite=localite,
            is_active=True,
        )
        db.add_all([coop, user, producer])
        db.commit()
        return producer.id, user.id
    finally:
        db.close()


def _admin_headers(email="score@test.ci"):
    """En-têtes d'auth de l'admin de 'Coop Scoring' (cloisonnement)."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return {"Authorization": "Bearer " + create_access_token({
            "sub": user.email, "role": user.role, "coop_id": user.cooperative_id,
        })}
    finally:
        db.close()


def _create_child_payload(producer_id: int, **overrides) -> dict:
    payload = {
        "producer_id": producer_id,
        "first_name": "Test",
        "last_name": "Enfant",
        "date_of_birth": "2015-01-01",  # ~11 ans le 2026-05-27
        "gender": "F",
        "school_status": "enrolled",
        "is_working_on_farm": False,
        "work_frequency": "never",
    }
    payload.update(overrides)
    return payload


# ----------------------------------------------------------------------------
# economic_risk
# ----------------------------------------------------------------------------

def test_economic_risk_negative_profit_scores_max(client):
    producer_id, _ = _seed_producer()

    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            total_revenue_cfa=200_000,
            total_cost_cfa=350_000,
            profit_cfa=-150_000,
            return_per_family_day_cfa=-500,
            family_labor_days=300,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.status_code == 201, r.text
    assert r.json()["risk_factors"]["economic"] == 10


def test_economic_risk_low_return_per_day_scores_seven(client):
    producer_id, _ = _seed_producer()

    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            profit_cfa=100_000,
            return_per_family_day_cfa=800,  # < 1000
            family_labor_days=125,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["economic"] == 7


def test_economic_risk_decent_return_scores_zero(client):
    producer_id, _ = _seed_producer()

    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            profit_cfa=500_000,
            return_per_family_day_cfa=4000,  # >= SMIG
            family_labor_days=125,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["economic"] == 0


def test_economic_risk_no_farmforce_data_scores_zero(client):
    producer_id, _ = _seed_producer()
    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["economic"] == 0


# ----------------------------------------------------------------------------
# geographic_risk
# ----------------------------------------------------------------------------

def test_geographic_risk_uses_child_school_distance_first(client):
    producer_id, _ = _seed_producer(localite="Soubre")

    r = client.post(
        "/children",
        json=_create_child_payload(producer_id, school_distance_km=6.0),
        headers=_admin_headers(),
    )
    assert r.json()["risk_factors"]["geographic"] == 5


def test_geographic_risk_falls_back_to_community_profile(client):
    producer_id, _ = _seed_producer(localite="Daloa")

    db = TestingSessionLocal()
    try:
        db.add(SsrteCommunityProfile(
            locality="Daloa",
            interview_date=date.today(),
            school_available=True,
            nearest_school_distance_km=Decimal("3.5"),
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["geographic"] == 3


def test_geographic_risk_no_school_in_community_scores_max(client):
    producer_id, _ = _seed_producer(localite="Yopougon")

    db = TestingSessionLocal()
    try:
        db.add(SsrteCommunityProfile(
            locality="Yopougon",
            interview_date=date.today(),
            school_available=False,
            nearest_school_distance_km=None,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["geographic"] == 5


def test_geographic_risk_no_data_scores_zero(client):
    producer_id, _ = _seed_producer()
    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    assert r.json()["risk_factors"]["geographic"] == 0


# ----------------------------------------------------------------------------
# history_risk
# ----------------------------------------------------------------------------

def test_history_risk_increments_with_prior_high_assessments(client):
    producer_id, _ = _seed_producer()

    # 1ere creation : pas d'historique
    r = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers())
    child_id = r.json()["id"]
    assert r.json()["risk_factors"]["history"] == 0

    # Une evaluation HIGH posee manuellement
    client.post("/children/assessments", json={
        "child_id": child_id,
        "assessment_type": "follow_up",
        "overall_risk_score": 65,
        "overall_risk_level": "high",
        "risk_factors": {"work": 30, "school": 20},
    }, headers=_admin_headers())

    # Une mise a jour recalcule le score, history doit etre = 3
    upd = client.put(f"/children/{child_id}", json={"is_working_on_farm": True}, headers=_admin_headers())
    assert upd.status_code == 200, upd.text
    assert upd.json()["risk_factors"]["history"] == 3

    # 2eme evaluation HIGH
    client.post("/children/assessments", json={
        "child_id": child_id,
        "assessment_type": "follow_up",
        "overall_risk_score": 78,
        "overall_risk_level": "critical",
        "risk_factors": {"work": 35},
    }, headers=_admin_headers())

    upd2 = client.put(f"/children/{child_id}", json={"is_working_on_farm": True}, headers=_admin_headers())
    assert upd2.json()["risk_factors"]["history"] == 5


# ----------------------------------------------------------------------------
# /calculate-risk endpoint
# ----------------------------------------------------------------------------

def test_calculate_risk_endpoint_returns_breakdown_without_persisting(client):
    producer_id, _ = _seed_producer()

    r = client.post("/children", json=_create_child_payload(
        producer_id,
        date_of_birth="2014-01-01",
        school_status="never_enrolled",
        is_working_on_farm=True,
        work_frequency="daily",
        dangerous_tasks_performed=["machete_use", "pesticide_application"],
    ), headers=_admin_headers())
    child_id = r.json()["id"]
    persisted_score = r.json()["risk_score"]

    # Ajout d'un context FarmForce apres creation -> drift attendu
    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            profit_cfa=-50_000,
            return_per_family_day_cfa=-100,
            family_labor_days=200,
        ))
        db.commit()
    finally:
        db.close()

    sim = client.post(f"/children/{child_id}/calculate-risk", headers=_admin_headers())
    assert sim.status_code == 200, sim.text
    body = sim.json()

    assert body["methodology_version"] == "2.0"
    assert set(body["risk_factors"].keys()) == {
        "age", "school", "work", "dangerous_tasks", "economic", "geographic", "history",
    }
    assert body["risk_factors"]["economic"] == 10  # FF deficitaire
    assert body["risk_score"] > persisted_score
    assert body["drift"] > 0

    # Verifier que rien n'a ete persiste
    fresh = client.get(f"/children/{child_id}", headers=_admin_headers())
    assert fresh.json()["risk_score"] == persisted_score


# ----------------------------------------------------------------------------
# methodology_version stamping
# ----------------------------------------------------------------------------

def test_assessment_records_methodology_version(client):
    producer_id, _ = _seed_producer()
    child = client.post("/children", json=_create_child_payload(producer_id), headers=_admin_headers()).json()

    client.post("/children/assessments", json={
        "child_id": child["id"],
        "assessment_type": "initial",
        "overall_risk_score": 50,
        "overall_risk_level": "high",
        "risk_factors": {"work": 30},
    }, headers=_admin_headers())

    db = TestingSessionLocal()
    try:
        assessment = db.query(RiskAssessment).filter(
            RiskAssessment.child_id == child["id"]
        ).first()
        assert assessment is not None
        assert assessment.methodology_version == "2.0"
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Bornement total
# ----------------------------------------------------------------------------

def test_max_intrinsic_plus_context_reaches_critical(client):
    """Sur premiere creation (sans historique), le max atteignable est 95.

    25 age + 25 school + 20 work + 10 dangerous + 10 economic + 5 geographic = 95.
    Confirme : le score est CRITICAL et chaque facteur saturé est plafonné comme spec.
    """
    producer_id, _ = _seed_producer(localite="Sansterre")

    db = TestingSessionLocal()
    try:
        db.add(FarmForceAssessment(
            producer_id=producer_id,
            campaign_label="2025-2026",
            profit_cfa=-200_000,
            return_per_family_day_cfa=-1000,
            family_labor_days=200,
        ))
        db.add(SsrteCommunityProfile(
            locality="Sansterre",
            interview_date=date.today(),
            school_available=False,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/children", json=_create_child_payload(
        producer_id,
        date_of_birth="2017-06-01",  # < 12 ans
        school_status="never_enrolled",
        is_working_on_farm=True,
        work_frequency="daily",
        dangerous_tasks_performed=["a", "b", "c", "d", "e"],  # 5 > cap 2
    ), headers=_admin_headers())
    assert r.status_code == 201, r.text
    body = r.json()
    factors = body["risk_factors"]

    assert factors["age"] == 25
    assert factors["school"] == 25
    assert factors["work"] == 20  # cap
    assert factors["dangerous_tasks"] == 10  # cap (5 tasks * 5 = 25 → cap 10)
    assert factors["economic"] == 10
    assert factors["geographic"] == 5
    assert factors["history"] == 0  # premiere creation
    assert body["risk_score"] == 95.0
    assert body["risk_level"] == "critical"
