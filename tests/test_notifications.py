"""Tests pour le feed in-app notifications CacaoGuard.

Couvre :
- fan-out par role (admin/agronomist voient HIGH/URGENT)
- technicien : ne voit que les alertes ou il est responsable
- viewer : pas autorise
- idempotence du sync (UniqueConstraint user_id+alert_id)
- mark-read individuel / mark-all-read
- dismiss (sort du feed sans suppression DB)
- unread-count badge
- 401 sans auth
"""
from datetime import date, datetime, timedelta

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Producer, User
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    MonitoringVisit,
    NotificationItem,
    Priority,
    VisitType,
    VisitStatus,
)
from tests.conftest import TestingSessionLocal


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    })}


def _seed_users():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop Notif", country="CI")
        admin = User(email="admin.notif@test.ci", password_hash="x", role="admin", cooperative=coop)
        agronomist = User(email="agro.notif@test.ci", password_hash="x", role="agronomist", cooperative=coop)
        tech = User(email="tech.notif@test.ci", password_hash="x", role="technician", cooperative=coop)
        viewer = User(email="viewer.notif@test.ci", password_hash="x", role="viewer", cooperative=coop)
        producer = Producer(cooperative=coop, nom_complet="Producteur Notif", localite="Soubre", is_active=True)
        db.add_all([coop, admin, agronomist, tech, viewer, producer])
        db.commit()
        return {
            "admin_id": admin.id,
            "tech_id": tech.id,
            "producer_id": producer.id,
            "admin": _auth(admin),
            "agronomist": _auth(agronomist),
            "tech": _auth(tech),
            "viewer": _auth(viewer),
        }
    finally:
        db.close()


def _seed_alert(alert_type=AlertType.HIGH_RISK_CHILD, priority=Priority.HIGH, **kwargs) -> int:
    db = TestingSessionLocal()
    try:
        source_entity = kwargs.get("source_entity", "producers")
        source_id = kwargs.get("source_id")
        if source_id is None:
            # Rattacher l'alerte à un producteur RÉEL de la coop (cloisonnement multi-tenant).
            prod = db.query(Producer).filter(Producer.nom_complet == "Producteur Notif").first()
            source_id = prod.id if prod else 1
        alert = Alert(
            source_entity=source_entity,
            source_id=source_id,
            alert_type=alert_type,
            priority=priority,
            title=kwargs.get("title", "Alerte test"),
            message=kwargs.get("message", "Contenu de l'alerte"),
            alert_metadata=kwargs.get("metadata", {}),
        )
        db.add(alert)
        db.commit()
        return alert.id
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Fan-out par role
# ----------------------------------------------------------------------------

def test_admin_receives_high_priority_alert(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH)
    r = client.get("/notifications", headers=ctx["admin"])
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1


def test_agronomist_receives_high_priority_alert(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.URGENT)
    r = client.get("/notifications", headers=ctx["agronomist"])
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_admin_does_not_receive_low_priority(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.LOW)
    r = client.get("/notifications", headers=ctx["admin"])
    assert r.json()["total"] == 0


def test_technician_does_not_receive_unassigned_alert(client):
    """Un technicien ne voit pas une alerte ou il n'est pas implique."""
    ctx = _seed_users()
    _seed_alert()  # source par defaut (children, id 1) — pas de visit/action liee au tech
    r = client.get("/notifications", headers=ctx["tech"])
    assert r.json()["total"] == 0


def test_technician_receives_alert_for_their_visit(client):
    ctx = _seed_users()
    # Cree une visite du technicien
    db = TestingSessionLocal()
    try:
        visit = MonitoringVisit(
            producer_id=ctx["producer_id"],
            scheduled_date=date.today(),
            visit_type=VisitType.ROUTINE,
            priority=Priority.MEDIUM,
            lead_assessor_id=ctx["tech_id"],
            status=VisitStatus.SCHEDULED,
        )
        db.add(visit)
        db.commit()
        visit_id = visit.id
    finally:
        db.close()

    _seed_alert(
        alert_type=AlertType.OVERDUE_ACTION,
        priority=Priority.HIGH,
        source_entity="monitoring_visits",
        source_id=visit_id,
    )
    r = client.get("/notifications", headers=ctx["tech"])
    assert r.json()["total"] == 1


def test_viewer_role_forbidden(client):
    ctx = _seed_users()
    r = client.get("/notifications", headers=ctx["viewer"])
    assert r.status_code == 403


def test_no_auth_returns_401(client):
    r = client.get("/notifications")
    assert r.status_code == 401


# ----------------------------------------------------------------------------
# Idempotence sync
# ----------------------------------------------------------------------------

def test_sync_is_idempotent(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH)

    r1 = client.post("/notifications/sync", headers=ctx["admin"])
    assert r1.json()["created"] == 1
    r2 = client.post("/notifications/sync", headers=ctx["admin"])
    assert r2.json()["created"] == 0

    db = TestingSessionLocal()
    try:
        count = db.query(NotificationItem).filter(
            NotificationItem.user_id == ctx["admin_id"],
        ).count()
        assert count == 1
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Mark read / dismiss
# ----------------------------------------------------------------------------

def test_mark_single_read(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH)
    notifs = client.get("/notifications", headers=ctx["admin"]).json()["items"]
    nid = notifs[0]["id"]

    r = client.post(f"/notifications/{nid}/read", headers=ctx["admin"])
    assert r.status_code == 200
    assert r.json()["read_at"] is not None

    badge = client.get("/notifications/unread-count", headers=ctx["admin"]).json()
    assert badge["unread_count"] == 0


def test_mark_other_user_notification_returns_403(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH)
    notifs = client.get("/notifications", headers=ctx["admin"]).json()["items"]
    nid = notifs[0]["id"]

    r = client.post(f"/notifications/{nid}/read", headers=ctx["agronomist"])
    assert r.status_code == 403


def test_mark_all_read(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH, title="Alerte 1")
    _seed_alert(priority=Priority.URGENT, title="Alerte 2")
    client.get("/notifications", headers=ctx["admin"])  # sync

    r = client.post("/notifications/mark-all-read", headers=ctx["admin"])
    assert r.status_code == 200
    assert r.json()["marked_read"] == 2

    badge = client.get("/notifications/unread-count", headers=ctx["admin"]).json()
    assert badge["unread_count"] == 0


def test_dismiss_removes_from_default_feed_but_keeps_in_db(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH)
    notifs = client.get("/notifications", headers=ctx["admin"]).json()["items"]
    nid = notifs[0]["id"]

    client.post(f"/notifications/{nid}/dismiss", headers=ctx["admin"])

    # Hors include_dismissed -> liste vide
    body = client.get("/notifications", headers=ctx["admin"]).json()
    assert body["total"] == 0

    # Avec include_dismissed -> reapparait
    body2 = client.get("/notifications?include_dismissed=true", headers=ctx["admin"]).json()
    assert body2["total"] == 1
    assert body2["items"][0]["dismissed_at"] is not None

    # En DB : toujours present
    db = TestingSessionLocal()
    try:
        assert db.query(NotificationItem).count() == 1
    finally:
        db.close()


# ----------------------------------------------------------------------------
# unread_only filter
# ----------------------------------------------------------------------------

def test_unread_only_filter(client):
    ctx = _seed_users()
    _seed_alert(priority=Priority.HIGH, title="A")
    _seed_alert(priority=Priority.URGENT, title="B")
    notifs = client.get("/notifications", headers=ctx["admin"]).json()["items"]
    client.post(f"/notifications/{notifs[0]['id']}/read", headers=ctx["admin"])

    full = client.get("/notifications", headers=ctx["admin"]).json()
    unread = client.get("/notifications?unread_only=true", headers=ctx["admin"]).json()
    assert full["total"] == 2
    assert unread["total"] == 1


# ----------------------------------------------------------------------------
# Resolved alerts not fanned out
# ----------------------------------------------------------------------------

def test_resolved_alert_not_synced(client):
    ctx = _seed_users()
    aid = _seed_alert(priority=Priority.HIGH)

    db = TestingSessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.id == aid).first()
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    r = client.get("/notifications", headers=ctx["admin"])
    assert r.json()["total"] == 0


# ----------------------------------------------------------------------------
# Cloisonnement multi-tenant (régression du bug : fuite inter-coopérative)
# ----------------------------------------------------------------------------

def test_notifications_are_cooperative_scoped(client):
    """Régression : l'admin d'une coop ne reçoit PAS l'alerte d'une autre coop."""
    db = TestingSessionLocal()
    try:
        coop_a = Cooperative(name="Coop A Iso", country="CI")
        admin_a = User(email="admin.a.iso@test.ci", password_hash="x", role="admin", cooperative=coop_a)
        prod_a = Producer(cooperative=coop_a, nom_complet="Prod A Iso", localite="A", is_active=True)
        coop_b = Cooperative(name="Coop B Iso", country="CI")
        admin_b = User(email="admin.b.iso@test.ci", password_hash="x", role="admin", cooperative=coop_b)
        db.add_all([coop_a, admin_a, prod_a, coop_b, admin_b])
        db.commit()
        prod_a_id = prod_a.id
        auth_a = _auth(admin_a)
        auth_b = _auth(admin_b)
    finally:
        db.close()

    # Alerte HIGH rattachée à un producteur de la coop A
    _seed_alert(priority=Priority.HIGH, source_entity="producers", source_id=prod_a_id)

    # Admin A (même coop) voit l'alerte ; admin B (autre coop) NON.
    assert client.get("/notifications", headers=auth_a).json()["total"] == 1
    assert client.get("/notifications", headers=auth_b).json()["total"] == 0
    assert client.get("/notifications/unread-count", headers=auth_b).json()["unread_count"] == 0


def test_sync_removes_previously_leaked_notification(client):
    """Auto-réparation : une notification héritée d'une fuite est retirée au sync."""
    db = TestingSessionLocal()
    try:
        coop_a = Cooperative(name="Coop A Leak", country="CI")
        prod_a = Producer(cooperative=coop_a, nom_complet="Prod A Leak", localite="A", is_active=True)
        coop_b = Cooperative(name="Coop B Leak", country="CI")
        admin_b = User(email="admin.b.leak@test.ci", password_hash="x", role="admin", cooperative=coop_b)
        db.add_all([coop_a, prod_a, coop_b, admin_b])
        db.commit()
        prod_a_id = prod_a.id
        admin_b_id = admin_b.id
        auth_b = _auth(admin_b)
    finally:
        db.close()

    aid = _seed_alert(priority=Priority.HIGH, source_entity="producers", source_id=prod_a_id)

    # Simule une fuite antérieure : NotificationItem de coop A chez l'admin de coop B.
    db = TestingSessionLocal()
    try:
        db.add(NotificationItem(
            user_id=admin_b_id, alert_id=aid,
            notification_type=AlertType.HIGH_RISK_CHILD, priority=Priority.HIGH,
            title="Fuite", message="Ne devrait pas etre la", payload={},
        ))
        db.commit()
    finally:
        db.close()

    # Au prochain GET, la notification fuitée est automatiquement nettoyée.
    assert client.get("/notifications", headers=auth_b).json()["total"] == 0
    db = TestingSessionLocal()
    try:
        assert db.query(NotificationItem).filter(NotificationItem.user_id == admin_b_id).count() == 0
    finally:
        db.close()
