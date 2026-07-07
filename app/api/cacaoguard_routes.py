from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth_service import decode_token
from app.db.database import get_db
from app.db.models import FarmForceAssessment, Plantation, Producer, User
from app.services.social_scope import coop_alert_ids
from app.db.models_social import (
    Alert,
    AlertStatus,
    MonitoringVisit,
    RemediationPlan,
    RemediationStatus,
    Child,
    RiskLevel,
    SchoolStatus,
    SsrteHouseholdProfile,
    SsrtePlantationVisit,
    TraceabilityBlock,
    BlockStatus,
    VisitStatus,
)

router = APIRouter(prefix="/cacaoguard", tags=["CacaoGuard"])
optional_bearer = HTTPBearer(auto_error=False)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        return None
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        return None
    return user


def _producer_subq(db: Session, cooperative_id: int | None):
    if cooperative_id is None:
        return None
    return db.query(Producer.id).filter(Producer.cooperative_id == cooperative_id).subquery()


def _plantation_subq(db: Session, cooperative_id: int | None):
    if cooperative_id is None:
        return None
    return db.query(Plantation.id).filter(Plantation.cooperative_id == cooperative_id).subquery()


@router.get("/summary")
def get_cacaoguard_summary(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _producer_subq(db, coop_id)
    plant_subq = _plantation_subq(db, coop_id)

    prod_filter = [Producer.cooperative_id == coop_id] if coop_id else []
    plant_filter = [Plantation.cooperative_id == coop_id] if coop_id else []
    child_filter = [Child.producer_id.in_(prod_subq)] if prod_subq is not None else []
    visit_filter = [MonitoringVisit.producer_id.in_(prod_subq)] if prod_subq is not None else []
    block_filter = [TraceabilityBlock.producer_id.in_(prod_subq)] if prod_subq is not None else []
    plan_filter = [RemediationPlan.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ssrte_hh_filter = [SsrteHouseholdProfile.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ssrte_pv_filter = [SsrtePlantationVisit.producer_id.in_(prod_subq)] if prod_subq is not None else []
    ff_filter = [FarmForceAssessment.producer_id.in_(prod_subq)] if prod_subq is not None else []

    total_producers = db.query(func.count(Producer.id)).filter(Producer.is_active == True, *prod_filter).scalar() or 0
    total_plantations = db.query(func.count(Plantation.id)).filter(*plant_filter).scalar() or 0
    total_children = db.query(func.count(Child.id)).filter(Child.is_active == True, *child_filter).scalar() or 0

    high_risk_children = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
        *child_filter,
    ).scalar() or 0
    medium_risk_children = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.risk_level == RiskLevel.MEDIUM,
        *child_filter,
    ).scalar() or 0
    enrolled_children = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.school_status == SchoolStatus.ENROLLED,
        *child_filter,
    ).scalar() or 0
    working_children = db.query(func.count(Child.id)).filter(
        Child.is_active == True,
        Child.is_working_on_farm == True,
        *child_filter,
    ).scalar() or 0
    # Alertes ouvertes CLOISONNÉES : Alert n'a pas de cooperative_id, on résout le
    # périmètre via coop_alert_ids (sinon le compteur fuite entre coopératives).
    alert_q = db.query(func.count(Alert.id)).filter(Alert.status != AlertStatus.RESOLVED)
    if coop_id is not None:
        allowed_alert_ids = coop_alert_ids(db, coop_id)
        alert_q = alert_q.filter(Alert.id.in_(allowed_alert_ids if allowed_alert_ids else [-1]))
    active_alerts = alert_q.scalar() or 0
    traceability_blocks = db.query(func.count(TraceabilityBlock.id)).filter(
        TraceabilityBlock.status == BlockStatus.ACTIVE,
        *block_filter,
    ).scalar() or 0
    scheduled_visits = db.query(func.count(MonitoringVisit.id)).filter(
        MonitoringVisit.status == VisitStatus.SCHEDULED,
        *visit_filter,
    ).scalar() or 0
    active_remediation_plans = db.query(func.count(RemediationPlan.id)).filter(
        RemediationPlan.status.in_([
            RemediationStatus.DRAFT,
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
            RemediationStatus.IN_PROGRESS,
            RemediationStatus.ESCALATED,
        ]),
        *plan_filter,
    ).scalar() or 0
    ssrte_households = db.query(func.count(SsrteHouseholdProfile.id)).filter(*ssrte_hh_filter).scalar() or 0
    ssrte_plantation_visits = db.query(func.count(SsrtePlantationVisit.id)).filter(*ssrte_pv_filter).scalar() or 0
    ssrte_suspicions = db.query(func.count(SsrtePlantationVisit.id)).filter(
        SsrtePlantationVisit.suspected_child_labor == True,
        *ssrte_pv_filter,
    ).scalar() or 0
    farmforce_assessments = db.query(func.count(FarmForceAssessment.id)).filter(*ff_filter).scalar() or 0
    farmforce_profit = db.query(
        func.coalesce(func.sum(FarmForceAssessment.profit_cfa), 0),
    ).filter(*ff_filter).scalar() or 0
    farmforce_avg_return = db.query(
        func.avg(FarmForceAssessment.return_per_family_day_cfa),
    ).filter(*ff_filter).scalar()
    farmforce_negative_profit = db.query(func.count(FarmForceAssessment.id)).filter(
        FarmForceAssessment.profit_cfa < 0,
        *ff_filter,
    ).scalar() or 0

    by_risk = {}
    for level in RiskLevel:
        count = db.query(func.count(Child.id)).filter(
            Child.is_active == True,
            Child.risk_level == level,
            *child_filter,
        ).scalar() or 0
        by_risk[level.value] = count

    return {
        "brand": "CacaoGuard",
        "positioning": "Plateforme cacao: protection enfant, tracabilite et suivi terrain.",
        "total_producers": total_producers,
        "total_plantations": total_plantations,
        "total_children": total_children,
        "high_risk_children": high_risk_children,
        "medium_risk_children": medium_risk_children,
        "school_enrollment_rate": round(enrolled_children / total_children * 100, 1)
        if total_children
        else 0,
        "children_working": working_children,
        "active_alerts": active_alerts,
        "traceability_blocks": traceability_blocks,
        "scheduled_visits": scheduled_visits,
        "active_remediation_plans": active_remediation_plans,
        "ssrte_household_profiles": ssrte_households,
        "ssrte_plantation_visits": ssrte_plantation_visits,
        "ssrte_suspected_child_labor_visits": ssrte_suspicions,
        "farmforce_assessments": farmforce_assessments,
        "farmforce_total_profit_cfa": float(farmforce_profit or 0),
        "farmforce_average_return_per_family_day_cfa": round(float(farmforce_avg_return), 2)
        if farmforce_avg_return is not None
        else None,
        "farmforce_negative_profit_assessments": farmforce_negative_profit,
        "by_risk_level": by_risk,
    }
