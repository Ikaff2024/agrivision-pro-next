"""
Audit trail consolide CacaoGuard.

Reconstruit une chronologie unique a partir des sources existantes
(sans introduire de double ecriture) :
- PrivacyAccessLog : actions utilisateurs deja loguees
- RemediationPlan  : transitions formelles (created, approved, completed)
- Alert            : cycle de vie (created, escalated, resolved)
- TraceabilityBlock: blocs (created, resolved)
- Child            : creation et derniere MAJ

Endpoint :
- GET /cacaoguard/reports/audit-trail

Filtres :
- from_date / to_date    : bornage chronologique
- user_id                : actions d'un utilisateur particulier
- entity_type            : "child" | "remediation_plans" | "alerts"
                           | "traceability_blocks" | "complaints"
- category               : "access" | "remediation" | "alert"
                           | "compliance" | "child"
- limit / skip           : pagination
"""
from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.db.models_social import (
    Alert,
    AlertStatus,
    Child,
    PrivacyAccessLog,
    RemediationPlan,
    RemediationStatus,
    TraceabilityBlock,
)
from app.api.cacaoguard_ops_routes import (
    get_optional_current_user,
    record_privacy_access,
    require_role,
)

router = APIRouter(prefix="/cacaoguard/reports", tags=["CacaoGuard - audit trail"])


CATEGORY_BY_ENTITY = {
    "children": "child",
    "remediation_plans": "remediation",
    "alerts": "alert",
    "traceability_blocks": "compliance",
    "complaints": "compliance",
}


def _to_dt(d: Optional[date], end_of_day: bool = False) -> Optional[datetime]:
    if d is None:
        return None
    return datetime.combine(d, time.max if end_of_day else time.min)


def _ev(
    *,
    timestamp: Optional[datetime],
    category: str,
    action: str,
    entity_type: str,
    entity_id: int,
    source: str,
    entity_reference: Optional[str] = None,
    user_id: Optional[int] = None,
    user_role: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    if timestamp is None:
        return None
    return {
        "timestamp": timestamp,
        "category": category,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_reference": entity_reference,
        "user_id": user_id,
        "user_role": user_role,
        "metadata": metadata or {},
        "source": source,
    }


def _collect_privacy_logs(
    db: Session,
    *,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
    user_id: Optional[int],
    entity_type: Optional[str],
) -> List[dict]:
    query = db.query(PrivacyAccessLog)
    if from_dt:
        query = query.filter(PrivacyAccessLog.created_at >= from_dt)
    if to_dt:
        query = query.filter(PrivacyAccessLog.created_at <= to_dt)
    if user_id is not None:
        query = query.filter(PrivacyAccessLog.user_id == user_id)
    if entity_type:
        query = query.filter(PrivacyAccessLog.source_entity == entity_type)
    out = []
    for log in query.all():
        event = _ev(
            timestamp=log.created_at,
            category=CATEGORY_BY_ENTITY.get(log.source_entity, "access"),
            action=log.action,
            entity_type=log.source_entity,
            entity_id=log.source_id or 0,
            source="privacy_log",
            user_id=log.user_id,
            user_role=log.user_role,
            metadata={
                "redacted": log.redacted,
                **(log.access_metadata or {}),
            },
        )
        if event:
            out.append(event)
    return out


def _collect_remediation_plan_events(
    db: Session,
    *,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
    entity_type: Optional[str],
) -> List[dict]:
    if entity_type and entity_type != "remediation_plans":
        return []
    plans = db.query(RemediationPlan).all()
    out: List[dict] = []
    for plan in plans:
        # Creation
        if plan.created_at:
            evt = _ev(
                timestamp=plan.created_at,
                category="remediation",
                action="plan_created",
                entity_type="remediation_plans",
                entity_id=plan.id,
                entity_reference=plan.plan_reference,
                source="remediation_plan",
                user_id=plan.created_by,
                metadata={
                    "child_id": plan.child_id,
                    "producer_id": plan.producer_id,
                    "priority": plan.priority.value if plan.priority else None,
                    "status": plan.status.value if plan.status else None,
                },
            )
            if evt:
                out.append(evt)
        # Approbation
        if plan.approved_at:
            out.append(_ev(
                timestamp=plan.approved_at,
                category="remediation",
                action="plan_approved",
                entity_type="remediation_plans",
                entity_id=plan.id,
                entity_reference=plan.plan_reference,
                source="remediation_plan",
                user_id=plan.approved_by,
                metadata={"approval_comments": plan.approval_comments},
            ))
        # Cloture (utilise actual_completion_date comme date jour)
        if plan.actual_completion_date and plan.status in (
            RemediationStatus.COMPLETED, RemediationStatus.CLOSED,
        ):
            out.append(_ev(
                timestamp=datetime.combine(plan.actual_completion_date, time(12, 0)),
                category="remediation",
                action="plan_completed" if plan.status == RemediationStatus.COMPLETED else "plan_closed",
                entity_type="remediation_plans",
                entity_id=plan.id,
                entity_reference=plan.plan_reference,
                source="remediation_plan",
                metadata={"outcome": plan.outcome, "description": plan.outcome_description},
            ))

    # Filtrage temporel
    return [e for e in out if e and _in_range(e["timestamp"], from_dt, to_dt)]


def _collect_alert_events(
    db: Session,
    *,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
    entity_type: Optional[str],
) -> List[dict]:
    if entity_type and entity_type != "alerts":
        return []
    alerts = db.query(Alert).all()
    out: List[dict] = []
    for alert in alerts:
        if alert.created_at:
            out.append(_ev(
                timestamp=alert.created_at,
                category="alert",
                action=f"alert_created_{alert.alert_type.value}" if alert.alert_type else "alert_created",
                entity_type="alerts",
                entity_id=alert.id,
                source="alert",
                metadata={
                    "priority": alert.priority.value if alert.priority else None,
                    "source_entity": alert.source_entity,
                    "source_id": alert.source_id,
                    "title": alert.title,
                },
            ))
        if alert.escalated_at:
            out.append(_ev(
                timestamp=alert.escalated_at,
                category="alert",
                action="alert_escalated",
                entity_type="alerts",
                entity_id=alert.id,
                source="alert",
                user_id=alert.escalated_to,
                metadata={
                    "escalation_level": alert.escalation_level or 0,
                    "priority": alert.priority.value if alert.priority else None,
                },
            ))
        if alert.resolved_at and alert.status == AlertStatus.RESOLVED:
            out.append(_ev(
                timestamp=alert.resolved_at,
                category="alert",
                action="alert_resolved",
                entity_type="alerts",
                entity_id=alert.id,
                source="alert",
                metadata={"source_entity": alert.source_entity},
            ))
    return [e for e in out if e and _in_range(e["timestamp"], from_dt, to_dt)]


def _collect_block_events(
    db: Session,
    *,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
    entity_type: Optional[str],
) -> List[dict]:
    if entity_type and entity_type != "traceability_blocks":
        return []
    blocks = db.query(TraceabilityBlock).all()
    out: List[dict] = []
    for block in blocks:
        if block.created_at:
            out.append(_ev(
                timestamp=block.created_at,
                category="compliance",
                action="traceability_block_created",
                entity_type="traceability_blocks",
                entity_id=block.id,
                source="traceability_block",
                user_id=block.blocked_by,
                metadata={
                    "producer_id": block.producer_id,
                    "reason": block.block_reason.value if block.block_reason else None,
                    "related_case_id": block.related_case_id,
                },
            ))
        if block.actual_resolution_date:
            out.append(_ev(
                timestamp=datetime.combine(block.actual_resolution_date, time(12, 0)),
                category="compliance",
                action="traceability_block_resolved",
                entity_type="traceability_blocks",
                entity_id=block.id,
                source="traceability_block",
                metadata={
                    "producer_id": block.producer_id,
                    "resolution_notes": block.resolution_notes,
                },
            ))
    return [e for e in out if e and _in_range(e["timestamp"], from_dt, to_dt)]


def _collect_child_events(
    db: Session,
    *,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
    entity_type: Optional[str],
) -> List[dict]:
    if entity_type and entity_type != "children":
        return []
    children = db.query(Child).all()
    out: List[dict] = []
    for child in children:
        if child.created_at:
            out.append(_ev(
                timestamp=child.created_at,
                category="child",
                action="child_created",
                entity_type="children",
                entity_id=child.id,
                source="child",
                user_id=child.created_by,
                metadata={
                    "producer_id": child.producer_id,
                    "risk_level": child.risk_level.value if child.risk_level else None,
                    "risk_score": float(child.risk_score or 0),
                    "is_active": child.is_active,
                },
            ))
        # Si updated_at distinct de created_at, on log une MAJ
        if child.updated_at and (
            child.created_at is None or child.updated_at != child.created_at
        ):
            out.append(_ev(
                timestamp=child.updated_at,
                category="child",
                action="child_updated",
                entity_type="children",
                entity_id=child.id,
                source="child",
                metadata={
                    "risk_level": child.risk_level.value if child.risk_level else None,
                    "risk_score": float(child.risk_score or 0),
                    "is_active": child.is_active,
                },
            ))
    return [e for e in out if e and _in_range(e["timestamp"], from_dt, to_dt)]


def _in_range(dt: datetime, from_dt: Optional[datetime], to_dt: Optional[datetime]) -> bool:
    # Normalise les naive vs aware : on compare en naive
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    if from_dt and dt < from_dt:
        return False
    if to_dt and dt > to_dt:
        return False
    return True


@router.get("/audit-trail")
def get_audit_trail(
    from_date: Optional[date] = Query(None, description="Borne basse incluse"),
    to_date: Optional[date] = Query(None, description="Borne haute incluse (fin de journee)"),
    user_id: Optional[int] = Query(None, description="Filtre actions d'un utilisateur"),
    entity_type: Optional[str] = Query(
        None,
        description="children | remediation_plans | alerts | traceability_blocks | complaints",
    ),
    category: Optional[str] = Query(
        None,
        description="access | remediation | alert | compliance | child",
    ),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Retourne la chronologie consolidee des evenements CacaoGuard.

    Reservee aux admin/agronomist (acces aux donnees sensibles).
    Trace l'acces dans PrivacyAccessLog.
    """
    require_role(current_user, {"admin", "agronomist"})

    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date doit etre <= to_date.")

    from_dt = _to_dt(from_date)
    to_dt = _to_dt(to_date, end_of_day=True)

    events: List[dict] = []
    events.extend(_collect_privacy_logs(
        db, from_dt=from_dt, to_dt=to_dt, user_id=user_id, entity_type=entity_type,
    ))
    events.extend(_collect_remediation_plan_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=entity_type,
    ))
    events.extend(_collect_alert_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=entity_type,
    ))
    events.extend(_collect_block_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=entity_type,
    ))
    events.extend(_collect_child_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=entity_type,
    ))

    if category:
        events = [e for e in events if e["category"] == category]
    if user_id is not None:
        events = [e for e in events if e.get("user_id") == user_id]

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    total = len(events)
    page = events[skip:skip + limit]

    record_privacy_access(
        db,
        current_user,
        action="view_audit_trail",
        source_entity="audit_trail",
        metadata={
            "from_date": str(from_date) if from_date else None,
            "to_date": str(to_date) if to_date else None,
            "filters": {
                "user_id": user_id,
                "entity_type": entity_type,
                "category": category,
            },
            "total": total,
            "returned": len(page),
        },
    )
    db.commit()

    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "filters": {
            "from_date": from_date,
            "to_date": to_date,
            "user_id": user_id,
            "entity_type": entity_type,
            "category": category,
        },
        "events": page,
    }


@router.get("/audit-trail/summary")
def get_audit_trail_summary(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """KPIs agreges pour les rapports superviseur."""
    require_role(current_user, {"admin", "agronomist"})

    from_dt = _to_dt(from_date)
    to_dt = _to_dt(to_date, end_of_day=True)

    all_events: List[dict] = []
    all_events.extend(_collect_privacy_logs(
        db, from_dt=from_dt, to_dt=to_dt, user_id=None, entity_type=None,
    ))
    all_events.extend(_collect_remediation_plan_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=None,
    ))
    all_events.extend(_collect_alert_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=None,
    ))
    all_events.extend(_collect_block_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=None,
    ))
    all_events.extend(_collect_child_events(
        db, from_dt=from_dt, to_dt=to_dt, entity_type=None,
    ))

    by_category: dict = {}
    by_action: dict = {}
    by_user: dict = {}
    for e in all_events:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
        if e.get("user_id"):
            by_user[e["user_id"]] = by_user.get(e["user_id"], 0) + 1

    return {
        "from_date": from_date,
        "to_date": to_date,
        "total_events": len(all_events),
        "by_category": by_category,
        "by_action": by_action,
        "by_user_id": by_user,
    }
