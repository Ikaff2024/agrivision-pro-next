"""
Notifications in-app CacaoGuard.

Repond au besoin "Notifications" de la roadmap (section 4) sans dependre
d'une infrastructure email/SMS. Le mecanisme est un feed in-app derive
des Alert : pour chaque utilisateur eligible, un NotificationItem est
cree a la demande (au prochain GET) avec idempotence stricte.

Endpoints :
- GET  /notifications              : liste paginee, filtre unread/dismissed
- GET  /notifications/unread-count : compteur badge
- POST /notifications/{id}/read    : marque lu
- POST /notifications/mark-all-read: marque tout lu
- POST /notifications/{id}/dismiss : retire du feed (conserve en DB)
- POST /notifications/sync         : force la synchro (utile en tests)

Logique de fan-out :
- admin/agronomist : recoivent toutes les Alert priority HIGH/URGENT
- technician       : ne recoit pour l'instant que les Alert COMPLAINT/HIGH_RISK_CHILD
                     dont la metadata pointe vers un producer/visit ou ils sont
                     responsibles. Scoping fin (cooperative/assignment) -> v2.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cacaoguard_ops_routes import get_optional_current_user, require_role
from app.db.database import get_db
from app.db.models import User
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    MonitoringVisit,
    NotificationItem,
    Priority,
    RemediationAction,
)
from app.services.social_scope import coop_alert_ids

router = APIRouter(prefix="/notifications", tags=["CacaoGuard - notifications"])


_SUPERVISOR_ROLES = {"admin", "agronomist"}
_NOTIFIABLE_PRIORITIES = {Priority.HIGH, Priority.URGENT}
_TECHNICIAN_NOTIFIABLE_TYPES = {
    AlertType.HIGH_RISK_CHILD,
    AlertType.COMPLAINT,
    AlertType.OVERDUE_ACTION,
}


def _require_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentification requise pour les notifications.")
    return user


def _is_alert_for_technician(db: Session, alert: Alert, tech_id: int) -> bool:
    """Le technicien est-il directement implique dans l'alerte ?

    Critere v1 : il est responsible d'une RemediationAction du plan
    referencé OU lead_assessor d'une MonitoringVisit du producteur.
    """
    if alert.alert_type not in _TECHNICIAN_NOTIFIABLE_TYPES:
        return False

    metadata = alert.alert_metadata or {}
    if alert.source_entity == "monitoring_visits":
        visit = db.query(MonitoringVisit).filter(MonitoringVisit.id == alert.source_id).first()
        return bool(visit and visit.lead_assessor_id == tech_id)
    if alert.source_entity == "remediation_plans":
        actions = db.query(RemediationAction).filter(
            RemediationAction.remediation_plan_id == alert.source_id,
            RemediationAction.responsible_id == tech_id,
        ).first()
        return actions is not None
    # Fallback : si la metadata reference explicitement le user
    return metadata.get("responsible_id") == tech_id


def _alert_payload(alert: Alert) -> dict:
    return {
        "source_entity": alert.source_entity,
        "source_id": alert.source_id,
        "alert_status": alert.status.value if alert.status else None,
        "metadata": alert.alert_metadata or {},
    }


def sync_notifications_for_user(db: Session, user: User) -> int:
    """Cree les NotificationItem manquantes pour `user`. Retourne le nombre cree."""
    role = user.role

    # Cloisonnement multi-tenant : ne considérer QUE les alertes de la coopérative
    # de l'utilisateur (résolues via l'entité source → producteur → coopérative).
    allowed_alert_ids = coop_alert_ids(db, user.cooperative_id)

    # Auto-réparation : retirer du feed les notifications déjà reçues qui
    # n'appartiennent PAS à la coopérative de l'utilisateur (corrige les fuites
    # inter-tenant antérieures à ce correctif).
    removed = (
        db.query(NotificationItem)
        .filter(
            NotificationItem.user_id == user.id,
            ~NotificationItem.alert_id.in_(allowed_alert_ids if allowed_alert_ids else [-1]),
        )
        .delete(synchronize_session=False)
    )
    if removed:
        db.commit()

    # Sans coopérative, ou sans alerte rattachable, aucune notification (fail-closed).
    if not allowed_alert_ids:
        return 0

    # Selection des alertes candidates (bornées à la coopérative)
    base_query = db.query(Alert).filter(
        Alert.status != AlertStatus.RESOLVED,
        Alert.id.in_(list(allowed_alert_ids)),
    )
    if role in _SUPERVISOR_ROLES:
        candidates = base_query.filter(Alert.priority.in_(list(_NOTIFIABLE_PRIORITIES))).all()
    elif role == "technician":
        candidates = base_query.filter(Alert.alert_type.in_(list(_TECHNICIAN_NOTIFIABLE_TYPES))).all()
        candidates = [a for a in candidates if _is_alert_for_technician(db, a, user.id)]
    else:
        return 0

    if not candidates:
        return 0

    # IDs deja synchronisees (evite N requetes)
    existing_ids = {
        row[0]
        for row in db.query(NotificationItem.alert_id)
        .filter(NotificationItem.user_id == user.id)
        .all()
    }

    created = 0
    for alert in candidates:
        if alert.id in existing_ids:
            continue
        db.add(NotificationItem(
            user_id=user.id,
            alert_id=alert.id,
            notification_type=alert.alert_type,
            priority=alert.priority,
            title=alert.title or alert.alert_type.value,
            message=alert.message,
            payload=_alert_payload(alert),
        ))
        created += 1
    if created:
        db.commit()
    return created


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: int
    notification_type: str
    priority: str
    title: str
    message: Optional[str]
    payload: dict
    read_at: Optional[datetime]
    dismissed_at: Optional[datetime]
    created_at: Optional[datetime]


def _to_out(n: NotificationItem) -> dict:
    return {
        "id": n.id,
        "alert_id": n.alert_id,
        "notification_type": n.notification_type.value if n.notification_type else None,
        "priority": n.priority.value if n.priority else None,
        "title": n.title,
        "message": n.message,
        "payload": n.payload or {},
        "read_at": n.read_at,
        "dismissed_at": n.dismissed_at,
        "created_at": n.created_at,
    }


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------

@router.get("")
def list_notifications(
    unread_only: bool = Query(False),
    include_dismissed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    require_role(user, _SUPERVISOR_ROLES | {"technician"})
    sync_notifications_for_user(db, user)

    query = db.query(NotificationItem).filter(NotificationItem.user_id == user.id)
    if unread_only:
        query = query.filter(NotificationItem.read_at.is_(None))
    if not include_dismissed:
        query = query.filter(NotificationItem.dismissed_at.is_(None))

    total = query.count()
    items = (
        query.order_by(NotificationItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "items": [_to_out(n) for n in items],
    }


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    require_role(user, _SUPERVISOR_ROLES | {"technician"})
    sync_notifications_for_user(db, user)

    count = (
        db.query(NotificationItem)
        .filter(
            NotificationItem.user_id == user.id,
            NotificationItem.read_at.is_(None),
            NotificationItem.dismissed_at.is_(None),
        )
        .count()
    )
    return {"unread_count": count}


@router.post("/sync")
def force_sync(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    require_role(user, _SUPERVISOR_ROLES | {"technician"})
    created = sync_notifications_for_user(db, user)
    return {"created": created}


@router.post("/{notification_id:int}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    notif = db.query(NotificationItem).filter(NotificationItem.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    if notif.user_id != user.id:
        raise HTTPException(status_code=403, detail="Notification d'un autre utilisateur.")
    if notif.read_at is None:
        notif.read_at = datetime.utcnow()
        db.commit()
    return _to_out(notif)


@router.post("/mark-all-read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    require_role(user, _SUPERVISOR_ROLES | {"technician"})
    now = datetime.utcnow()
    updated = (
        db.query(NotificationItem)
        .filter(NotificationItem.user_id == user.id, NotificationItem.read_at.is_(None))
        .update({NotificationItem.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return {"marked_read": updated}


@router.post("/{notification_id:int}/dismiss")
def dismiss(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    notif = db.query(NotificationItem).filter(NotificationItem.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    if notif.user_id != user.id:
        raise HTTPException(status_code=403, detail="Notification d'un autre utilisateur.")
    if notif.dismissed_at is None:
        notif.dismissed_at = datetime.utcnow()
        if notif.read_at is None:
            notif.read_at = notif.dismissed_at
        db.commit()
    return _to_out(notif)
