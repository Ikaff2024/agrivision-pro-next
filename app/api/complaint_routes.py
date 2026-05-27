"""
Endpoints pour le module Complaints CacaoGuard.

Couvre l'exigence EUDR / Fairtrade d'un mecanisme de signalement
(hotline, terrain, communaute, audit, anonyme) avec traitement formel,
escalade et tracabilite des consultations sensibles.

Routes :
- POST /complaints                  : creation, anonyme autorisee (sans auth)
- GET  /complaints                  : liste (admin/agronomist), filtres
- GET  /complaints/{id}             : detail (admin/agronomist)
- PUT  /complaints/{id}             : MAJ investigation (admin/agronomist)
- POST /complaints/{id}/escalate    : escalade explicite (admin/agronomist)
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Producer, User
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    Child,
    Complaint,
    ComplaintSeverity,
    ComplaintStatus,
    ComplaintType,
    Priority,
)
from app.api.cacaoguard_ops_routes import (
    get_optional_current_user,
    record_privacy_access,
    require_role,
)

router = APIRouter(prefix="/complaints", tags=["CacaoGuard - signalements"])


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------

class ComplaintCreate(BaseModel):
    complaint_type: ComplaintType
    severity: ComplaintSeverity = ComplaintSeverity.MEDIUM
    description: str = Field(..., min_length=10, max_length=5000)
    source: str = Field(default="anonymous", max_length=50)
    reporter_name: Optional[str] = Field(None, max_length=200)
    reporter_contact: Optional[str] = Field(None, max_length=100)
    reporter_relationship: Optional[str] = Field(None, max_length=50)
    producer_id: Optional[int] = None
    child_id: Optional[int] = None
    location_description: Optional[str] = Field(None, max_length=2000)
    location_gps: Optional[str] = Field(None, max_length=100)
    is_confidential: bool = True
    confidentiality_level: str = Field(default="confidential", max_length=50)


class ComplaintUpdate(BaseModel):
    status: Optional[ComplaintStatus] = None
    severity: Optional[ComplaintSeverity] = None
    assigned_investigator: Optional[int] = None
    investigation_start_date: Optional[date] = None
    investigation_end_date: Optional[date] = None
    findings: Optional[str] = Field(None, max_length=5000)
    actions_taken: Optional[list] = None
    referral_made: Optional[bool] = None
    referred_to: Optional[str] = Field(None, max_length=200)
    confidentiality_level: Optional[str] = Field(None, max_length=50)


class ComplaintEscalation(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)
    referred_to: Optional[str] = Field(None, max_length=200)


class ComplaintAck(BaseModel):
    id: int
    reference: str
    status: str
    message: str


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

_AUTO_ALERT_TYPES = {ComplaintType.TRAFFICKING, ComplaintType.ABUSE, ComplaintType.EXPLOITATION}
_AUTO_ALERT_SEVERITIES = {ComplaintSeverity.HIGH, ComplaintSeverity.CRITICAL}


def _next_reference(db: Session) -> str:
    """Format CMP-YYYY-NNN, sequence par annee."""
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
    return f"{prefix}{next_num:03d}"


def _priority_from_severity(sev: ComplaintSeverity) -> Priority:
    return {
        ComplaintSeverity.LOW: Priority.LOW,
        ComplaintSeverity.MEDIUM: Priority.MEDIUM,
        ComplaintSeverity.HIGH: Priority.HIGH,
        ComplaintSeverity.CRITICAL: Priority.URGENT,
    }.get(sev, Priority.MEDIUM)


def _maybe_create_alert(db: Session, complaint: Complaint) -> Optional[Alert]:
    """Cree une alerte automatique pour les signalements sensibles."""
    if complaint.complaint_type not in _AUTO_ALERT_TYPES and complaint.severity not in _AUTO_ALERT_SEVERITIES:
        return None

    existing = (
        db.query(Alert)
        .filter(
            Alert.source_entity == "complaints",
            Alert.source_id == complaint.id,
            Alert.alert_type == AlertType.COMPLAINT,
            Alert.status != AlertStatus.RESOLVED,
        )
        .first()
    )
    if existing:
        return existing

    alert = Alert(
        source_entity="complaints",
        source_id=complaint.id,
        alert_type=AlertType.COMPLAINT,
        priority=_priority_from_severity(complaint.severity),
        title=f"Signalement {complaint.severity.value} - {complaint.complaint_type.value}",
        message=(
            f"Plainte {complaint.complaint_reference} recue (source : {complaint.source}). "
            f"Type : {complaint.complaint_type.value}, severite : {complaint.severity.value}."
        ),
        alert_metadata={
            "complaint_id": complaint.id,
            "reference": complaint.complaint_reference,
            "type": complaint.complaint_type.value,
            "severity": complaint.severity.value,
            "producer_id": complaint.producer_id,
            "child_id": complaint.child_id,
        },
    )
    db.add(alert)
    return alert


def _validate_links(db: Session, producer_id: Optional[int], child_id: Optional[int]) -> None:
    if producer_id and not db.query(Producer).filter(Producer.id == producer_id).first():
        raise HTTPException(status_code=404, detail="Producteur non trouve.")
    if child_id and not db.query(Child).filter(Child.id == child_id, Child.is_active == True).first():
        raise HTTPException(status_code=404, detail="Enfant non trouve.")


def _complaint_to_dict(complaint: Complaint, *, redact_reporter: bool = False) -> dict:
    data = {
        "id": complaint.id,
        "reference": complaint.complaint_reference,
        "source": complaint.source,
        "complaint_type": complaint.complaint_type.value if complaint.complaint_type else None,
        "severity": complaint.severity.value if complaint.severity else None,
        "description": complaint.description,
        "producer_id": complaint.producer_id,
        "child_id": complaint.child_id,
        "location_description": complaint.location_description,
        "location_gps": complaint.location_gps,
        "status": complaint.status.value if complaint.status else None,
        "assigned_investigator": complaint.assigned_investigator,
        "received_date": complaint.received_date,
        "investigation_start_date": complaint.investigation_start_date,
        "investigation_end_date": complaint.investigation_end_date,
        "findings": complaint.findings,
        "actions_taken": complaint.actions_taken,
        "referral_made": complaint.referral_made,
        "referred_to": complaint.referred_to,
        "is_confidential": complaint.is_confidential,
        "confidentiality_level": complaint.confidentiality_level,
        "created_at": complaint.created_at,
        "updated_at": complaint.updated_at,
    }
    if redact_reporter:
        data.update({
            "reporter_name": None,
            "reporter_contact": None,
            "reporter_relationship": "[redacted]",
        })
    else:
        data["reporter_name"] = complaint.reporter_name
        data["reporter_contact"] = complaint.reporter_contact
        data["reporter_relationship"] = complaint.reporter_relationship
    return data


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@router.post("", status_code=201, response_model=ComplaintAck)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Cree un signalement. Accessible sans auth (hotline anonyme).

    Reponse minimale (id + reference + statut) pour ne pas exposer
    le contenu en retour cote client public.
    """
    _validate_links(db, payload.producer_id, payload.child_id)

    reference = _next_reference(db)
    complaint = Complaint(
        complaint_reference=reference,
        source=payload.source or ("anonymous" if current_user is None else "field_agent"),
        complaint_type=payload.complaint_type,
        severity=payload.severity,
        description=payload.description,
        reporter_name=payload.reporter_name,
        reporter_contact=payload.reporter_contact,
        reporter_relationship=payload.reporter_relationship,
        producer_id=payload.producer_id,
        child_id=payload.child_id,
        location_description=payload.location_description,
        location_gps=payload.location_gps,
        status=ComplaintStatus.RECEIVED,
        is_confidential=payload.is_confidential,
        confidentiality_level=payload.confidentiality_level,
        created_by=current_user.id if current_user else None,
    )
    db.add(complaint)
    db.flush()
    _maybe_create_alert(db, complaint)
    record_privacy_access(
        db,
        current_user,
        action="create_complaint",
        source_entity="complaints",
        source_id=complaint.id,
        metadata={
            "reference": reference,
            "type": payload.complaint_type.value,
            "severity": payload.severity.value,
            "anonymous": current_user is None,
        },
    )
    db.commit()
    db.refresh(complaint)
    return ComplaintAck(
        id=complaint.id,
        reference=complaint.complaint_reference,
        status=complaint.status.value,
        message="Signalement enregistre. Merci pour votre vigilance.",
    )


@router.get("")
def list_complaints(
    status: Optional[ComplaintStatus] = None,
    severity: Optional[ComplaintSeverity] = None,
    complaint_type: Optional[ComplaintType] = None,
    producer_id: Optional[int] = None,
    child_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})

    query = db.query(Complaint)
    if status:
        query = query.filter(Complaint.status == status)
    if severity:
        query = query.filter(Complaint.severity == severity)
    if complaint_type:
        query = query.filter(Complaint.complaint_type == complaint_type)
    if producer_id:
        query = query.filter(Complaint.producer_id == producer_id)
    if child_id:
        query = query.filter(Complaint.child_id == child_id)

    items = query.order_by(Complaint.received_date.desc()).offset(skip).limit(limit).all()

    # Redaction du reporter si confidentiality_level == 'restricted' et user != admin
    redact = current_user is not None and current_user.role != "admin"
    response = [
        _complaint_to_dict(
            c,
            redact_reporter=redact and (c.confidentiality_level == "restricted" or c.source == "anonymous"),
        )
        for c in items
    ]
    record_privacy_access(
        db,
        current_user,
        action="list_complaints",
        source_entity="complaints",
        redacted=redact,
        metadata={"count": len(items)},
    )
    db.commit()
    return response


@router.get("/{complaint_id:int}")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Signalement non trouve.")

    redact = (
        current_user is not None
        and current_user.role != "admin"
        and (complaint.confidentiality_level == "restricted" or complaint.source == "anonymous")
    )
    data = _complaint_to_dict(complaint, redact_reporter=redact)
    record_privacy_access(
        db,
        current_user,
        action="view_complaint",
        source_entity="complaints",
        source_id=complaint.id,
        redacted=redact,
        metadata={"reference": complaint.complaint_reference},
    )
    db.commit()
    return data


@router.put("/{complaint_id:int}")
def update_complaint(
    complaint_id: int,
    payload: ComplaintUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Signalement non trouve.")

    update_data = payload.model_dump(exclude_unset=True)
    if "assigned_investigator" in update_data and update_data["assigned_investigator"] is not None:
        if not db.query(User).filter(User.id == update_data["assigned_investigator"]).first():
            raise HTTPException(status_code=404, detail="Investigateur non trouve.")

    for field, value in update_data.items():
        setattr(complaint, field, value)

    # Si statut passe a UNDER_REVIEW/INVESTIGATING sans start_date, on l'initialise
    if (
        complaint.status in (ComplaintStatus.UNDER_REVIEW, ComplaintStatus.INVESTIGATING)
        and complaint.investigation_start_date is None
    ):
        complaint.investigation_start_date = date.today()

    # Si statut passe a CLOSED/SUBSTANTIATED/UNSUBSTANTIATED sans end_date, on l'initialise
    if (
        complaint.status in (ComplaintStatus.CLOSED, ComplaintStatus.SUBSTANTIATED, ComplaintStatus.UNSUBSTANTIATED)
        and complaint.investigation_end_date is None
    ):
        complaint.investigation_end_date = date.today()

    db.commit()
    db.refresh(complaint)
    record_privacy_access(
        db,
        current_user,
        action="update_complaint",
        source_entity="complaints",
        source_id=complaint.id,
        metadata={"reference": complaint.complaint_reference, "fields": list(update_data.keys())},
    )
    db.commit()
    return _complaint_to_dict(complaint)


@router.post("/{complaint_id:int}/escalate")
def escalate_complaint(
    complaint_id: int,
    payload: ComplaintEscalation,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Signalement non trouve.")

    complaint.status = ComplaintStatus.ESCALATED
    if payload.referred_to:
        complaint.referred_to = payload.referred_to
        complaint.referral_made = True

    # Cree ou aggrave une alerte
    alert = (
        db.query(Alert)
        .filter(
            Alert.source_entity == "complaints",
            Alert.source_id == complaint.id,
            Alert.status != AlertStatus.RESOLVED,
        )
        .first()
    )
    if alert:
        alert.priority = Priority.URGENT
        alert.status = AlertStatus.ESCALATED
        alert.message = f"{alert.message} | Escalade : {payload.reason}"
    else:
        alert = Alert(
            source_entity="complaints",
            source_id=complaint.id,
            alert_type=AlertType.COMPLAINT,
            priority=Priority.URGENT,
            status=AlertStatus.ESCALATED,
            title=f"Signalement escalade - {complaint.complaint_reference}",
            message=f"Escalade : {payload.reason}",
            alert_metadata={
                "reference": complaint.complaint_reference,
                "escalation_reason": payload.reason,
                "referred_to": payload.referred_to,
            },
        )
        db.add(alert)

    db.commit()
    db.refresh(complaint)
    record_privacy_access(
        db,
        current_user,
        action="escalate_complaint",
        source_entity="complaints",
        source_id=complaint.id,
        metadata={
            "reference": complaint.complaint_reference,
            "reason": payload.reason,
            "referred_to": payload.referred_to,
        },
    )
    db.commit()
    return _complaint_to_dict(complaint)
