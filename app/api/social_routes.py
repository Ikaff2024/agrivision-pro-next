from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FarmForceAssessment, Producer, User
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
    SsrteCommunityProfile,
    WorkFrequency,
)

SCORING_METHODOLOGY_VERSION = "2.0"
from app.api.cacaoguard_ops_routes import ensure_remediation_plan_for_child
from app.api.cacaoguard_ops_routes import record_privacy_access
from app.services.social_scope import coop_alert_ids, coop_producer_ids

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
    # Authentification OBLIGATOIRE : plus d'accès anonyme aux données CacaoGuard.
    if user is None:
        raise HTTPException(status_code=401, detail="Authentification requise.")
    if user.role not in allowed:
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
    school_distance_km: Optional[float] = Field(None, ge=0, le=100)
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
    school_distance_km: Optional[float] = Field(None, ge=0, le=100)
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
    school_distance_km: Optional[float] = None
    is_working_on_farm: bool
    work_frequency: WorkFrequency
    dangerous_tasks_performed: Optional[List[str]]
    risk_score: float
    risk_level: RiskLevel
    risk_factors: Optional[dict] = None
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


def _compute_economic_risk(db: Session, producer_id: int) -> int:
    """0-10 pts derives du dernier FarmForceAssessment du producteur.

    - profit_cfa negatif -> 10 pts (exploitation deficitaire, pression maximale)
    - rendement quotidien familial < 1000 FCFA/jour -> 7 pts (sous seuil pauvrete)
    - rendement quotidien familial < 2500 FCFA/jour -> 4 pts (sous SMIG ivoirien)
    - sinon ou pas de donnees -> 0 pts (pas de signal, on ne penalise pas)
    """
    if not producer_id:
        return 0
    assessment = (
        db.query(FarmForceAssessment)
        .filter(FarmForceAssessment.producer_id == producer_id)
        .order_by(FarmForceAssessment.created_at.desc())
        .first()
    )
    if not assessment:
        return 0
    if assessment.profit_cfa is not None and float(assessment.profit_cfa) < 0:
        return 10
    rpd = assessment.return_per_family_day_cfa
    if rpd is None:
        return 0
    rpd_value = float(rpd)
    if rpd_value < 1000:
        return 7
    if rpd_value < 2500:
        return 4
    return 0


def _compute_geographic_risk(
    school_distance_km: Optional[float],
    db: Session,
    producer_id: int,
) -> int:
    """0-5 pts derives de la distance ecole.

    Priorite : distance saisie sur l'enfant > profil communaute SSRTE de la localite.
    - aucune ecole disponible dans la communaute -> 5 pts
    - distance > 5 km -> 5 pts
    - distance > 3 km -> 3 pts
    - distance > 1.5 km -> 1 pt
    - sinon -> 0 pts
    """
    distance = school_distance_km
    if distance is None and producer_id:
        producer = db.query(Producer).filter(Producer.id == producer_id).first()
        if producer and producer.localite:
            profile = (
                db.query(SsrteCommunityProfile)
                .filter(SsrteCommunityProfile.locality == producer.localite)
                .order_by(SsrteCommunityProfile.interview_date.desc())
                .first()
            )
            if profile:
                if not profile.school_available:
                    return 5
                if profile.nearest_school_distance_km is not None:
                    distance = float(profile.nearest_school_distance_km)
    if distance is None:
        return 0
    if distance > 5:
        return 5
    if distance > 3:
        return 3
    if distance > 1.5:
        return 1
    return 0


def _compute_history_risk(db: Session, child_id: Optional[int]) -> int:
    """0-5 pts derives de l'historique d'evaluations de l'enfant.

    - >= 2 evaluations HIGH/CRITICAL anterieures -> 5 pts (risque recurrent)
    - 1 evaluation HIGH/CRITICAL anterieure -> 3 pts
    - sinon -> 0 pts (premiere evaluation ou historique sain)
    """
    if not child_id:
        return 0
    count = (
        db.query(RiskAssessment)
        .filter(
            RiskAssessment.child_id == child_id,
            RiskAssessment.overall_risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
        )
        .count()
    )
    if count >= 2:
        return 5
    if count == 1:
        return 3
    return 0


def calculate_risk_score(
    child: ChildCreate,
    *,
    db: Optional[Session] = None,
    producer_id: Optional[int] = None,
    child_id: Optional[int] = None,
) -> tuple[float, dict]:
    """Calcule le score de risque CacaoGuard sur 6 facteurs (methodologie v2.0).

    Total max 100 :
      - age (0-25) : age critique pour travail enfant
      - school (0-25) : statut scolaire de l'enfant
      - work (0-20) : statut + frequence de travail sur ferme
      - dangerous_tasks (0-10) : taches dangereuses observees
      - economic (0-10) : pression economique du menage (FarmForce)
      - geographic (0-5) : eloignement de l'ecole (Child / SSRTE communaute)
      - history (0-5) : recurrence du risque sur evaluations precedentes

    Les 3 facteurs de contexte (economic/geographic/history) sont calcules a 0
    si db n'est pas fourni, ce qui garde le scoring deterministe et testable
    en isolation.
    """
    factors = {
        "age": 0,
        "school": 0,
        "work": 0,
        "dangerous_tasks": 0,
        "economic": 0,
        "geographic": 0,
        "history": 0,
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
        work_score = 5
        if child.work_frequency == WorkFrequency.OCCASIONAL:
            work_score += 5
        elif child.work_frequency == WorkFrequency.REGULAR:
            work_score += 10
        elif child.work_frequency == WorkFrequency.DAILY:
            work_score += 15
        factors["work"] = min(work_score, 20)

    dangerous_tasks = child.dangerous_tasks_performed or []
    factors["dangerous_tasks"] = min(len(dangerous_tasks) * 5, 10)

    if db is not None:
        resolved_producer = producer_id or child.producer_id
        factors["economic"] = _compute_economic_risk(db, resolved_producer)
        factors["geographic"] = _compute_geographic_risk(
            child.school_distance_km, db, resolved_producer
        )
        factors["history"] = _compute_history_risk(db, child_id)

    score = min(sum(factors.values()), 100)
    return float(score), factors


def risk_level_from_score(score: float) -> RiskLevel:
    """Seuils alignes sur la methodologie v2.0 (6 facteurs).

    Le score intrinseque max (sans contexte) plafonne a 80 (25+25+20+10),
    donc un cas intrinsequement critique doit pouvoir basculer CRITICAL
    sans dependre des facteurs de contexte (qui peuvent etre absents en
    debut de programme). Les seuils sont 5-15 pts plus bas que l'ancienne
    methodologie (v1.x) pour refleter cela.
    """
    if score >= 70:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 30:
        return RiskLevel.MEDIUM
    if score >= 15:
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
    require_role(current_user, {"admin", "agronomist", "technician", "viewer"})
    # Cloisonnement : uniquement les enfants des producteurs de la coopérative.
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    query = db.query(Child).filter(
        Child.is_active == True,
        Child.producer_id.in_(pids if pids else [-1]),
    )

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
    current_user: User | None = Depends(get_optional_current_user),
):
    # Cloisonnement : uniquement les alertes rattachées à la coopérative.
    require_role(current_user, {"admin", "agronomist", "technician", "viewer"})
    allowed = coop_alert_ids(db, current_user.cooperative_id if current_user else None)
    query = db.query(Alert).filter(
        Alert.source_entity == "children",
        Alert.id.in_(allowed if allowed else [-1]),
    )
    if unresolved_only:
        query = query.filter(Alert.status != AlertStatus.RESOLVED)
    return [_alert_to_response(alert) for alert in query.order_by(Alert.created_at.desc()).limit(limit).all()]


@router.post("/alerts/{alert_id:int}/resolve", status_code=200)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    # Cloisonnement : on ne peut résoudre qu'une alerte de sa coopérative.
    allowed = coop_alert_ids(db, current_user.cooperative_id if current_user else None)
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert or alert.id not in allowed:
        raise HTTPException(status_code=404, detail="Alerte non trouvee.")

    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Alerte resolue"}


@router.get("/stats/summary")
def get_summary_stats(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician", "viewer"})
    # Cloisonnement : statistiques bornées à la coopérative de l'utilisateur.
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    pid_f = Child.producer_id.in_(pids if pids else [-1])
    total = db.query(Child).filter(Child.is_active == True, pid_f).count()
    by_risk = {}
    for level in RiskLevel:
        count = db.query(Child).filter(
            Child.is_active == True,
            pid_f,
            Child.risk_level == level,
        ).count()
        if count:
            by_risk[level.value] = count

    enrolled = db.query(Child).filter(
        Child.is_active == True,
        pid_f,
        Child.school_status == SchoolStatus.ENROLLED,
    ).count()
    working = db.query(Child).filter(
        Child.is_active == True,
        pid_f,
        Child.is_working_on_farm == True,
    ).count()
    allowed = coop_alert_ids(db, current_user.cooperative_id if current_user else None)
    active_alerts = db.query(Alert).filter(
        Alert.source_entity == "children",
        Alert.status != AlertStatus.RESOLVED,
        Alert.id.in_(allowed if allowed else [-1]),
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
    require_role(current_user, {"admin", "agronomist", "technician", "viewer"})
    child = db.query(Child).filter(Child.id == child_id, Child.is_active == True).first()
    # Cloisonnement : l'enfant doit appartenir à un producteur de la coopérative.
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    if not child or child.producer_id not in pids:
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
    # Cloisonnement : interdit de créer un enfant sous le producteur d'une autre coop.
    coop_id = current_user.cooperative_id if current_user else None
    producer = db.query(Producer).filter(Producer.id == child_data.producer_id).first()
    if not producer or (coop_id is not None and producer.cooperative_id != coop_id):
        raise HTTPException(status_code=404, detail="Producteur non trouve.")

    score, factors = calculate_risk_score(
        child_data, db=db, producer_id=child_data.producer_id, child_id=None
    )
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
        school_distance_km=Decimal(str(child_data.school_distance_km))
        if child_data.school_distance_km is not None
        else None,
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
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    if not child or child.producer_id not in pids:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    update_data = child_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "school_distance_km" and value is not None:
            value = Decimal(str(value))
        setattr(child, field, value)

    if any(
        field in update_data
        for field in (
            "date_of_birth",
            "school_status",
            "school_distance_km",
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
            school_distance_km=float(child.school_distance_km)
            if child.school_distance_km is not None
            else None,
            is_working_on_farm=child.is_working_on_farm,
            work_frequency=child.work_frequency,
            dangerous_tasks_performed=child.dangerous_tasks_performed,
        )
        score, factors = calculate_risk_score(
            temp, db=db, producer_id=child.producer_id, child_id=child.id
        )
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
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    if not child or child.producer_id not in pids:
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
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    child = db.query(Child).filter(Child.id == data.child_id, Child.is_active == True).first()
    if not child or child.producer_id not in pids:
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
        methodology_version=SCORING_METHODOLOGY_VERSION,
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


@router.post("/{child_id:int}/calculate-risk")
def recompute_child_risk(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Recalcule le score sur l'etat courant en base sans persister.

    Utile pour l'auditeur et le frontend : permet de verifier le score
    avec la methodologie courante apres mise a jour FarmForce/SSRTE,
    sans declencher d'alerte ou de plan de remediation.
    """
    require_role(current_user, {"admin", "agronomist", "technician"})
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    child = db.query(Child).filter(Child.id == child_id, Child.is_active == True).first()
    if not child or child.producer_id not in pids:
        raise HTTPException(status_code=404, detail="Enfant non trouve.")

    snapshot = ChildCreate(
        producer_id=child.producer_id,
        first_name=child.first_name,
        last_name=child.last_name,
        date_of_birth=child.date_of_birth,
        gender=child.gender,
        birth_certificate_number=child.birth_certificate_number,
        school_status=child.school_status,
        school_name=child.school_name,
        school_distance_km=float(child.school_distance_km)
        if child.school_distance_km is not None
        else None,
        is_working_on_farm=child.is_working_on_farm,
        work_frequency=child.work_frequency,
        dangerous_tasks_performed=child.dangerous_tasks_performed,
    )
    score, factors = calculate_risk_score(
        snapshot, db=db, producer_id=child.producer_id, child_id=child.id
    )
    return {
        "child_id": child.id,
        "methodology_version": SCORING_METHODOLOGY_VERSION,
        "risk_score": score,
        "risk_level": risk_level_from_score(score).value,
        "risk_factors": factors,
        "persisted_risk_score": float(child.risk_score or 0),
        "persisted_risk_level": child.risk_level.value if child.risk_level else None,
        "drift": round(score - float(child.risk_score or 0), 2),
    }
