"""
Sync mobile pour terrain offline CacaoGuard.

Couvre les 4 endpoints attendus par la roadmap (section 5.1) :
- POST /sync/pull              : snapshot/delta par entite
- POST /sync/push              : batch d'operations offline avec idempotence
- POST /sync/conflict/resolve  : resolution explicite des conflits (server_wins MVP)
- GET  /sync/status            : metadonnees client (last_op, supported_ops)

Modele :
- Idempotence stricte par op_id (UUID client) via SyncOperationLog
- Last-write-wins par defaut (conflicts retournes mais non automatises)
- Scoping per-user : technicien voit ses assignments, admin/agronomist voit tout
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cacaoguard_ops_routes import (
    get_optional_current_user,
    require_role,
)
from app.db.database import get_db
from app.db.models import Plantation, Producer, User
from app.db.models_social import (
    ActionStatus,
    Alert,
    AlertStatus,
    Child,
    Complaint,
    ComplaintSeverity,
    ComplaintStatus,
    ComplaintType,
    MonitoringVisit,
    Priority,
    RemediationAction,
    RemediationPlan,
    SyncOperationLog,
    VisitStatus,
    VisitType,
)

router = APIRouter(prefix="/sync", tags=["CacaoGuard - sync mobile"])

ALL_ENTITIES = [
    "producers",
    "plantations",
    "children",
    "monitoring_visits",
    "remediation_plans",
    "remediation_actions",
    "alerts",
]


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------

class PullRequest(BaseModel):
    last_sync_at: Optional[datetime] = None
    entities: Optional[List[str]] = None


class PushOperation(BaseModel):
    op_id: str = Field(..., min_length=8, max_length=64)
    op_type: str = Field(..., max_length=50)
    client_timestamp: Optional[datetime] = None
    payload: dict = Field(default_factory=dict)


class PushRequest(BaseModel):
    operations: List[PushOperation] = Field(default_factory=list)


class ConflictResolve(BaseModel):
    op_id: str = Field(..., min_length=8, max_length=64)
    resolution: str = Field(..., pattern="^(server_wins|client_wins)$")


# ----------------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------------

def _require_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentification requise pour la sync.")
    return user


def _is_supervisor(user: User) -> bool:
    return user.role in {"admin", "agronomist"}


# ----------------------------------------------------------------------------
# Serialisation (lightweight pour transit mobile)
# ----------------------------------------------------------------------------

def _serialize_producer(p: Producer) -> dict:
    return {
        "id": p.id,
        "nom_complet": p.nom_complet,
        "code_yeyasso": p.code_yeyasso,
        "localite": p.localite,
        "section": p.section,
        "telephone": p.telephone,
        "cooperative_id": p.cooperative_id,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "is_active": p.is_active,
        "updated_at": p.created_at,  # Producer n'a pas d'updated_at
    }


def _serialize_plantation(p: Plantation) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "producer_id": p.producer_id,
        "hectares": float(p.hectares) if p.hectares is not None else None,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "region": p.region,
    }


def _serialize_child(c: Child) -> dict:
    return {
        "id": c.id,
        "producer_id": c.producer_id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "date_of_birth": c.date_of_birth,
        "gender": c.gender,
        "school_status": c.school_status.value if c.school_status else None,
        "is_working_on_farm": c.is_working_on_farm,
        "work_frequency": c.work_frequency.value if c.work_frequency else None,
        "risk_score": float(c.risk_score or 0),
        "risk_level": c.risk_level.value if c.risk_level else None,
        "is_active": c.is_active,
        "updated_at": c.updated_at or c.created_at,
    }


def _serialize_visit(v: MonitoringVisit) -> dict:
    return {
        "id": v.id,
        "producer_id": v.producer_id,
        "scheduled_date": v.scheduled_date,
        "actual_date": v.actual_date,
        "visit_type": v.visit_type.value if v.visit_type else None,
        "status": v.status.value if v.status else None,
        "priority": v.priority.value if v.priority else None,
        "lead_assessor_id": v.lead_assessor_id,
        "updated_at": v.updated_at or v.created_at,
    }


def _serialize_plan(p: RemediationPlan) -> dict:
    return {
        "id": p.id,
        "producer_id": p.producer_id,
        "child_id": p.child_id,
        "plan_reference": p.plan_reference,
        "status": p.status.value if p.status else None,
        "priority": p.priority.value if p.priority else None,
        "case_worker_id": p.case_worker_id,
        "updated_at": p.updated_at or p.created_at,
    }


def _serialize_action(a: RemediationAction) -> dict:
    return {
        "id": a.id,
        "remediation_plan_id": a.remediation_plan_id,
        "action_type": a.action_type.value if a.action_type else None,
        "status": a.status.value if a.status else None,
        "planned_date": a.planned_date,
        "completed_date": a.completed_date,
        "responsible_id": a.responsible_id,
        "updated_at": a.updated_at or a.created_at,
    }


def _serialize_alert(a: Alert) -> dict:
    return {
        "id": a.id,
        "source_entity": a.source_entity,
        "source_id": a.source_id,
        "alert_type": a.alert_type.value if a.alert_type else None,
        "priority": a.priority.value if a.priority else None,
        "status": a.status.value if a.status else None,
        "title": a.title,
        "updated_at": a.updated_at or a.created_at,
    }


# ----------------------------------------------------------------------------
# Pull : snapshot / delta
# ----------------------------------------------------------------------------

def _scoped_producers_query(db: Session, user: User):
    if _is_supervisor(user):
        return db.query(Producer).filter(Producer.is_active == True)
    # Pour technicien : producteurs lies aux plantations assignees
    # En MVP, les techniciens voient tous les producteurs actifs de leur coop
    coop_id = user.cooperative_id
    q = db.query(Producer).filter(Producer.is_active == True)
    if coop_id is not None:
        q = q.filter(Producer.cooperative_id == coop_id)
    return q


def _filter_updated_since(query, column, since: Optional[datetime]):
    if since is None:
        return query
    return query.filter(column >= since)


@router.post("/pull")
def sync_pull(
    payload: PullRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Snapshot ou delta depuis `last_sync_at`.

    Si `last_sync_at` est null : snapshot complet (premiere sync).
    Sinon : retourne uniquement les enregistrements modifies/crees depuis.

    `entities` permet de filtrer les types demandes. None = tous.
    """
    user = _require_user(current_user)
    require_role(user, {"admin", "agronomist", "technician"})

    requested = set(payload.entities) if payload.entities else set(ALL_ENTITIES)
    unknown = requested - set(ALL_ENTITIES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Entites inconnues : {sorted(unknown)}")

    since = payload.last_sync_at
    server_time = datetime.utcnow()
    result: dict = {"server_time": server_time, "counts": {}}

    if "producers" in requested:
        q = _scoped_producers_query(db, user)
        # Producer n'a pas d'updated_at -> on utilise created_at
        q = _filter_updated_since(q, Producer.created_at, since)
        items = [_serialize_producer(p) for p in q.all()]
        result["producers"] = items
        result["counts"]["producers"] = len(items)

    if "plantations" in requested:
        producer_ids = [p.id for p in _scoped_producers_query(db, user).all()]
        q = db.query(Plantation).filter(Plantation.producer_id.in_(producer_ids))
        items = [_serialize_plantation(p) for p in q.all()]
        result["plantations"] = items
        result["counts"]["plantations"] = len(items)

    if "children" in requested:
        producer_ids = [p.id for p in _scoped_producers_query(db, user).all()]
        q = db.query(Child).filter(Child.producer_id.in_(producer_ids), Child.is_active == True)
        # Child a updated_at + created_at — on borne sur le max des deux via OR
        if since:
            q = q.filter(
                (Child.updated_at >= since) | (Child.created_at >= since)
            )
        items = [_serialize_child(c) for c in q.all()]
        result["children"] = items
        result["counts"]["children"] = len(items)

    if "monitoring_visits" in requested:
        producer_ids = [p.id for p in _scoped_producers_query(db, user).all()]
        q = db.query(MonitoringVisit).filter(MonitoringVisit.producer_id.in_(producer_ids))
        # Technicien : filtre supplementaire sur ses propres visites
        if not _is_supervisor(user):
            q = q.filter(MonitoringVisit.lead_assessor_id == user.id)
        if since:
            q = q.filter(
                (MonitoringVisit.updated_at >= since) | (MonitoringVisit.created_at >= since)
            )
        items = [_serialize_visit(v) for v in q.all()]
        result["monitoring_visits"] = items
        result["counts"]["monitoring_visits"] = len(items)

    if "remediation_plans" in requested:
        producer_ids = [p.id for p in _scoped_producers_query(db, user).all()]
        q = db.query(RemediationPlan).filter(RemediationPlan.producer_id.in_(producer_ids))
        if since:
            q = q.filter(
                (RemediationPlan.updated_at >= since) | (RemediationPlan.created_at >= since)
            )
        items = [_serialize_plan(p) for p in q.all()]
        result["remediation_plans"] = items
        result["counts"]["remediation_plans"] = len(items)

    if "remediation_actions" in requested:
        producer_ids = [p.id for p in _scoped_producers_query(db, user).all()]
        plan_ids = [
            p.id for p in db.query(RemediationPlan)
            .filter(RemediationPlan.producer_id.in_(producer_ids)).all()
        ]
        q = db.query(RemediationAction).filter(
            RemediationAction.remediation_plan_id.in_(plan_ids)
        )
        if not _is_supervisor(user):
            q = q.filter(RemediationAction.responsible_id == user.id)
        if since:
            q = q.filter(
                (RemediationAction.updated_at >= since) | (RemediationAction.created_at >= since)
            )
        items = [_serialize_action(a) for a in q.all()]
        result["remediation_actions"] = items
        result["counts"]["remediation_actions"] = len(items)

    if "alerts" in requested:
        q = db.query(Alert).filter(Alert.status != AlertStatus.RESOLVED)
        if since:
            q = q.filter(Alert.created_at >= since)
        items = [_serialize_alert(a) for a in q.all()]
        result["alerts"] = items
        result["counts"]["alerts"] = len(items)

    return result


# ----------------------------------------------------------------------------
# Push : handlers per op_type
# ----------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Conversion recursive en types JSON-serialisables (date/datetime/Decimal)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class OpResult(dict):
    """Marque ergonomique. Cle obligatoire: status."""


def _ok(server_id: int, snapshot: Optional[dict] = None) -> OpResult:
    return OpResult(status="success", server_id=server_id, server_snapshot=snapshot)


def _conflict(message: str, server_id: Optional[int] = None) -> OpResult:
    return OpResult(status="conflict", server_id=server_id, error=message)


def _error(message: str) -> OpResult:
    return OpResult(status="error", server_id=None, error=message)


def _handle_create_visit(db: Session, user: User, payload: dict) -> OpResult:
    try:
        producer_id = int(payload["producer_id"])
        scheduled = date.fromisoformat(payload["scheduled_date"])
    except (KeyError, ValueError, TypeError) as exc:
        return _error(f"Payload invalide : {exc}")

    if not db.query(Producer).filter(Producer.id == producer_id).first():
        return _error("Producteur introuvable.")

    visit = MonitoringVisit(
        producer_id=producer_id,
        scheduled_date=scheduled,
        actual_date=date.fromisoformat(payload["actual_date"]) if payload.get("actual_date") else None,
        visit_type=VisitType(payload.get("visit_type", "routine")),
        priority=Priority(payload.get("priority", "medium")),
        lead_assessor_id=payload.get("lead_assessor_id") or user.id,
        visit_location=payload.get("visit_location"),
        checklist_data=payload.get("checklist_data") or {},
        observations=payload.get("observations"),
        dangerous_tasks_observed=payload.get("dangerous_tasks_observed"),
        photos=payload.get("photos") or [],
        producer_signature_data=payload.get("producer_signature_data") or {},
        assessor_signature_data=payload.get("assessor_signature_data") or {},
        status=VisitStatus.COMPLETED if payload.get("complete_on_create") else VisitStatus.SCHEDULED,
    )
    db.add(visit)
    db.flush()
    return _ok(visit.id, _serialize_visit(visit))


def _handle_complete_visit(db: Session, user: User, payload: dict) -> OpResult:
    try:
        visit_id = int(payload["visit_id"])
    except (KeyError, ValueError):
        return _error("visit_id manquant ou invalide.")

    visit = db.query(MonitoringVisit).filter(MonitoringVisit.id == visit_id).first()
    if not visit:
        return _error("Visite introuvable.")
    if visit.status == VisitStatus.COMPLETED:
        return _conflict("Visite deja completee.", server_id=visit.id)

    visit.status = VisitStatus.COMPLETED
    visit.actual_date = (
        date.fromisoformat(payload["actual_date"]) if payload.get("actual_date") else date.today()
    )
    if "observations" in payload:
        visit.observations = payload["observations"]
    if "checklist_data" in payload:
        visit.checklist_data = payload["checklist_data"]
    if "dangerous_tasks_observed" in payload:
        visit.dangerous_tasks_observed = payload["dangerous_tasks_observed"]
    if "photos" in payload:
        visit.photos = payload["photos"]
    db.flush()
    return _ok(visit.id, _serialize_visit(visit))


def _handle_create_complaint(db: Session, user: User, payload: dict) -> OpResult:
    try:
        complaint_type = ComplaintType(payload["complaint_type"])
        severity = ComplaintSeverity(payload.get("severity", "medium"))
        description = payload["description"]
    except (KeyError, ValueError) as exc:
        return _error(f"Payload invalide : {exc}")
    if not description or len(description) < 10:
        return _error("description trop courte (>= 10 caracteres).")

    # Reference auto (CMP-YYYY-NNN) — meme logique que complaint_routes (duplique pour
    # independance du module, evite cycle d'import).
    year = date.today().year
    prefix = f"CMP-{year}-"
    last = (
        db.query(Complaint)
        .filter(Complaint.complaint_reference.like(f"{prefix}%"))
        .order_by(Complaint.id.desc())
        .first()
    )
    next_num = 1
    if last and last.complaint_reference:
        try:
            next_num = int(last.complaint_reference.rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            next_num = 1

    complaint = Complaint(
        complaint_reference=f"{prefix}{next_num:03d}",
        source=payload.get("source", "field_agent"),
        complaint_type=complaint_type,
        severity=severity,
        description=description,
        reporter_name=payload.get("reporter_name"),
        reporter_contact=payload.get("reporter_contact"),
        producer_id=payload.get("producer_id"),
        child_id=payload.get("child_id"),
        location_description=payload.get("location_description"),
        location_gps=payload.get("location_gps"),
        status=ComplaintStatus.RECEIVED,
        is_confidential=payload.get("is_confidential", True),
        created_by=user.id,
    )
    db.add(complaint)
    db.flush()
    return _ok(complaint.id, {
        "id": complaint.id,
        "reference": complaint.complaint_reference,
        "status": complaint.status.value,
    })


def _handle_complete_action(db: Session, user: User, payload: dict) -> OpResult:
    try:
        action_id = int(payload["action_id"])
        evidence = payload.get("evidence") or {}
    except (KeyError, ValueError):
        return _error("action_id manquant ou invalide.")

    if not any(bool(v) for v in evidence.values()):
        return _error("Preuves obligatoires (au moins une cle non vide).")

    action = db.query(RemediationAction).filter(RemediationAction.id == action_id).first()
    if not action:
        return _error("Action introuvable.")
    if action.status == ActionStatus.COMPLETED:
        return _conflict("Action deja completee.", server_id=action.id)
    if action.status == ActionStatus.CANCELLED:
        return _error("Action annulee : impossible a completer.")

    action.status = ActionStatus.COMPLETED
    action.completed_date = (
        date.fromisoformat(payload["completed_date"]) if payload.get("completed_date") else date.today()
    )
    action.evidence = evidence
    if payload.get("notes"):
        action.notes = payload["notes"]
    if payload.get("impact_assessment"):
        action.impact_assessment = payload["impact_assessment"]
    db.flush()
    return _ok(action.id, _serialize_action(action))


HANDLERS: dict = {
    "create_visit": ("monitoring_visits", _handle_create_visit),
    "complete_visit": ("monitoring_visits", _handle_complete_visit),
    "create_complaint": ("complaints", _handle_create_complaint),
    "complete_action": ("remediation_actions", _handle_complete_action),
}


@router.post("/push")
def sync_push(
    payload: PushRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Applique un batch d'operations offline. Idempotent par op_id.

    Pour chaque op, retourne un statut individuel : success / duplicate /
    conflict / error. Les operations ne sont jamais rejouees : un op_id deja
    vu retourne le resultat memorise (duplicate).
    """
    user = _require_user(current_user)
    require_role(user, {"admin", "agronomist", "technician"})

    if not payload.operations:
        return {"results": []}

    results: List[dict] = []
    for op in payload.operations:
        # Idempotence : verifier si op_id deja traite
        existing = db.query(SyncOperationLog).filter(SyncOperationLog.op_id == op.op_id).first()
        if existing:
            results.append({
                "op_id": op.op_id,
                "status": "duplicate",
                "server_id": existing.server_entity_id,
                "original_status": existing.status,
                "applied_at": existing.applied_at,
            })
            continue

        handler_entry = HANDLERS.get(op.op_type)
        if handler_entry is None:
            outcome = _error(f"op_type non supporte : {op.op_type}")
            entity_type = "unknown"
        else:
            entity_type, handler = handler_entry
            try:
                outcome = handler(db, user, op.payload)
            except Exception as exc:  # noqa: BLE001 — on capture pour le retour API
                db.rollback()
                outcome = _error(f"Exception : {exc}")

        log = SyncOperationLog(
            op_id=op.op_id,
            user_id=user.id,
            op_type=op.op_type,
            entity_type=entity_type,
            payload=_json_safe(op.payload),
            result=_json_safe(dict(outcome)),
            status=outcome["status"],
            server_entity_id=outcome.get("server_id"),
            error_message=outcome.get("error"),
            client_timestamp=op.client_timestamp,
        )
        db.add(log)
        db.commit()  # commit per-op pour ne pas perdre le log en cas de crash

        results.append({
            "op_id": op.op_id,
            "status": outcome["status"],
            "server_id": outcome.get("server_id"),
            "error": outcome.get("error"),
            "server_snapshot": outcome.get("server_snapshot"),
        })

    return {"results": results}


@router.get("/status")
def sync_status(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    user = _require_user(current_user)
    require_role(user, {"admin", "agronomist", "technician"})

    last_log = (
        db.query(SyncOperationLog)
        .filter(SyncOperationLog.user_id == user.id)
        .order_by(SyncOperationLog.applied_at.desc())
        .first()
    )
    applied_count = (
        db.query(SyncOperationLog)
        .filter(SyncOperationLog.user_id == user.id)
        .count()
    )
    return {
        "server_time": datetime.utcnow(),
        "user_id": user.id,
        "role": user.role,
        "last_op_at": last_log.applied_at if last_log else None,
        "last_op_status": last_log.status if last_log else None,
        "applied_ops_count": applied_count,
        "supported_op_types": list(HANDLERS.keys()),
        "supported_entities": ALL_ENTITIES,
    }


@router.post("/conflict/resolve")
def sync_conflict_resolve(
    payload: ConflictResolve,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Acquittement de conflit. En MVP, seul `server_wins` est supporte.

    Le client doit refetch via /sync/pull pour recuperer l'etat serveur
    canonique. `client_wins` reserve pour un futur PR (force re-application
    avec override des verifications de conflit).
    """
    user = _require_user(current_user)
    require_role(user, {"admin", "agronomist", "technician"})

    log = db.query(SyncOperationLog).filter(SyncOperationLog.op_id == payload.op_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Operation inconnue.")
    if log.status != "conflict":
        raise HTTPException(
            status_code=409,
            detail=f"Operation en statut {log.status} : pas de conflit a resoudre.",
        )

    if payload.resolution == "client_wins":
        raise HTTPException(
            status_code=501,
            detail="client_wins non implemente. Utiliser server_wins puis re-soumettre apres pull.",
        )

    # server_wins : on marque le log comme acquitte, le client doit refetch
    log.status = "resolved_server_wins"
    log.error_message = (log.error_message or "") + " | resolved_server_wins"
    db.commit()
    return {
        "op_id": log.op_id,
        "resolution": "server_wins",
        "applied": True,
        "instruction": "Refetch via /sync/pull pour synchroniser l'etat serveur.",
    }
