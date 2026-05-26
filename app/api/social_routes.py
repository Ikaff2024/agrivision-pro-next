from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Producer, User
from app.auth.auth_service import decode_token
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    AssessmentType,
    Child,
    Priority,
    RiskAssessment,
    RiskLevel,
    SchoolStatus,
    WorkFrequency,
)
from app.api.cacaoguard_ops_routes import ensure_remediation_plan_for_child
from app.api.cacaoguard_ops_routes import record_privacy_access

router = APIRouter(prefix="/children", tags=["CacaoGuard - protection enfant"])
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


class ChildCreate(BaseModel):
    producer_id: int
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    gender: str = Field(..., pattern="^[MF]$")
    birth_certificate_number: Optional[str] = Field(None, max_length=100)
    school_status: SchoolStatus = SchoolStatus.NOT_SCHOOL_AGE
    school_name: Optional[str] = Field(None, max_length=200)
    is_working_on_farm: bool = False
    work_frequency: WorkFrequency = WorkFrequency.NEVER
    dangerous_tasks_performed: Optional[List[str]] = None


class ChildUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, pattern="^[MF]$")
    birth_certificate_number: Optional[str] = Field(None, max_length=100)
    school_status: Optional[SchoolStatus] = None
    school_name: Optional[str] = Field(None, max_length=200)
    is_working_on_farm: Optional[bool] = None
    work_frequency: Optional[WorkFrequency] = None
    dangerous_tasks_performed: Optional[List[str]] = None


class ChildResponse(BaseModel):
    id: int
    producer_id: int
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    birth_certificate_number: Optional[str]
    school_status: SchoolStatus
    school_name: Optional[str]
    is_working_on_farm: bool
    work_frequency: WorkFrequency
    dangerous_tasks_performed: Optional[List[str]]
    risk_score: float
    risk_level: RiskLevel
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class RiskAssessmentCreate(BaseModel):
    child_id: int
    assessment_type: AssessmentType = AssessmentType.INITIAL
    overall_risk_score: float = Field(..., ge=0, le=100)
    overall_risk_level: RiskLevel
    risk_factors: dict = Field(default_factory=dict)
    notes: Optional[str] = None
    assessor_id: Optional[int] = None


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    priority: str
    source_entity: str
    source_id: int
    title: str
    message: str
    status: str
    created_at: Optional[datetime]


def _age_years(dob: date) -> float:
    return (date.today() - dob).days / 365.25


def calculate_risk_score(child: ChildCreate) -> tuple[float, dict]:
    factors = {
        "age": 0,
        "school": 0,
        "work": 0,
        "dangerous_tasks": 0,
    }

    age = _age_years(child.date_of_birth)
    if age < 12:
        factors["age"] = 25
    elif age < 15:
        factors["age"] = 18
    elif age < 18:
        factors["age"] = 8

    if child.school_status == SchoolStatus.NEVER_ENROLLED:
        factors["school"] = 25
    elif child.school_status == SchoolStatus.DROPPED_OUT:
        factors["school"] = 20
    elif child.school_status == SchoolStatus.NOT_SCHOOL_AGE:
        factors["school"] = 4

    if child.is_working_on_farm:
        factors["work"] = 12
        if child.work_frequency == WorkFrequency.OCCASIONAL:
            factors["work"] += 5
        elif child.work_frequency == WorkFrequency.REGULAR:
            factors["work"] += 12
        elif child.work_frequency == WorkFrequency.DAILY:
            factors["work"] += 20

    dangerous_tasks = child.dangerous_tasks_performed or []
    factors["dangerous_tasks"] = min(len(dangerous_tasks) * 10, 25)

    score = min(sum(factors.values()), 100)
    return float(score), factors


def risk_level_from_score(score: float) -> RiskLevel:
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 40:
        return RiskLevel.MEDIUM
    if score >= 20:
        return RiskLevel.LOW
    return RiskLevel.NONE


def _risk_label(level: RiskLevel) -> str:
    return {
        RiskLevel.NONE: "aucun",
        RiskLevel.LOW: "faible",
        RiskLevel.MEDIUM: "moyen",
        RiskLevel.HIGH: "eleve",
        RiskLevel.CRITICAL: "critique",
    }.get(level, level.value)


def _ensure_alert_for_child(db: Session, child: Child) -> None:
    if child.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return

    existing = db.query(Alert).filter(
        Alert.source_entity == "children",
        Alert.source_id == child.id,
        Alert.alert_type == AlertType.HIGH_RISK_CHILD,
        Alert.status != AlertStatus.RESOLVED,
    ).first()
    if existing:
        return

    alert = Alert(
        source_entity="children",
        source_id=child.id,
        alert_type=AlertType.HIGH_RISK_CHILD,
        priority=Priority.HIGH if child.risk_level == RiskLevel.CRITICAL else Priority.MEDIUM,
        title=f"Enfant a risque {_risk_label(child.risk_level)}",
        message=(
            f"{child.first_name} {child.last_name} a ete classe "
            f"au niveau de risque {_risk_label(child.risk_level)}."
        ),
        alert_metadata={
            "child_id": child.id,
            "producer_id": child.producer_id,
            "risk_level": child.risk_level.value,
            "risk_score": float(child.risk_score or 0),
        },
    )
    db.add(alert)


def _child_response(child: Child, include_sensitive: bool = True) -> dict:
    data = ChildResponse.model_validate(child).model_dump()
    if include_sensitive:
        data["privacy_redacted"] = False
        return data

    first_initial = child.first_name[:1].upper() if child.first_name else "?"
    data.update({
        "first_name": first_initial,
        "last_name": "Confidentiel",
        "date_of_birth": date(child.date_of_birth.year, 1, 1),
        "birth_certificate_number": None,
        "school_name": None,
        "dangerous_tasks_performed": [],
        "privacy_redacted": True,
    })
    return data


@router.get("")
def list_children(
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    risk_level: Optional[RiskLevel] = None,
    school_status: Optional[SchoolStatus] = None,
    producer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(Child).filter(Child.is_active == True)

    if risk_level:
        query = query.filter(Child.risk_level == risk_level)
    if school_status:
        query = query.filter(Child.school_status == school_status)
    if producer_id:
        query = query.filter(Child.producer_id == producer_id)

    children = query.order_by(Child.created_at.desc()).offset(skip).limit(limit).all()
    include_sensitive = can_view_sensitive(current_user)
    response = [_child_response(child, include_sensitive) for child in children]
    record_privacy_access(
        db,
        current_user,
        action="list_children",
        source_entity="children",
        redacted=not include_sensitive,
        metadata={"count": len(children), "risk_level": risk_level.value if risk_level else None},
    )
    db.commit()
    return response


def _alert_to_response(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type.value,
        "priority": alert.priority.value,
        "source_entity": alert.source_entity,
        "source_id": alert.source_id,
        "title": alert.title,
        "message": alert.message,
        "status": alert.status.value,
        "created_at": alert.created_at,
    }


@router.get("/alerts", response_model=List[AlertResponse])
def list_alerts(
    unresolved_only: bool = True,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Alert).filter(Alert.source_entity == "children")
    if unresolved_only:
        query = query.filter(Alert.status != AlertStatus.RESOLVED)
    return [_alert_to_response(alert) for alert in query.order_by(Alert.created_at.desc()).limit(limit).all()]


@router.post("/alerts/{alert_id:int}/resolve", status_code=200)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvee.")

    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Alerte resolue"}


@router.get("/stats/summary")
def get_summary_stats(db: Session = Depends(get_db)):
    total = db.query(Child).filter(Child.is_active == True).count()
    by_risk = {}
    for level in RiskLevel:
        count = db.query(Child).filter(
            Child.is_active == True,
            Child.risk_level == level,
        ).count()
        if count:
            by_risk[level.value] = count

    enrolled = db.query(Child).filter(
        Child.is_active == True,
        Child.school_status == SchoolStatus.ENROLLED,
    ).count()
    working = db.query(Child).filter(
        Child.is_active == True,
        Child.is_working_on_farm == True,
    ).count()
    active_alerts = db.query(Alert).filter(
        Alert.source_entity == "children",
        Alert.status != AlertStatus.RESOLVED,
    ).count()

    return {
        "total_children": total,
        "by_risk_level": by_risk,
        "school_enrollment_rate": round(enrolled / total * 100, 1) if total else 0,
        "children_working": working,
        "active_alerts": active_alerts,
    }


@router.get("/{child_id:int}")
def get_child(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    child = db.query(Child).filter(Child.id == child_id, Child.is_active == True).first()
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")
    include_sensitive = can_view_sensitive(current_user)
    response = _child_response(child, include_sensitive)
    record_privacy_access(
        db,
        current_user,
        action="view_child",
        source_entity="children",
        source_id=child.id,
        redacted=not include_sensitive,
        metadata={"producer_id": child.producer_id, "risk_level": child.risk_level.value},
    )
    db.commit()
    return response


@router.post("", response_model=ChildResponse, status_code=201)
def create_child(
    child_data: ChildCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    producer = db.query(Producer).filter(Producer.id == child_data.producer_id).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur non trouve.")

    score, factors = calculate_risk_score(child_data)
    risk_level = risk_level_from_score(score)

    child = Child(
        producer_id=child_data.producer_id,
        first_name=child_data.first_name,
        last_name=child_data.last_name,
        date_of_birth=child_data.date_of_birth,
        gender=child_data.gender,
        birth_certificate_number=child_data.birth_certificate_number,
        school_status=child_data.school_status,
        school_name=child_data.school_name,
        is_working_on_farm=child_data.is_working_on_farm,
        work_frequency=child_data.work_frequency,
        dangerous_tasks_performed=child_data.dangerous_tasks_performed,
        risk_score=score,
        risk_level=risk_level,
        risk_factors=factors,
    )

    db.add(child)
    db.flush()
    _ensure_alert_for_child(db, child)
    ensure_remediation_plan_for_child(db, child)
    db.commit()
    db.refresh(child)
    return child


@router.put("/{child_id:int}", response_model=ChildResponse)
def update_child(
    child_id: int,
    child_data: ChildUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    child = db.query(Child).filter(Child.id == child_id, Child.is_active == True).first()
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    update_data = child_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(child, field, value)

    if any(
        field in update_data
        for field in (
            "date_of_birth",
            "school_status",
            "is_working_on_farm",
            "work_frequency",
            "dangerous_tasks_performed",
        )
    ):
        temp = ChildCreate(
            producer_id=child.producer_id,
            first_name=child.first_name,
            last_name=child.last_name,
            date_of_birth=child.date_of_birth,
            gender=child.gender,
            birth_certificate_number=child.birth_certificate_number,
            school_status=child.school_status,
            school_name=child.school_name,
            is_working_on_farm=child.is_working_on_farm,
            work_frequency=child.work_frequency,
            dangerous_tasks_performed=child.dangerous_tasks_performed,
        )
        score, factors = calculate_risk_score(temp)
        child.risk_score = score
        child.risk_level = risk_level_from_score(score)
        child.risk_factors = factors
        _ensure_alert_for_child(db, child)

    db.commit()
    db.refresh(child)
    return child


@router.delete("/{child_id:int}", status_code=204)
def delete_child(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin"})
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    child.is_active = False
    db.commit()
    return None


@router.post("/assessments", status_code=201)
def create_assessment(
    data: RiskAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    child = db.query(Child).filter(Child.id == data.child_id, Child.is_active == True).first()
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    assessor_id = data.assessor_id
    if assessor_id is None:
        assessor = db.query(User).first()
        if not assessor:
            raise HTTPException(status_code=400, detail="Aucun utilisateur disponible comme evaluateur.")
        assessor_id = assessor.id

    risk_factors = dict(data.risk_factors or {})
    if data.notes:
        risk_factors["notes"] = data.notes

    assessment = RiskAssessment(
        producer_id=child.producer_id,
        child_id=child.id,
        assessment_type=data.assessment_type,
        assessment_date=date.today(),
        overall_risk_score=data.overall_risk_score,
        overall_risk_level=data.overall_risk_level,
        risk_factors=risk_factors,
        assessor_id=assessor_id,
        status=AssessmentStatus.COMPLETED,
    )

    child.risk_score = data.overall_risk_score
    child.risk_level = data.overall_risk_level
    child.risk_factors = risk_factors
    child.last_assessment_date = date.today()

    db.add(assessment)
    db.flush()
    _ensure_alert_for_child(db, child)
    ensure_remediation_plan_for_child(db, child)
    db.commit()
    db.refresh(assessment)

    return {"message": "Evaluation creee", "assessment_id": assessment.id}
