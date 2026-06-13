from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth_service import decode_token, get_current_user
from app.db.database import get_db
from app.db.models import Plantation, Producer, User
from app.db.models_social import (
    Alert,
    AlertStatus,
    AlertType,
    BlockReason,
    BlockStatus,
    Priority,
    RiskLevel,
    SsrteCommunityProfile,
    SsrteHouseholdProfile,
    SsrtePlantationVisit,
    TraceabilityBlock,
)

router = APIRouter(prefix="/ssrte", tags=["SSRTE"])
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


def _coop_producer_subq(db: Session, cooperative_id: int | None):
    """Sous-requete des producteurs d'une coop (None => pas de filtre = global)."""
    if cooperative_id is None:
        return None
    return db.query(Producer.id).filter(Producer.cooperative_id == cooperative_id).subquery()


class CommunityProfilePayload(BaseModel):
    locality: str = Field(..., min_length=2, max_length=200)
    section: Optional[str] = Field(None, max_length=100)
    interview_date: date = Field(default_factory=date.today)
    respondent_name: Optional[str] = Field(None, max_length=200)
    respondent_role: Optional[str] = Field(None, max_length=100)
    # Identification administrative (A.02-A.06)
    supplier: Optional[str] = Field(None, max_length=200)
    sub_prefecture: Optional[str] = Field(None, max_length=200)
    collection_agent_code: Optional[str] = Field(None, max_length=100)
    collection_agent_name: Optional[str] = Field(None, max_length=200)
    # GPS + heures (A.07a/b/c)
    gps_start: Optional[str] = Field(None, max_length=120)
    time_start: Optional[str] = Field(None, max_length=20)
    gps_end: Optional[str] = Field(None, max_length=120)
    time_end: Optional[str] = Field(None, max_length=20)
    school_available: bool = False
    nearest_school_distance_km: Optional[float] = Field(None, ge=0)
    has_child_protection_committee: bool = False
    committee_members: list[dict] = Field(default_factory=list)
    risks_identified: list[str] = Field(default_factory=list)
    # services_available porte aussi : electricity_origin, water_distance,
    # secondary_classes_count, secondary_school_distance_km, org_state/ngo/other.
    services_available: dict = Field(default_factory=dict)
    schools: list[dict] = Field(default_factory=list)
    section_notes: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class HouseholdProfilePayload(BaseModel):
    producer_id: int
    interview_date: date = Field(default_factory=date.today)
    interviewer_name: Optional[str] = Field(None, max_length=200)
    # Identification administrative (B.02-B.07)
    supplier: Optional[str] = Field(None, max_length=200)
    sub_prefecture: Optional[str] = Field(None, max_length=200)
    locality: Optional[str] = Field(None, max_length=200)
    collection_agent_code: Optional[str] = Field(None, max_length=100)
    producer_ssrte_code: Optional[str] = Field(None, max_length=100)
    # GPS + heures (B.09a/b/c)
    gps_start: Optional[str] = Field(None, max_length=120)
    time_start: Optional[str] = Field(None, max_length=20)
    time_end: Optional[str] = Field(None, max_length=20)
    # Type d'enquete + statut de visite (B.10a/b, B.15)
    survey_type: Optional[str] = Field(None, max_length=40)
    producer_available: Optional[bool] = None
    unavailable_reason: Optional[str] = Field(None, max_length=60)
    visited_person_status: Optional[str] = Field(None, max_length=60)
    # Travailleurs (B.18b/c/d)
    external_workers_count: Optional[int] = Field(None, ge=0)
    daily_workers_count: Optional[int] = Field(None, ge=0)
    non_daily_workers: list[dict] = Field(default_factory=list)
    section_notes: dict = Field(default_factory=dict)
    household_size: Optional[int] = Field(None, ge=0)
    children_count: Optional[int] = Field(None, ge=0)
    school_age_children_count: Optional[int] = Field(None, ge=0)
    enrolled_children_count: Optional[int] = Field(None, ge=0)
    household_members: list[dict] = Field(default_factory=list)
    vulnerabilities: list[str] = Field(default_factory=list)
    child_work_declarations: list[dict] = Field(default_factory=list)
    school_constraints: list[str] = Field(default_factory=list)
    farm_info: dict = Field(default_factory=dict)
    # Situation économique du ménage (Fiche B section 7)
    housing_type: Optional[str] = Field(None, max_length=40)
    household_assets: list[str] = Field(default_factory=list)
    allow_worker_interview: Optional[bool] = None
    head_photo_ref: Optional[str] = Field(None, max_length=255)
    consent_given: bool = False
    signature_data: Optional[dict] = None
    notes: Optional[str] = None


class PlantationVisitPayload(BaseModel):
    plantation_id: int
    producer_id: Optional[int] = None
    visit_date: date = Field(default_factory=date.today)
    interviewer_name: Optional[str] = Field(None, max_length=200)
    gps_location: Optional[str] = Field(None, max_length=255)
    gps_accuracy: Optional[float] = Field(None, ge=0)
    # Identification administrative (C.01-C.07)
    section: Optional[str] = Field(None, max_length=100)
    supplier: Optional[str] = Field(None, max_length=200)
    sub_prefecture: Optional[str] = Field(None, max_length=200)
    locality: Optional[str] = Field(None, max_length=200)
    collection_agent_code: Optional[str] = Field(None, max_length=100)
    producer_ssrte_code: Optional[str] = Field(None, max_length=100)
    # Heures (C.09b/c)
    time_start: Optional[str] = Field(None, max_length=20)
    time_end: Optional[str] = Field(None, max_length=20)
    # Comptages (C.10a/b/d, C.11, C.12)
    adults_count: Optional[int] = Field(None, ge=0)
    daily_workers_count: Optional[int] = Field(None, ge=0)
    allow_worker_interview: Optional[bool] = None
    children_present_count: Optional[int] = Field(None, ge=0)
    non_household_children_count: Optional[int] = Field(None, ge=0)
    non_household_children: list[dict] = Field(default_factory=list)
    section_notes: dict = Field(default_factory=dict)
    checklist_data: dict = Field(default_factory=dict)
    children_observed: list[dict] = Field(default_factory=list)
    adults_observed: list[dict] = Field(default_factory=list)
    workers_present: list[dict] = Field(default_factory=list)
    dangerous_tasks_observed: list[str] = Field(default_factory=list)
    suspected_child_labor: bool = False
    immediate_actions_taken: Optional[str] = None
    photos: list[dict] = Field(default_factory=list)
    consent_given: bool = False
    producer_signature_data: Optional[dict] = None
    assessor_signature_data: Optional[dict] = None
    notes: Optional[str] = None


def _risk_level_from_score(score: float) -> RiskLevel:
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 40:
        return RiskLevel.MEDIUM
    if score >= 20:
        return RiskLevel.LOW
    return RiskLevel.NONE


def _score_household(data: HouseholdProfilePayload) -> tuple[float, RiskLevel]:
    score = 0.0
    school_age = data.school_age_children_count or 0
    enrolled = data.enrolled_children_count or 0
    if school_age and enrolled < school_age:
        score += min((school_age - enrolled) * 12, 30)
    if data.vulnerabilities:
        score += min(len(data.vulnerabilities) * 8, 24)
    work_rows = data.child_work_declarations or []
    score += min(len(work_rows) * 10, 30)
    dangerous = sum(1 for row in work_rows if row.get("dangerous") or row.get("tache_dangereuse"))
    score += min(dangerous * 18, 36)
    if data.school_constraints:
        score += min(len(data.school_constraints) * 5, 15)
    score = min(score, 100)
    return score, _risk_level_from_score(score)


def _producer_name(producer: Producer | None) -> str:
    return producer.nom_complet if producer else "Producteur inconnu"


def _plantation_name(plantation: Plantation | None) -> str:
    return plantation.name if plantation else "Plantation inconnue"


def _first_user_id(db: Session) -> int | None:
    user = db.query(User).first()
    return user.id if user else None


def _alert_for_ssrte_visit(db: Session, visit: SsrtePlantationVisit) -> None:
    if not visit.suspected_child_labor and not visit.dangerous_tasks_observed:
        return
    # Idempotent : une seule alerte par visite (pas de doublon a l'edition/cloture).
    existing = db.query(Alert).filter(
        Alert.source_entity == "ssrte_plantation_visits",
        Alert.source_id == visit.id,
    ).first()
    if existing:
        return
    title = "Suspicion SSRTE en plantation"
    message = f"Visite SSRTE C sur {_plantation_name(visit.plantation)}: action de suivi requise."
    db.add(Alert(
        source_entity="ssrte_plantation_visits",
        source_id=visit.id,
        alert_type=AlertType.HIGH_RISK_CHILD,
        priority=Priority.HIGH,
        title=title,
        message=message,
        status=AlertStatus.NEW,
        alert_metadata={
            "producer_id": visit.producer_id,
            "plantation_id": visit.plantation_id,
            "suspected_child_labor": bool(visit.suspected_child_labor),
            "dangerous_tasks_observed": visit.dangerous_tasks_observed or [],
        },
    ))


def _traceability_block_for_ssrte_visit(db: Session, visit: SsrtePlantationVisit) -> TraceabilityBlock | None:
    if not visit.suspected_child_labor or not visit.producer_id:
        return None

    existing = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id == visit.producer_id,
        TraceabilityBlock.block_reason == BlockReason.CHILD_LABOR_CASE,
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).first()
    if existing:
        return existing

    blocked_by = visit.created_by or _first_user_id(db)
    if not blocked_by:
        return None

    block = TraceabilityBlock(
        producer_id=visit.producer_id,
        block_reason=BlockReason.CHILD_LABOR_CASE,
        block_description=(
            f"Blocage automatique SSRTE: suspicion travail enfant lors de la Fiche C "
            f"sur {_plantation_name(visit.plantation)}."
        ),
        related_case_id=visit.id,
        affects_all_production=True,
        affected_batches=[],
        expected_resolution_date=date.today() + timedelta(days=90),
        status=BlockStatus.ACTIVE,
        blocked_by=blocked_by,
    )
    db.add(block)
    db.flush()
    db.add(Alert(
        source_entity="traceability_blocks",
        source_id=block.id,
        alert_type=AlertType.TRACEABILITY_BLOCK,
        priority=Priority.URGENT,
        title="Blocage tracabilite SSRTE",
        message=f"La production de {_producer_name(visit.producer)} est bloquee jusqu'a clarification du cas SSRTE.",
        status=AlertStatus.NEW,
        alert_metadata={
            "producer_id": visit.producer_id,
            "plantation_id": visit.plantation_id,
            "ssrte_visit_id": visit.id,
        },
    ))
    return block


def community_to_dict(row: SsrteCommunityProfile) -> dict:
    return {
        "id": row.id,
        "locality": row.locality,
        "section": row.section,
        "cooperative_id": row.cooperative_id,
        "interview_date": row.interview_date,
        "respondent_name": row.respondent_name,
        "respondent_role": row.respondent_role,
        "supplier": row.supplier,
        "sub_prefecture": row.sub_prefecture,
        "collection_agent_code": row.collection_agent_code,
        "collection_agent_name": row.collection_agent_name,
        "gps_start": row.gps_start,
        "time_start": row.time_start,
        "gps_end": row.gps_end,
        "time_end": row.time_end,
        "section_notes": row.section_notes or {},
        "school_available": bool(row.school_available),
        "nearest_school_distance_km": float(row.nearest_school_distance_km) if row.nearest_school_distance_km is not None else None,
        "has_child_protection_committee": bool(row.has_child_protection_committee),
        "committee_members": row.committee_members or [],
        "risks_identified": row.risks_identified or [],
        "services_available": row.services_available or {},
        "schools": row.schools or [],
        "notes": row.notes,
        "status": row.status or "draft",
        "finalized_at": row.finalized_at,
        "created_at": row.created_at,
    }


def household_to_dict(row: SsrteHouseholdProfile) -> dict:
    return {
        "id": row.id,
        "producer_id": row.producer_id,
        "producer_name": _producer_name(row.producer),
        "interview_date": row.interview_date,
        "interviewer_name": row.interviewer_name,
        "supplier": row.supplier,
        "sub_prefecture": row.sub_prefecture,
        "locality": row.locality,
        "collection_agent_code": row.collection_agent_code,
        "producer_ssrte_code": row.producer_ssrte_code,
        "gps_start": row.gps_start,
        "time_start": row.time_start,
        "time_end": row.time_end,
        "survey_type": row.survey_type,
        "producer_available": row.producer_available,
        "unavailable_reason": row.unavailable_reason,
        "visited_person_status": row.visited_person_status,
        "external_workers_count": row.external_workers_count,
        "daily_workers_count": row.daily_workers_count,
        "non_daily_workers": row.non_daily_workers or [],
        "section_notes": row.section_notes or {},
        "household_size": row.household_size,
        "children_count": row.children_count,
        "school_age_children_count": row.school_age_children_count,
        "enrolled_children_count": row.enrolled_children_count,
        "household_members": row.household_members or [],
        "vulnerabilities": row.vulnerabilities or [],
        "child_work_declarations": row.child_work_declarations or [],
        "school_constraints": row.school_constraints or [],
        "farm_info": row.farm_info or {},
        "housing_type": row.housing_type,
        "household_assets": row.household_assets or [],
        "allow_worker_interview": row.allow_worker_interview,
        "head_photo_ref": row.head_photo_ref,
        "risk_score": float(row.risk_score or 0),
        "risk_level": row.risk_level.value,
        "consent_given": bool(row.consent_given),
        "signature_data": row.signature_data,
        "notes": row.notes,
        "status": row.status or "draft",
        "finalized_at": row.finalized_at,
        "created_at": row.created_at,
    }


def visit_to_dict(row: SsrtePlantationVisit) -> dict:
    return {
        "id": row.id,
        "plantation_id": row.plantation_id,
        "plantation_name": _plantation_name(row.plantation),
        "producer_id": row.producer_id,
        "producer_name": _producer_name(row.producer),
        "visit_date": row.visit_date,
        "interviewer_name": row.interviewer_name,
        "gps_location": row.gps_location,
        "gps_accuracy": row.gps_accuracy,
        "section": row.section,
        "supplier": row.supplier,
        "sub_prefecture": row.sub_prefecture,
        "locality": row.locality,
        "collection_agent_code": row.collection_agent_code,
        "producer_ssrte_code": row.producer_ssrte_code,
        "time_start": row.time_start,
        "time_end": row.time_end,
        "adults_count": row.adults_count,
        "daily_workers_count": row.daily_workers_count,
        "allow_worker_interview": row.allow_worker_interview,
        "children_present_count": row.children_present_count,
        "non_household_children_count": row.non_household_children_count,
        "non_household_children": row.non_household_children or [],
        "section_notes": row.section_notes or {},
        "checklist_data": row.checklist_data or {},
        "children_observed": row.children_observed or [],
        "adults_observed": row.adults_observed or [],
        "workers_present": row.workers_present or [],
        "dangerous_tasks_observed": row.dangerous_tasks_observed or [],
        "suspected_child_labor": bool(row.suspected_child_labor),
        "immediate_actions_taken": row.immediate_actions_taken,
        "photos": row.photos or [],
        "consent_given": bool(row.consent_given),
        "producer_signature_data": row.producer_signature_data,
        "assessor_signature_data": row.assessor_signature_data,
        "notes": row.notes,
        "status": row.status or "draft",
        "finalized_at": row.finalized_at,
        "created_at": row.created_at,
    }


@router.get("/summary")
def ssrte_summary(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _coop_producer_subq(db, coop_id)
    hh_filter = [SsrteHouseholdProfile.producer_id.in_(prod_subq)] if prod_subq is not None else []
    pv_filter = [SsrtePlantationVisit.producer_id.in_(prod_subq)] if prod_subq is not None else []
    com_filter = [SsrteCommunityProfile.cooperative_id == coop_id] if coop_id is not None else []

    households = db.query(func.count(SsrteHouseholdProfile.id)).filter(*hh_filter).scalar() or 0
    visits = db.query(func.count(SsrtePlantationVisit.id)).filter(*pv_filter).scalar() or 0
    communities = db.query(func.count(SsrteCommunityProfile.id)).filter(*com_filter).scalar() or 0
    suspected = db.query(func.count(SsrtePlantationVisit.id)).filter(
        SsrtePlantationVisit.suspected_child_labor == True, *pv_filter,
    ).scalar() or 0
    high_households = db.query(func.count(SsrteHouseholdProfile.id)).filter(
        SsrteHouseholdProfile.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]), *hh_filter,
    ).scalar() or 0
    return {
        "community_profiles": communities,
        "household_profiles": households,
        "plantation_visits": visits,
        "suspected_child_labor_visits": suspected,
        "high_risk_households": high_households,
    }


@router.get("/communities")
def list_communities(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(SsrteCommunityProfile)
    coop_id = current_user.cooperative_id if current_user else None
    if coop_id is not None:
        query = query.filter(SsrteCommunityProfile.cooperative_id == coop_id)
    rows = query.order_by(SsrteCommunityProfile.created_at.desc()).limit(limit).all()
    return [community_to_dict(row) for row in rows]


@router.post("/communities", status_code=201)
def create_community_profile(
    data: CommunityProfilePayload,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    row = SsrteCommunityProfile(
        **data.model_dump(),
        cooperative_id=current_user.cooperative_id if current_user else None,
        created_by=current_user.id if current_user else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return community_to_dict(row)


@router.get("/households")
def list_households(
    producer_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(SsrteHouseholdProfile)
    if producer_id:
        query = query.filter(SsrteHouseholdProfile.producer_id == producer_id)
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _coop_producer_subq(db, coop_id)
    if prod_subq is not None:
        query = query.filter(SsrteHouseholdProfile.producer_id.in_(prod_subq))
    rows = query.order_by(SsrteHouseholdProfile.created_at.desc()).limit(limit).all()
    return [household_to_dict(row) for row in rows]


@router.post("/households", status_code=201)
def create_household_profile(
    data: HouseholdProfilePayload,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    producer = db.query(Producer).filter(Producer.id == data.producer_id, Producer.is_active == True).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    score, level = _score_household(data)
    row = SsrteHouseholdProfile(
        **data.model_dump(),
        risk_score=score,
        risk_level=level,
        created_by=current_user.id if current_user else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return household_to_dict(row)


def _ssrte_coop_id(db, entity):
    """Coop d'une entité SSRTE : cooperative_id direct si présent, sinon via le producteur."""
    cid = getattr(entity, "cooperative_id", None)
    if cid:
        return cid
    pid = getattr(entity, "producer_id", None)
    if not pid:
        return None
    from app.db.models import Producer
    pr = db.query(Producer).filter(Producer.id == pid).first()
    return pr.cooperative_id if pr else None


@router.get("/communities/{community_id}/fichea.pdf")
def download_fichea_pdf(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telecharge la Fiche A (profil localite) au format PDF."""
    from app.services.ssrte_reports import (
        build_fichea_context,
        fichea_filename,
        generate_fichea_pdf,
    )
    profile = db.query(SsrteCommunityProfile).filter(SsrteCommunityProfile.id == community_id).first()
    if not profile or _ssrte_coop_id(db, profile) != current_user.cooperative_id:
        raise HTTPException(status_code=404, detail="Fiche A introuvable.")
    context = build_fichea_context(profile)
    from app.services.reports import coop_brand
    context.update(coop_brand(db, _ssrte_coop_id(db, profile)))
    pdf_bytes = generate_fichea_pdf(context)
    filename = fichea_filename(profile)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/households/{household_id}/ficheb.pdf")
def download_ficheb_pdf(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telecharge la Fiche B (profilage de menage) au format PDF."""
    from app.services.ssrte_reports import (
        build_ficheb_context,
        ficheb_filename,
        generate_ficheb_pdf,
    )
    profile = db.query(SsrteHouseholdProfile).filter(SsrteHouseholdProfile.id == household_id).first()
    if not profile or _ssrte_coop_id(db, profile) != current_user.cooperative_id:
        raise HTTPException(status_code=404, detail="Fiche B introuvable.")
    context = build_ficheb_context(profile)
    from app.services.reports import coop_brand
    context.update(coop_brand(db, _ssrte_coop_id(db, profile)))
    pdf_bytes = generate_ficheb_pdf(context)
    filename = ficheb_filename(profile)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/plantation-visits/{visit_id}/fichec.pdf")
def download_fichec_pdf(
    visit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telecharge la Fiche C (visite de plantation) au format PDF."""
    from app.services.ssrte_reports import (
        build_fichec_context,
        fichec_filename,
        generate_fichec_pdf,
    )
    visit = db.query(SsrtePlantationVisit).filter(SsrtePlantationVisit.id == visit_id).first()
    if not visit or _ssrte_coop_id(db, visit) != current_user.cooperative_id:
        raise HTTPException(status_code=404, detail="Fiche C introuvable.")
    context = build_fichec_context(visit)
    from app.services.reports import coop_brand
    context.update(coop_brand(db, _ssrte_coop_id(db, visit)))
    pdf_bytes = generate_fichec_pdf(context)
    filename = fichec_filename(visit)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/plantation-visits")
def list_plantation_visits(
    plantation_id: Optional[int] = None,
    producer_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(SsrtePlantationVisit)
    if plantation_id:
        query = query.filter(SsrtePlantationVisit.plantation_id == plantation_id)
    if producer_id:
        query = query.filter(SsrtePlantationVisit.producer_id == producer_id)
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _coop_producer_subq(db, coop_id)
    if prod_subq is not None:
        query = query.filter(SsrtePlantationVisit.producer_id.in_(prod_subq))
    rows = query.order_by(SsrtePlantationVisit.created_at.desc()).limit(limit).all()
    return [visit_to_dict(row) for row in rows]


@router.post("/plantation-visits", status_code=201)
def create_plantation_visit(
    data: PlantationVisitPayload,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    plantation = db.query(Plantation).filter(Plantation.id == data.plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    producer_id = data.producer_id or plantation.producer_id
    row = SsrtePlantationVisit(
        **data.model_dump(exclude={"producer_id"}),
        producer_id=producer_id,
        created_by=current_user.id if current_user else None,
    )
    db.add(row)
    db.flush()
    _alert_for_ssrte_visit(db, row)
    _traceability_block_for_ssrte_visit(db, row)
    db.commit()
    db.refresh(row)
    return visit_to_dict(row)


# ── Cycle de vie : modifier (brouillon) / clôturer (définitif) / supprimer ────
# Une fiche reste un BROUILLON modifiable jusqu'à sa clôture. On corrige donc une
# erreur sur la fiche elle-même au lieu d'en recréer une (qui fausserait le
# tableau de bord). Une fiche CLÔTURÉE est verrouillée (intégrité d'audit).

_SSRTE_WRITE_ROLES = {"admin", "agronomist", "technician"}


def _require_ssrte_write(user: User) -> None:
    if user.role not in _SSRTE_WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Action reservee aux roles terrain SSRTE (admin / agronome / technicien).",
        )


def _load_ssrte_writable(db: Session, model, entity_id: int, user: User, *, require_draft: bool):
    """Charge une fiche SSRTE pour écriture : cloisonnée par coop, brouillon exigé."""
    entity = db.query(model).filter(model.id == entity_id).first()
    if not entity or _ssrte_coop_id(db, entity) != user.cooperative_id:
        raise HTTPException(status_code=404, detail="Fiche introuvable.")
    if require_draft and (entity.status or "draft") != "draft":
        raise HTTPException(
            status_code=409,
            detail="Fiche deja cloturee (definitive) : modification impossible. Creez une nouvelle fiche.",
        )
    return entity


def _finalize(entity, user: User) -> None:
    entity.status = "final"
    entity.finalized_at = datetime.utcnow()
    entity.finalized_by = user.email


# ----- Fiche A : communauté ---------------------------------------------------
@router.put("/communities/{community_id}")
def update_community_profile(
    community_id: int,
    data: CommunityProfilePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteCommunityProfile, community_id, current_user, require_draft=True)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return community_to_dict(row)


@router.post("/communities/{community_id}/finalize")
def finalize_community_profile(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteCommunityProfile, community_id, current_user, require_draft=True)
    _finalize(row, current_user)
    db.commit()
    db.refresh(row)
    return community_to_dict(row)


@router.delete("/communities/{community_id}")
def delete_community_profile(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteCommunityProfile, community_id, current_user, require_draft=True)
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": community_id}


# ----- Fiche B / F1 : ménage --------------------------------------------------
@router.put("/households/{household_id}")
def update_household_profile(
    household_id: int,
    data: HouseholdProfilePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteHouseholdProfile, household_id, current_user, require_draft=True)
    score, level = _score_household(data)
    for key, value in data.model_dump(exclude={"producer_id"}).items():
        setattr(row, key, value)
    row.risk_score = score
    row.risk_level = level
    db.commit()
    db.refresh(row)
    return household_to_dict(row)


@router.post("/households/{household_id}/finalize")
def finalize_household_profile(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteHouseholdProfile, household_id, current_user, require_draft=True)
    _finalize(row, current_user)
    db.commit()
    db.refresh(row)
    return household_to_dict(row)


@router.delete("/households/{household_id}")
def delete_household_profile(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrteHouseholdProfile, household_id, current_user, require_draft=True)
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": household_id}


# ----- Fiche C : visite de plantation -----------------------------------------
@router.put("/plantation-visits/{visit_id}")
def update_plantation_visit(
    visit_id: int,
    data: PlantationVisitPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrtePlantationVisit, visit_id, current_user, require_draft=True)
    for key, value in data.model_dump(exclude={"producer_id", "plantation_id"}).items():
        setattr(row, key, value)
    db.flush()
    _alert_for_ssrte_visit(db, row)            # idempotent
    _traceability_block_for_ssrte_visit(db, row)  # idempotent (bloque si suspicion ajoutee)
    db.commit()
    db.refresh(row)
    return visit_to_dict(row)


@router.post("/plantation-visits/{visit_id}/finalize")
def finalize_plantation_visit(
    visit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrtePlantationVisit, visit_id, current_user, require_draft=True)
    _finalize(row, current_user)
    db.flush()
    _alert_for_ssrte_visit(db, row)
    _traceability_block_for_ssrte_visit(db, row)
    db.commit()
    db.refresh(row)
    return visit_to_dict(row)


@router.delete("/plantation-visits/{visit_id}")
def delete_plantation_visit(
    visit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_ssrte_write(current_user)
    row = _load_ssrte_writable(db, SsrtePlantationVisit, visit_id, current_user, require_draft=True)
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": visit_id}
