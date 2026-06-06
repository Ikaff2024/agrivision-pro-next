from datetime import date, datetime, timedelta
import hashlib
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FarmForceAssessment, Producer, User
from app.auth.auth_service import decode_token
from app.db.models_social import (
    ActionType,
    ActionStatus,
    Alert,
    AlertStatus,
    AlertType,
    BlockReason,
    BlockStatus,
    Child,
    MonitoringVisit,
    Priority,
    PrivacyAccessLog,
    RemediationAction,
    RemediationPlan,
    RemediationStatus,
    RiskLevel,
    SchoolStatus,
    SsrteCommunityProfile,
    SsrteHouseholdProfile,
    SsrtePlantationVisit,
    TrainingSession,
    TrainingStatus,
    TrainingType,
    TraceabilityBlock,
    VisitStatus,
    VisitType,
)
from app.db.models import Harvest, Plantation
from app.services.reports import cacaoguard_report_filename, generate_cacaoguard_pdf
from app.services.social_scope import coop_alert_ids, coop_producer_ids

router = APIRouter(tags=["CacaoGuard - operations terrain"])
optional_bearer = HTTPBearer(auto_error=False)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token type invalide.")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur invalide.")
    return user


def require_role(user: User | None, allowed: set[str]) -> None:
    if user is not None and user.role not in allowed:
        raise HTTPException(status_code=403, detail="Acces CacaoGuard non autorise pour ce role.")


def can_view_sensitive(user: User | None) -> bool:
    return user is None or user.role in {"admin", "agronomist"}


def _coop_id_of(user: User | None) -> Optional[int]:
    return user.cooperative_id if user else None


def _in_coop_producers(db: Session, current_user: User | None, producer_id: Optional[int]) -> bool:
    """Cloisonnement : producer_id appartient-il à la coop de l'utilisateur ?

    Cohérent avec build_due_diligence_report : coop None ⇒ pas de scoping
    (accès anonyme/interne), coop définie ⇒ filtrage strict.
    """
    coop_id = _coop_id_of(current_user)
    if coop_id is None:
        return True
    return producer_id in coop_producer_ids(db, coop_id)


def record_privacy_access(
    db: Session,
    user: User | None,
    *,
    action: str,
    source_entity: str,
    source_id: int | None = None,
    redacted: bool = False,
    metadata: dict | None = None,
) -> None:
    db.add(PrivacyAccessLog(
        user_id=user.id if user else None,
        user_role=user.role if user else "anonymous_demo",
        action=action,
        source_entity=source_entity,
        source_id=source_id,
        redacted=redacted,
        access_metadata=metadata or {},
    ))


def privacy_log_to_dict(log: PrivacyAccessLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "user_role": log.user_role,
        "action": log.action,
        "source_entity": log.source_entity,
        "source_id": log.source_id,
        "redacted": bool(log.redacted),
        "metadata": log.access_metadata or {},
        "created_at": log.created_at,
    }


def _stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_signature(signature: Optional[dict], *, role: str, consent_given: bool, visit_payload: dict) -> Optional[dict]:
    if not signature:
        return None
    signed_by = signature.get("signed_by") or signature.get("name") or signature.get("signature_text")
    if not signed_by:
        return None
    signed_at = signature.get("signed_at") or datetime.utcnow().isoformat()
    evidence = {
        "role": role,
        "signed_by": signed_by,
        "signed_at": signed_at,
        "consent_given": consent_given,
        "device_id": signature.get("device_id") or signature.get("device") or "unknown_device",
        "method": signature.get("method") or "typed_name",
        "app_context": "AgriVision Pro CacaoGuard",
    }
    evidence["payload_hash"] = _stable_hash({
        "role": role,
        "signed_by": signed_by,
        "signed_at": signed_at,
        "visit_payload": visit_payload,
    })
    return evidence


def _first_user_id(db: Session) -> int:
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=400, detail="Aucun utilisateur disponible.")
    return user.id


def _producer_name(producer: Producer | None) -> str:
    return producer.nom_complet if producer else "Producteur inconnu"


def _child_name(child: Child | None) -> str:
    return f"{child.first_name} {child.last_name}" if child else "Enfant inconnu"


def _risk_priority(level: RiskLevel) -> Priority:
    if level == RiskLevel.CRITICAL:
        return Priority.URGENT
    if level == RiskLevel.HIGH:
        return Priority.HIGH
    return Priority.MEDIUM


def _plan_reference(db: Session) -> str:
    count = db.query(RemediationPlan).count() + 1
    return f"REM-{date.today().year}-{count:04d}"


class MonitoringVisitCreate(BaseModel):
    producer_id: int
    scheduled_date: date
    visit_type: VisitType = VisitType.ROUTINE
    priority: Priority = Priority.MEDIUM
    lead_assessor_id: Optional[int] = None
    visit_location: Optional[str] = Field(None, max_length=255)
    gps_accuracy: Optional[float] = None
    checklist_data: dict = Field(default_factory=dict)
    observations: Optional[str] = None
    dangerous_tasks_observed: Optional[List[str]] = None
    immediate_actions_taken: Optional[str] = None
    photos: Optional[List[dict]] = None
    consent_given: bool = False
    producer_signature_data: Optional[dict] = None
    assessor_signature_data: Optional[dict] = None


class MonitoringVisitComplete(BaseModel):
    actual_date: date = Field(default_factory=date.today)
    visit_location: Optional[str] = Field(None, max_length=255)
    gps_accuracy: Optional[float] = None
    checklist_data: dict = Field(default_factory=dict)
    observations: Optional[str] = None
    dangerous_tasks_observed: Optional[List[str]] = None
    immediate_actions_taken: Optional[str] = None
    photos: Optional[List[dict]] = None
    consent_given: bool = False
    producer_signature_data: Optional[dict] = None
    assessor_signature_data: Optional[dict] = None


class RemediationPlanCreate(BaseModel):
    child_id: int
    priority: Optional[Priority] = None
    main_objective: Optional[str] = None
    planned_actions: Optional[List[dict]] = None
    case_worker_id: Optional[int] = None
    expected_completion_date: Optional[date] = None


class RemediationProgressCreate(BaseModel):
    note: str = Field(..., min_length=2)
    status: Optional[RemediationStatus] = None
    resources_provided: Optional[dict] = None


class TraceabilityBlockCreate(BaseModel):
    producer_id: int
    block_reason: BlockReason = BlockReason.CHILD_LABOR_CASE
    block_description: str = Field(..., min_length=4)
    related_case_id: Optional[int] = None
    expected_resolution_date: Optional[date] = None
    affected_batches: Optional[List[dict]] = None


class TraceabilityResolve(BaseModel):
    resolution_notes: str = Field(..., min_length=4)


class TrainingSessionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    training_type: TrainingType = TrainingType.CHILD_PROTECTION
    scheduled_date: date
    location: str = Field(..., min_length=2, max_length=200)
    village: Optional[str] = Field(None, max_length=100)
    trainer_id: Optional[int] = None
    trainer_organization: Optional[str] = Field(None, max_length=200)
    expected_participants: int = Field(0, ge=0)
    topics_covered: Optional[List[str]] = None
    materials_used: Optional[dict] = None


class TrainingAttendanceUpdate(BaseModel):
    participants: List[dict] = Field(default_factory=list)
    post_test_scores: Optional[dict] = None
    effectiveness_rating: Optional[float] = Field(None, ge=0, le=5)
    status: TrainingStatus = TrainingStatus.COMPLETED


def alert_to_dict(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type.value,
        "priority": alert.priority.value,
        "source_entity": alert.source_entity,
        "source_id": alert.source_id,
        "title": alert.title,
        "message": alert.message,
        "status": alert.status.value,
        "assigned_to": alert.assigned_to,
        "escalation_level": alert.escalation_level or 0,
        "escalated_to": alert.escalated_to,
        "escalated_at": alert.escalated_at,
        "notifications_sent": alert.notifications_sent or {},
        "metadata": alert.alert_metadata or {},
        "created_at": alert.created_at,
    }


def visit_to_dict(visit: MonitoringVisit, include_sensitive: bool = True) -> dict:
    data = {
        "id": visit.id,
        "producer_id": visit.producer_id,
        "producer_name": _producer_name(visit.producer),
        "scheduled_date": visit.scheduled_date,
        "actual_date": visit.actual_date,
        "visit_type": visit.visit_type.value,
        "priority": visit.priority.value,
        "visit_location": visit.visit_location,
        "gps_accuracy": visit.gps_accuracy,
        "checklist_data": visit.checklist_data or {},
        "checklist_score": float(visit.checklist_score or 0),
        "observations": visit.observations,
        "photos": visit.photos or [],
        "dangerous_tasks_observed": visit.dangerous_tasks_observed or [],
        "immediate_actions_taken": visit.immediate_actions_taken,
        "consent_given": bool((visit.checklist_data or {}).get("consent_given")),
        "producer_signature_data": visit.producer_signature_data or {},
        "assessor_signature_data": visit.assessor_signature_data or {},
        "status": visit.status.value,
        "created_at": visit.created_at,
    }
    if not include_sensitive:
        data.update({
            "visit_location": "Masque",
            "gps_accuracy": None,
            "photos": [],
            "producer_signature_data": {},
            "assessor_signature_data": {},
            "privacy_redacted": True,
        })
    else:
        data["privacy_redacted"] = False
    return data


def plan_to_dict(plan: RemediationPlan) -> dict:
    return {
        "id": plan.id,
        "producer_id": plan.producer_id,
        "producer_name": _producer_name(plan.producer),
        "child_id": plan.child_id,
        "child_name": _child_name(plan.child),
        "plan_reference": plan.plan_reference,
        "status": plan.status.value,
        "priority": plan.priority.value,
        "main_objective": plan.main_objective,
        "success_criteria": plan.success_criteria or [],
        "planned_actions": plan.planned_actions or [],
        "start_date": plan.start_date,
        "expected_completion_date": plan.expected_completion_date,
        "budget_allocated": float(plan.budget_allocated or 0),
        "resources_provided": plan.resources_provided or {},
        "monthly_progress": plan.monthly_progress or [],
        "outcome": plan.outcome,
        "created_at": plan.created_at,
        "actions": [
            {
                "id": action.id,
                "action_type": action.action_type.value,
                "description": action.description,
                "planned_date": action.planned_date,
                "completed_date": action.completed_date,
                "status": action.status.value,
                "notes": action.notes,
            }
            for action in plan.actions
        ],
    }


def block_to_dict(block: TraceabilityBlock) -> dict:
    harvests = (
        block.affected_batches
        if block.affected_batches is not None
        else []
    )
    return {
        "id": block.id,
        "producer_id": block.producer_id,
        "producer_name": _producer_name(block.producer),
        "block_reason": block.block_reason.value,
        "block_description": block.block_description,
        "related_case_id": block.related_case_id,
        "affects_all_production": block.affects_all_production,
        "affected_batches": harvests,
        "block_start_date": block.block_start_date,
        "expected_resolution_date": block.expected_resolution_date,
        "actual_resolution_date": block.actual_resolution_date,
        "status": block.status.value,
        "resolution_notes": block.resolution_notes,
        "created_at": block.created_at,
    }


def training_to_dict(session: TrainingSession) -> dict:
    participants = session.participants or []
    post_scores = session.post_test_scores or {}
    return {
        "id": session.id,
        "title": session.title,
        "description": session.description,
        "training_type": session.training_type.value,
        "scheduled_date": session.scheduled_date,
        "location": session.location,
        "village": session.village,
        "trainer_organization": session.trainer_organization,
        "expected_participants": session.expected_participants or 0,
        "actual_participants": session.actual_participants or len(participants),
        "participants": participants,
        "materials_used": session.materials_used or {},
        "topics_covered": session.topics_covered or [],
        "pre_test_scores": session.pre_test_scores or {},
        "post_test_scores": post_scores,
        "effectiveness_rating": float(session.effectiveness_rating or 0),
        "status": session.status.value,
        "created_at": session.created_at,
    }


def detect_cacaoguard_inconsistencies(db: Session, cooperative_id: int | None = None) -> list[dict]:
    findings: list[dict] = []
    child_q = db.query(Child).filter(Child.is_active == True)
    psub = _coop_producer_subq(db, cooperative_id)
    if psub is not None:
        child_q = child_q.filter(Child.producer_id.in_(psub))
    children = child_q.all()
    for child in children:
        latest_visit = db.query(MonitoringVisit).filter(
            MonitoringVisit.producer_id == child.producer_id,
            MonitoringVisit.status == VisitStatus.COMPLETED,
        ).order_by(MonitoringVisit.actual_date.desc().nullslast(), MonitoringVisit.created_at.desc()).first()
        checklist = latest_visit.checklist_data if latest_visit else {}
        observed_tasks = latest_visit.dangerous_tasks_observed if latest_visit else []

        if child.school_status == SchoolStatus.ENROLLED and child.is_working_on_farm and child.work_frequency.value in {"regular", "daily"}:
            findings.append({
                "severity": "high",
                "code": "school_work_conflict",
                "entity": "children",
                "entity_id": child.id,
                "producer_id": child.producer_id,
                "message": f"{_child_name(child)} est declare scolarise mais travaille regulierement sur la ferme.",
            })
        if child.school_status == SchoolStatus.ENROLLED and observed_tasks:
            findings.append({
                "severity": "critical",
                "code": "school_dangerous_tasks_observed",
                "entity": "children",
                "entity_id": child.id,
                "producer_id": child.producer_id,
                "message": f"{_child_name(child)} est scolarise mais une visite a releve des taches dangereuses.",
            })
        if latest_visit and checklist and checklist.get("children_observed") and not child.is_working_on_farm and child.risk_level in (RiskLevel.NONE, RiskLevel.LOW):
            findings.append({
                "severity": "medium",
                "code": "visit_observation_low_declared_risk",
                "entity": "monitoring_visits",
                "entity_id": latest_visit.id,
                "producer_id": child.producer_id,
                "message": f"Enfants observes chez {_producer_name(child.producer)} alors que le risque declare reste faible.",
            })

    visits = db.query(MonitoringVisit).all()
    for visit in visits:
        photos = visit.photos or []
        consent = bool((visit.checklist_data or {}).get("consent_given"))
        if photos and not consent:
            findings.append({
                "severity": "high",
                "code": "photos_without_consent",
                "entity": "monitoring_visits",
                "entity_id": visit.id,
                "producer_id": visit.producer_id,
                "message": f"Visite chez {_producer_name(visit.producer)} avec photo(s) mais sans consentement trace.",
            })
        if visit.status == VisitStatus.COMPLETED and not visit.visit_location:
            findings.append({
                "severity": "medium",
                "code": "completed_visit_without_gps",
                "entity": "monitoring_visits",
                "entity_id": visit.id,
                "producer_id": visit.producer_id,
                "message": f"Visite terminee chez {_producer_name(visit.producer)} sans localisation GPS/lieu.",
            })
        for role, signature in (("producer", visit.producer_signature_data), ("assessor", visit.assessor_signature_data)):
            if signature and not signature.get("payload_hash"):
                findings.append({
                    "severity": "medium",
                    "code": "legacy_signature_without_hash",
                    "entity": "monitoring_visits",
                    "entity_id": visit.id,
                    "producer_id": visit.producer_id,
                    "message": f"Signature {role} de visite sans empreinte de preuve structuree.",
                })
    return findings


def ensure_inconsistency_alerts(db: Session, findings: list[dict]) -> None:
    for finding in findings:
        if finding["severity"] not in {"high", "critical"}:
            continue
        existing = db.query(Alert).filter(
            Alert.source_entity == finding["entity"],
            Alert.source_id == finding["entity_id"],
            Alert.alert_type == AlertType.AUDIT_FAILURE,
            Alert.status != AlertStatus.RESOLVED,
        ).first()
        if existing:
            existing.alert_metadata = finding
            continue
        db.add(Alert(
            source_entity=finding["entity"],
            source_id=finding["entity_id"],
            alert_type=AlertType.AUDIT_FAILURE,
            priority=Priority.URGENT if finding["severity"] == "critical" else Priority.HIGH,
            title="Incoherence CacaoGuard detectee",
            message=finding["message"],
            alert_metadata=finding,
        ))


def impacted_harvests_for_producer(db: Session, producer_id: int) -> list[dict]:
    rows = (
        db.query(Harvest, Plantation)
        .join(Plantation, Harvest.plantation_id == Plantation.id)
        .filter(Plantation.producer_id == producer_id)
        .order_by(Harvest.harvest_date.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "harvest_id": harvest.id,
            "plantation_id": plantation.id,
            "plantation_name": plantation.name,
            "harvest_date": harvest.harvest_date.isoformat() if harvest.harvest_date else None,
            "quantity_kg": harvest.quantity_kg,
            "quality": harvest.quality,
            "receipt": harvest.numero_recu_achat,
        }
        for harvest, plantation in rows
    ]


def ensure_traceability_block_for_child(db: Session, child: Child) -> Optional[TraceabilityBlock]:
    if child.risk_level != RiskLevel.CRITICAL:
        return None

    existing = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id == child.producer_id,
        TraceabilityBlock.block_reason == BlockReason.CHILD_LABOR_CASE,
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).first()
    if existing:
        return existing

    user_id = _first_user_id(db)
    block = TraceabilityBlock(
        producer_id=child.producer_id,
        block_reason=BlockReason.CHILD_LABOR_CASE,
        block_description=(
            f"Blocage automatique CacaoGuard: cas critique non resolu pour {_child_name(child)}."
        ),
        related_case_id=child.id,
        affects_all_production=True,
        affected_batches=impacted_harvests_for_producer(db, child.producer_id),
        expected_resolution_date=date.today() + timedelta(days=90),
        status=BlockStatus.ACTIVE,
        blocked_by=user_id,
    )
    db.add(block)
    db.flush()
    db.add(Alert(
        source_entity="traceability_blocks",
        source_id=block.id,
        alert_type=AlertType.TRACEABILITY_BLOCK,
        priority=Priority.URGENT,
        title="Blocage tracabilite actif",
        message=f"La production de {_producer_name(child.producer)} est bloquee jusqu'a resolution du cas.",
        alert_metadata={"child_id": child.id, "producer_id": child.producer_id},
    ))
    return block


def ensure_remediation_plan_for_child(db: Session, child: Child) -> Optional[RemediationPlan]:
    if child.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return None

    existing = db.query(RemediationPlan).filter(
        RemediationPlan.child_id == child.id,
        RemediationPlan.status.in_([
            RemediationStatus.DRAFT,
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
            RemediationStatus.IN_PROGRESS,
            RemediationStatus.ESCALATED,
        ]),
    ).first()
    if existing:
        return existing

    case_worker_id = _first_user_id(db)
    plan = RemediationPlan(
        producer_id=child.producer_id,
        child_id=child.id,
        plan_reference=_plan_reference(db),
        status=RemediationStatus.IN_PROGRESS,
        priority=_risk_priority(child.risk_level),
        main_objective="Retirer l'enfant des taches dangereuses et securiser sa scolarisation.",
        success_criteria=[
            "Aucune tache dangereuse observee",
            "Presence scolaire verifiee",
            "Suivi mensuel documente",
        ],
        planned_actions=[
            {
                "type": "education",
                "description": "Verifier inscription scolaire et assiduite",
                "deadline": str(date.today() + timedelta(days=30)),
            },
            {
                "type": "awareness",
                "description": "Sensibiliser le menage sur les taches dangereuses",
                "deadline": str(date.today() + timedelta(days=15)),
            },
            {
                "type": "economic_support",
                "description": "Evaluer besoin de kit scolaire ou soutien economique",
                "deadline": str(date.today() + timedelta(days=45)),
            },
        ],
        start_date=date.today(),
        expected_completion_date=date.today() + timedelta(days=90),
        case_worker_id=case_worker_id,
        created_by=case_worker_id,
    )
    db.add(plan)
    db.flush()

    for item in plan.planned_actions or []:
        db.add(RemediationAction(
            remediation_plan_id=plan.id,
            action_type=ActionType(item.get("type", "other")),
            description=item.get("description", "Action de remediation"),
            planned_date=date.fromisoformat(item["deadline"]) if item.get("deadline") else date.today(),
            responsible_id=case_worker_id,
        ))

    db.add(Alert(
        source_entity="remediation_plans",
        source_id=plan.id,
        alert_type=AlertType.OVERDUE_ACTION,
        priority=plan.priority,
        title="Plan de remediation ouvert",
        message=f"Un plan de remediation {plan.plan_reference} a ete ouvert pour {_child_name(child)}.",
        alert_metadata={"child_id": child.id, "producer_id": child.producer_id},
    ))
    ensure_traceability_block_for_child(db, child)
    return plan


@router.get("/monitoring/visits")
def list_visits(
    limit: int = Query(100, ge=1, le=500),
    status: Optional[VisitStatus] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(MonitoringVisit)
    psub = _coop_producer_subq(db, _coop_id_of(current_user))
    if psub is not None:
        query = query.filter(MonitoringVisit.producer_id.in_(psub))
    if status:
        query = query.filter(MonitoringVisit.status == status)
    return [
        visit_to_dict(v, can_view_sensitive(current_user))
        for v in query.order_by(MonitoringVisit.scheduled_date.desc()).limit(limit).all()
    ]


def _supervisor_id(db: Session) -> Optional[int]:
    user = db.query(User).filter(User.role.in_(["admin", "agronomist"]), User.is_active == True).first()
    return user.id if user else None


def _upsert_operational_alert(
    db: Session,
    *,
    source_entity: str,
    source_id: int,
    alert_type: AlertType,
    priority: Priority,
    title: str,
    message: str,
    metadata: dict,
    overdue_days: int,
    escalation_after_days: int,
) -> tuple[Alert, bool]:
    alert = db.query(Alert).filter(
        Alert.source_entity == source_entity,
        Alert.source_id == source_id,
        Alert.alert_type == alert_type,
        Alert.status != AlertStatus.RESOLVED,
    ).first()
    created = False
    if not alert:
        alert = Alert(
            source_entity=source_entity,
            source_id=source_id,
            alert_type=alert_type,
            priority=priority,
            title=title,
            message=message,
            alert_metadata=metadata,
            status=AlertStatus.NEW,
        )
        db.add(alert)
        db.flush()
        created = True
    else:
        alert.priority = priority
        alert.title = title
        alert.message = message
        alert.alert_metadata = metadata

    if overdue_days >= escalation_after_days:
        alert.status = AlertStatus.ESCALATED
        alert.escalation_level = max(alert.escalation_level or 0, 1)
        alert.escalated_to = alert.escalated_to or _supervisor_id(db)
        alert.escalated_at = alert.escalated_at or datetime.utcnow()
        notifications = dict(alert.notifications_sent or {})
        notifications.setdefault("system", [])
        marker = f"escalation:{date.today().isoformat()}"
        if marker not in notifications["system"]:
            notifications["system"].append(marker)
        alert.notifications_sent = notifications

    return alert, created


def run_cacaoguard_alert_checks(db: Session, escalation_after_days: int = 7) -> dict:
    today = date.today()
    created = 0
    escalated = 0
    reviewed = 0
    generated_alerts = []

    overdue_visits = db.query(MonitoringVisit).filter(
        MonitoringVisit.status.in_([VisitStatus.SCHEDULED, VisitStatus.IN_PROGRESS]),
        MonitoringVisit.scheduled_date < today,
    ).all()
    for visit in overdue_visits:
        overdue_days = (today - visit.scheduled_date).days
        alert, was_created = _upsert_operational_alert(
            db,
            source_entity="monitoring_visits",
            source_id=visit.id,
            alert_type=AlertType.MISSED_VISIT,
            priority=Priority.URGENT if overdue_days >= escalation_after_days else Priority.HIGH,
            title="Visite de monitoring en retard",
            message=f"La visite chez {_producer_name(visit.producer)} est en retard de {overdue_days} jour(s).",
            metadata={"producer_id": visit.producer_id, "scheduled_date": str(visit.scheduled_date), "overdue_days": overdue_days},
            overdue_days=overdue_days,
            escalation_after_days=escalation_after_days,
        )
        reviewed += 1
        created += 1 if was_created else 0
        escalated += 1 if alert.status == AlertStatus.ESCALATED else 0
        generated_alerts.append(alert)

    active_plan_statuses = [
        RemediationStatus.DRAFT,
        RemediationStatus.PENDING_APPROVAL,
        RemediationStatus.APPROVED,
        RemediationStatus.IN_PROGRESS,
        RemediationStatus.ESCALATED,
    ]
    overdue_plans = db.query(RemediationPlan).filter(
        RemediationPlan.status.in_(active_plan_statuses),
        RemediationPlan.expected_completion_date.isnot(None),
        RemediationPlan.expected_completion_date < today,
    ).all()
    for plan in overdue_plans:
        overdue_days = (today - plan.expected_completion_date).days
        if overdue_days >= escalation_after_days:
            plan.status = RemediationStatus.ESCALATED
        alert, was_created = _upsert_operational_alert(
            db,
            source_entity="remediation_plans",
            source_id=plan.id,
            alert_type=AlertType.OVERDUE_ACTION,
            priority=Priority.URGENT if overdue_days >= escalation_after_days else Priority.HIGH,
            title="Plan de remediation en retard",
            message=f"Le plan {plan.plan_reference} pour {_child_name(plan.child)} est en retard de {overdue_days} jour(s).",
            metadata={"producer_id": plan.producer_id, "child_id": plan.child_id, "plan_reference": plan.plan_reference, "overdue_days": overdue_days},
            overdue_days=overdue_days,
            escalation_after_days=escalation_after_days,
        )
        reviewed += 1
        created += 1 if was_created else 0
        escalated += 1 if alert.status == AlertStatus.ESCALATED else 0
        generated_alerts.append(alert)

    overdue_actions = db.query(RemediationAction).join(RemediationPlan).filter(
        RemediationAction.status.in_([ActionStatus.PENDING, ActionStatus.IN_PROGRESS, ActionStatus.OVERDUE]),
        RemediationAction.planned_date < today,
    ).all()
    for action in overdue_actions:
        overdue_days = (today - action.planned_date).days
        action.status = ActionStatus.OVERDUE
        plan = action.remediation_plan
        alert, was_created = _upsert_operational_alert(
            db,
            source_entity="remediation_actions",
            source_id=action.id,
            alert_type=AlertType.OVERDUE_ACTION,
            priority=Priority.URGENT if overdue_days >= escalation_after_days else Priority.HIGH,
            title="Action de remediation en retard",
            message=f"L'action '{action.description}' du plan {plan.plan_reference} est en retard de {overdue_days} jour(s).",
            metadata={"plan_id": plan.id, "producer_id": plan.producer_id, "child_id": plan.child_id, "overdue_days": overdue_days},
            overdue_days=overdue_days,
            escalation_after_days=escalation_after_days,
        )
        reviewed += 1
        created += 1 if was_created else 0
        escalated += 1 if alert.status == AlertStatus.ESCALATED else 0
        generated_alerts.append(alert)

    overdue_blocks = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.status == BlockStatus.ACTIVE,
        TraceabilityBlock.expected_resolution_date.isnot(None),
        TraceabilityBlock.expected_resolution_date < today,
    ).all()
    for block in overdue_blocks:
        overdue_days = (today - block.expected_resolution_date).days
        if overdue_days >= escalation_after_days:
            block.status = BlockStatus.ESCALATED
        alert, was_created = _upsert_operational_alert(
            db,
            source_entity="traceability_blocks",
            source_id=block.id,
            alert_type=AlertType.TRACEABILITY_BLOCK,
            priority=Priority.URGENT,
            title="Blocage tracabilite a escalader",
            message=f"Le blocage de {_producer_name(block.producer)} depasse son echeance de {overdue_days} jour(s).",
            metadata={"producer_id": block.producer_id, "block_id": block.id, "overdue_days": overdue_days},
            overdue_days=overdue_days,
            escalation_after_days=escalation_after_days,
        )
        reviewed += 1
        created += 1 if was_created else 0
        escalated += 1 if alert.status == AlertStatus.ESCALATED else 0
        generated_alerts.append(alert)

    db.commit()
    return {
        "checked_at": datetime.utcnow().isoformat(),
        "reviewed_items": reviewed,
        "created_alerts": created,
        "escalated_alerts": escalated,
        "alerts": [alert_to_dict(alert) for alert in generated_alerts],
    }


@router.get("/alerts")
def list_operational_alerts(
    unresolved_only: bool = True,
    limit: int = Query(50, ge=1, le=200),
    source_entity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    query = db.query(Alert)
    coop_id = _coop_id_of(current_user)
    if coop_id is not None:
        allowed = coop_alert_ids(db, coop_id)
        query = query.filter(Alert.id.in_(allowed if allowed else [-1]))
    if unresolved_only:
        query = query.filter(Alert.status != AlertStatus.RESOLVED)
    if source_entity:
        query = query.filter(Alert.source_entity == source_entity)
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [alert_to_dict(alert) for alert in alerts]


@router.get("/privacy/access-logs")
def list_privacy_access_logs(
    limit: int = Query(100, ge=1, le=500),
    source_entity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    query = db.query(PrivacyAccessLog)
    coop_id = _coop_id_of(current_user)
    if coop_id is not None:
        coop_user_ids = [i for (i,) in db.query(User.id).filter(User.cooperative_id == coop_id).all()]
        query = query.filter(PrivacyAccessLog.user_id.in_(coop_user_ids if coop_user_ids else [-1]))
    if source_entity:
        query = query.filter(PrivacyAccessLog.source_entity == source_entity)
    logs = query.order_by(PrivacyAccessLog.created_at.desc()).limit(limit).all()
    return [privacy_log_to_dict(log) for log in logs]


@router.get("/ai/inconsistencies")
def list_ai_inconsistencies(
    create_alerts: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    findings = detect_cacaoguard_inconsistencies(db, _coop_id_of(current_user))
    if create_alerts:
        ensure_inconsistency_alerts(db, findings)
        db.commit()
    return {
        "engine": "CacaoGuard lightweight consistency checks",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(findings),
        "findings": findings,
    }


@router.post("/alerts/run-checks")
def run_alert_checks_endpoint(
    escalation_after_days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    return run_cacaoguard_alert_checks(db, escalation_after_days=escalation_after_days)


@router.post("/monitoring/visits", status_code=201)
def create_visit(
    data: MonitoringVisitCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    producer = db.query(Producer).filter(Producer.id == data.producer_id).first()
    if not producer or not _in_coop_producers(db, current_user, producer.id):
        raise HTTPException(status_code=404, detail="Producteur non trouve.")

    assessor_id = data.lead_assessor_id or _first_user_id(db)
    checklist_score = min(sum(1 for value in data.checklist_data.values() if value), 100)
    checklist_data = dict(data.checklist_data or {})
    checklist_data["consent_given"] = data.consent_given
    visit_payload = {
        "producer_id": producer.id,
        "scheduled_date": data.scheduled_date,
        "visit_location": data.visit_location,
        "checklist_data": checklist_data,
        "observations": data.observations,
        "photos": data.photos or [],
    }
    visit = MonitoringVisit(
        producer_id=producer.id,
        scheduled_date=data.scheduled_date,
        visit_type=data.visit_type,
        priority=data.priority,
        lead_assessor_id=assessor_id,
        visit_location=data.visit_location,
        gps_accuracy=data.gps_accuracy,
        checklist_data=checklist_data,
        checklist_score=checklist_score,
        observations=data.observations,
        photos=data.photos,
        dangerous_tasks_observed=data.dangerous_tasks_observed,
        immediate_actions_taken=data.immediate_actions_taken,
        producer_signature_data=normalize_signature(data.producer_signature_data, role="producer", consent_given=data.consent_given, visit_payload=visit_payload),
        assessor_signature_data=normalize_signature(data.assessor_signature_data, role="assessor", consent_given=data.consent_given, visit_payload=visit_payload),
        status=VisitStatus.SCHEDULED,
        created_by=assessor_id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit_to_dict(visit)


@router.post("/monitoring/visits/{visit_id:int}/complete")
def complete_visit(
    visit_id: int,
    data: MonitoringVisitComplete,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    visit = db.query(MonitoringVisit).filter(MonitoringVisit.id == visit_id).first()
    if not visit or not _in_coop_producers(db, current_user, visit.producer_id):
        raise HTTPException(status_code=404, detail="Visite non trouvee.")

    visit.actual_date = data.actual_date
    visit.visit_location = data.visit_location or visit.visit_location
    visit.gps_accuracy = data.gps_accuracy if data.gps_accuracy is not None else visit.gps_accuracy
    checklist_data = dict(data.checklist_data or {})
    checklist_data["consent_given"] = data.consent_given
    visit_payload = {
        "visit_id": visit.id,
        "producer_id": visit.producer_id,
        "actual_date": data.actual_date,
        "visit_location": data.visit_location or visit.visit_location,
        "checklist_data": checklist_data,
        "observations": data.observations,
        "photos": data.photos or [],
        "dangerous_tasks_observed": data.dangerous_tasks_observed or [],
    }
    visit.checklist_data = checklist_data
    visit.checklist_score = min(sum(1 for value in data.checklist_data.values() if value), 100)
    visit.observations = data.observations
    visit.photos = data.photos
    visit.dangerous_tasks_observed = data.dangerous_tasks_observed
    visit.immediate_actions_taken = data.immediate_actions_taken
    visit.producer_signature_data = normalize_signature(data.producer_signature_data, role="producer", consent_given=data.consent_given, visit_payload=visit_payload)
    visit.assessor_signature_data = normalize_signature(data.assessor_signature_data, role="assessor", consent_given=data.consent_given, visit_payload=visit_payload)
    visit.status = VisitStatus.COMPLETED
    visit.completion_date = datetime.utcnow()

    if data.dangerous_tasks_observed:
        child = db.query(Child).filter(
            Child.producer_id == visit.producer_id,
            Child.is_active == True,
            Child.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
        ).order_by(Child.risk_score.desc()).first()
        if child:
            ensure_remediation_plan_for_child(db, child)

    db.commit()
    db.refresh(visit)
    return visit_to_dict(visit)


@router.get("/remediation/plans")
def list_plans(
    limit: int = Query(100, ge=1, le=500),
    status: Optional[RemediationStatus] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    query = db.query(RemediationPlan)
    psub = _coop_producer_subq(db, _coop_id_of(current_user))
    if psub is not None:
        query = query.filter(RemediationPlan.producer_id.in_(psub))
    if status:
        query = query.filter(RemediationPlan.status == status)
    return [plan_to_dict(p) for p in query.order_by(RemediationPlan.created_at.desc()).limit(limit).all()]


@router.post("/remediation/plans", status_code=201)
def create_plan(
    data: RemediationPlanCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    child = db.query(Child).filter(Child.id == data.child_id, Child.is_active == True).first()
    if not child or not _in_coop_producers(db, current_user, child.producer_id):
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    case_worker_id = data.case_worker_id or _first_user_id(db)
    planned_actions = data.planned_actions or [
        {
            "type": "education",
            "description": "Inscription ou verification scolaire",
            "deadline": str(date.today() + timedelta(days=30)),
        },
        {
            "type": "awareness",
            "description": "Sensibilisation parent/enfant",
            "deadline": str(date.today() + timedelta(days=15)),
        },
    ]
    plan = RemediationPlan(
        producer_id=child.producer_id,
        child_id=child.id,
        plan_reference=_plan_reference(db),
        status=RemediationStatus.IN_PROGRESS,
        priority=data.priority or _risk_priority(child.risk_level),
        main_objective=data.main_objective or "Resoudre le risque enfant et documenter la remediation.",
        success_criteria=["Cas resolu", "Preuves documentees", "Suivi valide par superviseur"],
        planned_actions=planned_actions,
        start_date=date.today(),
        expected_completion_date=data.expected_completion_date or date.today() + timedelta(days=90),
        case_worker_id=case_worker_id,
        created_by=case_worker_id,
    )
    db.add(plan)
    db.flush()
    for item in planned_actions:
        db.add(RemediationAction(
            remediation_plan_id=plan.id,
            action_type=ActionType(item.get("type", "other")),
            description=item.get("description", "Action de remediation"),
            planned_date=date.fromisoformat(item["deadline"]) if item.get("deadline") else date.today(),
            responsible_id=case_worker_id,
        ))
    db.commit()
    db.refresh(plan)
    return plan_to_dict(plan)


@router.post("/remediation/plans/{plan_id:int}/progress")
def add_plan_progress(
    plan_id: int,
    data: RemediationProgressCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    plan = db.query(RemediationPlan).filter(RemediationPlan.id == plan_id).first()
    if not plan or not _in_coop_producers(db, current_user, plan.producer_id):
        raise HTTPException(status_code=404, detail="Plan de remediation non trouve.")

    progress = list(plan.monthly_progress or [])
    progress.append({
        "date": str(date.today()),
        "note": data.note,
        "status": data.status.value if data.status else plan.status.value,
    })
    plan.monthly_progress = progress
    if data.status:
        plan.status = data.status
    if data.resources_provided:
        resources = dict(plan.resources_provided or {})
        resources.update(data.resources_provided)
        plan.resources_provided = resources

    db.commit()
    db.refresh(plan)
    return plan_to_dict(plan)


@router.get("/training/sessions")
def list_training_sessions(
    limit: int = Query(100, ge=1, le=500),
    status: Optional[TrainingStatus] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    query = db.query(TrainingSession)
    coop_id = _coop_id_of(current_user)
    if coop_id is not None:
        query = query.filter(TrainingSession.cooperative_id == coop_id)
    if status:
        query = query.filter(TrainingSession.status == status)
    return [
        training_to_dict(session)
        for session in query.order_by(TrainingSession.scheduled_date.desc()).limit(limit).all()
    ]


@router.post("/training/sessions", status_code=201)
def create_training_session(
    data: TrainingSessionCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    trainer_id = data.trainer_id or _first_user_id(db)
    trainer = db.query(User).filter(User.id == trainer_id).first()
    if not trainer:
        raise HTTPException(status_code=404, detail="Formateur non trouve.")

    session = TrainingSession(
        cooperative_id=_coop_id_of(current_user) or trainer.cooperative_id,
        title=data.title,
        description=data.description,
        training_type=data.training_type,
        scheduled_date=data.scheduled_date,
        location=data.location,
        village=data.village,
        trainer_id=trainer_id,
        trainer_organization=data.trainer_organization,
        expected_participants=data.expected_participants,
        actual_participants=0,
        participants=[],
        materials_used=data.materials_used or {},
        topics_covered=data.topics_covered or [],
        status=TrainingStatus.PLANNED,
        created_by=trainer_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return training_to_dict(session)


@router.post("/training/sessions/{session_id:int}/attendance")
def update_training_attendance(
    session_id: int,
    data: TrainingAttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    coop_id = _coop_id_of(current_user)
    if not session or (coop_id is not None and session.cooperative_id != coop_id):
        raise HTTPException(status_code=404, detail="Session de formation non trouvee.")

    participants = []
    for item in data.participants:
        producer_id = item.get("producer_id")
        if producer_id is not None:
            producer = db.query(Producer).filter(Producer.id == producer_id).first()
            if not producer:
                raise HTTPException(status_code=404, detail=f"Producteur {producer_id} non trouve.")
        participants.append({
            "producer_id": producer_id,
            "name": item.get("name"),
            "signature": bool(item.get("signature", False)),
            "evaluation_score": item.get("evaluation_score"),
        })

    session.participants = participants
    session.actual_participants = len(participants)
    session.post_test_scores = data.post_test_scores or {}
    session.effectiveness_rating = data.effectiveness_rating
    session.status = data.status

    db.commit()
    db.refresh(session)
    return training_to_dict(session)


@router.get("/compliance/traceability")
def get_traceability_compliance(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    psub = _coop_producer_subq(db, _coop_id_of(current_user))
    block_q = db.query(TraceabilityBlock).filter(TraceabilityBlock.status == BlockStatus.ACTIVE)
    if psub is not None:
        block_q = block_q.filter(TraceabilityBlock.producer_id.in_(psub))
    active_blocks = block_q.order_by(TraceabilityBlock.created_at.desc()).all()

    child_q = db.query(Child).filter(
        Child.is_active == True,
        Child.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
    )
    if psub is not None:
        child_q = child_q.filter(Child.producer_id.in_(psub))
    risky_children = child_q.all()
    blocked_producer_ids = {block.producer_id for block in active_blocks}
    producers_to_review = []
    for child in risky_children:
        if child.producer_id in blocked_producer_ids:
            continue
        producers_to_review.append({
            "producer_id": child.producer_id,
            "producer_name": _producer_name(child.producer),
            "child_id": child.id,
            "child_name": _child_name(child),
            "risk_level": child.risk_level.value,
            "risk_score": float(child.risk_score or 0),
        })

    impacted_batches = []
    for block in active_blocks:
        batches = block.affected_batches or impacted_harvests_for_producer(db, block.producer_id)
        for batch in batches:
            impacted_batches.append({
                **batch,
                "producer_id": block.producer_id,
                "producer_name": _producer_name(block.producer),
                "block_id": block.id,
            })

    return {
        "active_blocks": [block_to_dict(block) for block in active_blocks],
        "producers_to_review": producers_to_review,
        "impacted_batches": impacted_batches,
        "summary": {
            "active_blocks": len(active_blocks),
            "producers_to_review": len(producers_to_review),
            "impacted_batches": len(impacted_batches),
        },
    }


@router.post("/compliance/blocks", status_code=201)
def create_traceability_block(
    data: TraceabilityBlockCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    producer = db.query(Producer).filter(Producer.id == data.producer_id).first()
    if not producer or not _in_coop_producers(db, current_user, producer.id):
        raise HTTPException(status_code=404, detail="Producteur non trouve.")

    existing = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id == producer.id,
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).first()
    if existing:
        return block_to_dict(existing)

    user_id = _first_user_id(db)
    block = TraceabilityBlock(
        producer_id=producer.id,
        block_reason=data.block_reason,
        block_description=data.block_description,
        related_case_id=data.related_case_id,
        affects_all_production=True,
        affected_batches=data.affected_batches if data.affected_batches is not None else impacted_harvests_for_producer(db, producer.id),
        expected_resolution_date=data.expected_resolution_date,
        status=BlockStatus.ACTIVE,
        blocked_by=user_id,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block_to_dict(block)


@router.post("/compliance/blocks/{block_id:int}/resolve")
def resolve_traceability_block(
    block_id: int,
    data: TraceabilityResolve,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    block = db.query(TraceabilityBlock).filter(TraceabilityBlock.id == block_id).first()
    if not block or not _in_coop_producers(db, current_user, block.producer_id):
        raise HTTPException(status_code=404, detail="Blocage non trouve.")

    block.status = BlockStatus.RESOLVED
    block.actual_resolution_date = date.today()
    block.resolution_notes = data.resolution_notes
    db.commit()
    db.refresh(block)
    return block_to_dict(block)


def _coop_producer_subq(db: Session, cooperative_id: int | None):
    if cooperative_id is None:
        return None
    return db.query(Producer.id).filter(Producer.cooperative_id == cooperative_id).subquery()


def _coop_plantation_subq(db: Session, cooperative_id: int | None):
    if cooperative_id is None:
        return None
    return db.query(Plantation.id).filter(Plantation.cooperative_id == cooperative_id).subquery()


def build_due_diligence_report(db: Session, cooperative_id: int | None = None) -> dict:
    prod_subq = _coop_producer_subq(db, cooperative_id)
    plant_subq = _coop_plantation_subq(db, cooperative_id)

    child_f = [Child.producer_id.in_(prod_subq)] if prod_subq is not None else []
    visit_f = [MonitoringVisit.producer_id.in_(prod_subq)] if prod_subq is not None else []
    plan_f = [RemediationPlan.producer_id.in_(prod_subq)] if prod_subq is not None else []
    block_f = [TraceabilityBlock.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ssrte_hh_f = [SsrteHouseholdProfile.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ssrte_pv_f = [SsrtePlantationVisit.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ff_f = [FarmForceAssessment.producer_id.in_(prod_subq)] if prod_subq is not None else []
    train_f = [TrainingSession.cooperative_id == cooperative_id] if cooperative_id is not None else []
    ssrte_comm_f = [SsrteCommunityProfile.cooperative_id == cooperative_id] if cooperative_id is not None else []

    children_total = db.query(func.count(Child.id)).filter(Child.is_active == True, *child_f).scalar() or 0
    children_working = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.is_working_on_farm == True,
        *child_f,
    ).scalar() or 0
    enrolled = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.school_status == SchoolStatus.ENROLLED,
        *child_f,
    ).scalar() or 0

    risk_distribution = {}
    for level in RiskLevel:
        risk_distribution[level.value] = db.query(func.count(Child.id)).filter(
            Child.is_active == True,
            Child.risk_level == level,
            *child_f,
        ).scalar() or 0

    visits_total = db.query(func.count(MonitoringVisit.id)).filter(*visit_f).scalar() or 0
    visits_completed = db.query(func.count(MonitoringVisit.id)).filter(
        MonitoringVisit.status == VisitStatus.COMPLETED,
        *visit_f,
    ).scalar() or 0
    visits_with_photos = db.query(MonitoringVisit).filter(MonitoringVisit.photos.isnot(None), *visit_f).all()
    visits_with_consent = [
        visit for visit in db.query(MonitoringVisit).filter(*visit_f).all()
        if (visit.checklist_data or {}).get("consent_given")
    ]
    plans_active = db.query(func.count(RemediationPlan.id)).filter(
        RemediationPlan.status.in_([
            RemediationStatus.DRAFT,
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
            RemediationStatus.IN_PROGRESS,
            RemediationStatus.ESCALATED,
        ]),
        *plan_f,
    ).scalar() or 0
    blocks_active = db.query(func.count(TraceabilityBlock.id)).filter(
        TraceabilityBlock.status == BlockStatus.ACTIVE,
        *block_f,
    ).scalar() or 0
    alerts_open = db.query(func.count(Alert.id)).filter(
        Alert.status != AlertStatus.RESOLVED,
    ).scalar() or 0
    privacy_logs_total = db.query(func.count(PrivacyAccessLog.id)).scalar() or 0
    inconsistencies = detect_cacaoguard_inconsistencies(db)
    critical_inconsistencies = len([item for item in inconsistencies if item["severity"] == "critical"])
    trainings_total = db.query(func.count(TrainingSession.id)).filter(*train_f).scalar() or 0
    trainings_completed = db.query(func.count(TrainingSession.id)).filter(
        TrainingSession.status == TrainingStatus.COMPLETED,
        *train_f,
    ).scalar() or 0
    training_participants = sum(
        int(value or 0)
        for (value,) in db.query(TrainingSession.actual_participants).filter(*train_f).all()
    )
    ssrte_communities = db.query(func.count(SsrteCommunityProfile.id)).filter(*ssrte_comm_f).scalar() or 0
    ssrte_households = db.query(func.count(SsrteHouseholdProfile.id)).filter(*ssrte_hh_f).scalar() or 0
    ssrte_plantation_visits = db.query(func.count(SsrtePlantationVisit.id)).filter(*ssrte_pv_f).scalar() or 0
    ssrte_suspicions = db.query(func.count(SsrtePlantationVisit.id)).filter(
        SsrtePlantationVisit.suspected_child_labor == True,
        *ssrte_pv_f,
    ).scalar() or 0
    ssrte_high_risk_households = db.query(func.count(SsrteHouseholdProfile.id)).filter(
        SsrteHouseholdProfile.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
        *ssrte_hh_f,
    ).scalar() or 0
    farmforce_assessments = db.query(func.count(FarmForceAssessment.id)).filter(*ff_f).scalar() or 0
    farmforce_totals = db.query(
        func.coalesce(func.sum(FarmForceAssessment.total_revenue_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.total_cost_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.profit_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.family_labor_days), 0),
    ).filter(*ff_f).one()
    farmforce_avg_return = db.query(func.avg(FarmForceAssessment.return_per_family_day_cfa)).filter(*ff_f).scalar()
    farmforce_negative_profit = db.query(func.count(FarmForceAssessment.id)).filter(
        FarmForceAssessment.profit_cfa < 0,
        *ff_f,
    ).scalar() or 0

    critical_children = db.query(Child).filter(
        Child.is_active == True,
        Child.risk_level == RiskLevel.CRITICAL,
        *child_f,
    ).order_by(Child.risk_score.desc()).limit(10).all()
    recent_visits = db.query(MonitoringVisit).filter(*visit_f).order_by(
        MonitoringVisit.scheduled_date.desc(),
    ).limit(10).all()
    active_plans = db.query(RemediationPlan).filter(
        RemediationPlan.status.in_([
            RemediationStatus.DRAFT,
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
            RemediationStatus.IN_PROGRESS,
            RemediationStatus.ESCALATED,
        ]),
        *plan_f,
    ).order_by(RemediationPlan.created_at.desc()).limit(10).all()
    active_blocks = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.status == BlockStatus.ACTIVE,
        *block_f,
    ).order_by(TraceabilityBlock.created_at.desc()).limit(10).all()
    recent_trainings = db.query(TrainingSession).filter(*train_f).order_by(
        TrainingSession.scheduled_date.desc(),
    ).limit(10).all()
    recent_ssrte_households = db.query(SsrteHouseholdProfile).filter(*ssrte_hh_f).order_by(
        SsrteHouseholdProfile.created_at.desc(),
    ).limit(10).all()
    recent_ssrte_visits = db.query(SsrtePlantationVisit).filter(*ssrte_pv_f).order_by(
        SsrtePlantationVisit.created_at.desc(),
    ).limit(10).all()
    recent_farmforce = db.query(FarmForceAssessment).filter(*ff_f).order_by(
        FarmForceAssessment.created_at.desc(),
    ).limit(10).all()

    prod_filter = [Producer.cooperative_id == cooperative_id] if cooperative_id is not None else []
    plant_filter = [Plantation.cooperative_id == cooperative_id] if cooperative_id is not None else []

    return {
        "report_type": "CacaoGuard due diligence",
        "generated_at": datetime.utcnow().isoformat(),
        "coverage": {
            "producers": db.query(func.count(Producer.id)).filter(Producer.is_active == True, *prod_filter).scalar() or 0,
            "plantations": db.query(func.count(Plantation.id)).filter(*plant_filter).scalar() or 0,
            "children": children_total,
        },
        "indicators": {
            "children_working": children_working,
            "school_enrollment_rate": round(enrolled / children_total * 100, 1) if children_total else 0,
            "risk_distribution": risk_distribution,
            "open_alerts": alerts_open,
            "monitoring_visits_total": visits_total,
            "monitoring_visits_completed": visits_completed,
            "monitoring_visits_with_photos": len([v for v in visits_with_photos if v.photos]),
            "monitoring_visits_with_consent": len(visits_with_consent),
            "training_sessions_total": trainings_total,
            "training_sessions_completed": trainings_completed,
            "training_participants": training_participants,
            "ssrte_community_profiles": ssrte_communities,
            "ssrte_household_profiles": ssrte_households,
            "ssrte_plantation_visits": ssrte_plantation_visits,
            "ssrte_suspected_child_labor_visits": ssrte_suspicions,
            "ssrte_high_risk_households": ssrte_high_risk_households,
            "farmforce_assessments": farmforce_assessments,
            "farmforce_total_revenue_cfa": float(farmforce_totals[0] or 0),
            "farmforce_total_cost_cfa": float(farmforce_totals[1] or 0),
            "farmforce_total_profit_cfa": float(farmforce_totals[2] or 0),
            "farmforce_family_labor_days": float(farmforce_totals[3] or 0),
            "farmforce_average_return_per_family_day_cfa": round(float(farmforce_avg_return), 2)
            if farmforce_avg_return is not None
            else None,
            "farmforce_negative_profit_assessments": farmforce_negative_profit,
            "active_remediation_plans": plans_active,
            "active_traceability_blocks": blocks_active,
            "privacy_access_logs": privacy_logs_total,
            "ai_inconsistencies": len(inconsistencies),
            "ai_critical_inconsistencies": critical_inconsistencies,
        },
        "critical_cases": [
            {
                "child_id": child.id,
                "child_name": _child_name(child),
                "producer_id": child.producer_id,
                "producer_name": _producer_name(child.producer),
                "risk_score": float(child.risk_score or 0),
                "school_status": child.school_status.value,
                "work_frequency": child.work_frequency.value,
                "dangerous_tasks": child.dangerous_tasks_performed or [],
            }
            for child in critical_children
        ],
        "recent_visits": [visit_to_dict(visit) for visit in recent_visits],
        "recent_training_sessions": [training_to_dict(session) for session in recent_trainings],
        "recent_ssrte_households": [
            {
                "id": row.id,
                "producer_id": row.producer_id,
                "producer_name": _producer_name(row.producer),
                "interview_date": row.interview_date,
                "risk_score": float(row.risk_score or 0),
                "risk_level": row.risk_level.value,
                "vulnerabilities": row.vulnerabilities or [],
                "school_constraints": row.school_constraints or [],
            }
            for row in recent_ssrte_households
        ],
        "recent_ssrte_plantation_visits": [
            {
                "id": row.id,
                "plantation_id": row.plantation_id,
                "plantation_name": row.plantation.name if row.plantation else "Plantation inconnue",
                "producer_id": row.producer_id,
                "producer_name": _producer_name(row.producer),
                "visit_date": row.visit_date,
                "suspected_child_labor": bool(row.suspected_child_labor),
                "dangerous_tasks_observed": row.dangerous_tasks_observed or [],
                "consent_given": bool(row.consent_given),
                "photos": row.photos or [],
            }
            for row in recent_ssrte_visits
        ],
        "recent_farmforce_assessments": [
            {
                "id": row.id,
                "producer_id": row.producer_id,
                "producer_name": _producer_name(row.producer),
                "campaign_label": row.campaign_label,
                "localite": row.localite,
                "total_revenue_cfa": float(row.total_revenue_cfa or 0),
                "total_cost_cfa": float(row.total_cost_cfa or 0),
                "profit_cfa": float(row.profit_cfa or 0),
                "family_labor_days": float(row.family_labor_days or 0),
                "return_per_family_day_cfa": (
                    float(row.return_per_family_day_cfa)
                    if row.return_per_family_day_cfa is not None
                    else None
                ),
                "created_at": row.created_at,
            }
            for row in recent_farmforce
        ],
        "active_remediation_plans": [plan_to_dict(plan) for plan in active_plans],
        "traceability_blocks": [block_to_dict(block) for block in active_blocks],
        "ai_inconsistencies": inconsistencies[:20],
        "audit_evidence": {
            "children_register": "/children",
            "risk_assessments": "/children/assessments",
            "monitoring_visits": "/monitoring/visits",
            "training_sessions": "/training/sessions",
            "ssrte_community_profiles": "/ssrte/communities",
            "ssrte_household_profiles": "/ssrte/households",
            "ssrte_plantation_visits": "/ssrte/plantation-visits",
            "farmforce_assessments": "/farmforce/assessments",
            "remediation_plans": "/remediation/plans",
            "traceability_compliance": "/compliance/traceability",
            "privacy_access_logs": "/privacy/access-logs",
            "ai_inconsistencies": "/ai/inconsistencies",
        },
    }


@router.get("/compliance/report")
def get_due_diligence_report(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    record_privacy_access(
        db,
        current_user,
        action="view_due_diligence_report",
        source_entity="compliance_report",
        redacted=False,
        metadata={"format": "json"},
    )
    db.commit()
    coop_id = current_user.cooperative_id if current_user else None
    return build_due_diligence_report(db, cooperative_id=coop_id)


@router.get("/compliance/report.pdf")
def get_due_diligence_report_pdf(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    record_privacy_access(
        db,
        current_user,
        action="download_due_diligence_pdf",
        source_entity="compliance_report",
        redacted=False,
        metadata={"format": "pdf"},
    )
    db.commit()
    coop_id = current_user.cooperative_id if current_user else None
    report = build_due_diligence_report(db, cooperative_id=coop_id)
    pdf_bytes = generate_cacaoguard_pdf({"report": report, "generated_at": datetime.utcnow()})
    filename = cacaoguard_report_filename()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
