"""Routes Producteurs + drill-down CacaoGuard.

Etend les routes producer historiques (list/get) avec les endpoints
"drill-down" attendus par la roadmap (section 5.1) : depuis un producteur,
acceder a ses enfants, evaluations, visites, plans, plaintes, statut
tracabilite et score de risque agrege.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cacaoguard_ops_routes import (
    get_optional_current_user,
    plan_to_dict,
    record_privacy_access,
    require_role,
    visit_to_dict,
)
from app.db.database import get_db
from app.db.models import Producer, User
from app.db.models_social import (
    BlockStatus,
    Child,
    Complaint,
    MonitoringVisit,
    RemediationPlan,
    RiskAssessment,
    RiskLevel,
    TraceabilityBlock,
)

router = APIRouter(tags=["Producteurs"])


def _can_view_sensitive(user: User | None) -> bool:
    return user is None or user.role in {"admin", "agronomist"}


class ProducerResponse(BaseModel):
    id: int
    nom_complet: str
    code_yeyasso: Optional[str] = None
    telephone: Optional[str] = None
    localite: Optional[str] = None
    section: Optional[str] = None
    cooperative_id: Optional[int] = None

    class Config:
        from_attributes = True


class ProducerCreate(BaseModel):
    nom_complet: str = Field(..., min_length=2, max_length=200)
    code_yeyasso: Optional[str] = Field(None, max_length=100)
    telephone: Optional[str] = Field(None, max_length=50)
    localite: Optional[str] = Field(None, max_length=120)
    section: Optional[str] = Field(None, max_length=120)
    sexe: Optional[str] = Field(None, pattern="^[HF]$")


def _filtered_producers_query(db, current_user, search=None, localite=None,
                              section=None, certification=None):
    """Construit la requête producteurs filtrée (sans tri ni pagination).

    Partagée par la liste paginée ET le comptage, pour que le total du pager
    corresponde exactement aux lignes affichées (mêmes filtres, même scope coop).
    """
    query = db.query(Producer).filter(Producer.is_active == True)

    # Cloisonnement multi-tenant : un utilisateur ne voit que sa cooperative.
    if current_user is not None and current_user.cooperative_id is not None:
        query = query.filter(Producer.cooperative_id == current_user.cooperative_id)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            (Producer.nom_complet.ilike(like))
            | (Producer.code_yeyasso.ilike(like))
            | (Producer.telephone.ilike(like))
        )
    if localite:
        query = query.filter(Producer.localite == localite)
    if section:
        query = query.filter(Producer.section == section)
    if certification and certification.strip():
        # Un producteur est "certifié X" si une de ses plantations porte le label X.
        from app.db.models import Certification, Plantation, PlantationCertification
        cert = db.query(Certification).filter(
            Certification.code == certification.strip().upper()
        ).first()
        if cert:
            prod_ids = [
                row[0] for row in db.query(Plantation.producer_id)
                .join(PlantationCertification, PlantationCertification.plantation_id == Plantation.id)
                .filter(
                    PlantationCertification.certification_id == cert.id,
                    Plantation.producer_id.isnot(None),
                )
                .distinct().all()
            ]
            query = query.filter(Producer.id.in_(prod_ids or [-1]))
        else:
            query = query.filter(Producer.id.in_([-1]))
    return query


@router.get("/producers/count")
def count_producers(
    search: Optional[str] = None,
    localite: Optional[str] = None,
    section: Optional[str] = None,
    certification: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Total des producteurs correspondant aux filtres — pour la pagination (P2 scale).

    Défini AVANT /producers/{...} éventuels : « count » ne doit pas être pris pour un id.
    """
    q = _filtered_producers_query(db, current_user, search, localite, section, certification)
    return {"total": q.count()}


@router.get("/producers", response_model=List[ProducerResponse])
def list_producers(
    limit: int = Query(500, ge=1, le=5000),
    skip: int = Query(0, ge=0),
    search: Optional[str] = None,
    localite: Optional[str] = None,
    section: Optional[str] = None,
    certification: Optional[str] = Query(None, description="Filtre : producteurs ayant une plantation certifiée (code)"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    query = _filtered_producers_query(db, current_user, search, localite, section, certification)
    return query.order_by(Producer.nom_complet.asc()).offset(skip).limit(limit).all()


@router.post("/producers", response_model=ProducerResponse, status_code=201)
def create_producer(
    data: ProducerCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Crée un producteur directement (sans passer par une parcelle).

    Utile pour enregistrer un membre avant de cartographier ses parcelles. Les
    producteurs restent aussi auto-créés depuis le propriétaire d'une parcelle
    et par l'import de registre.
    """
    require_role(current_user, {"admin", "agronomist", "technician", "gestionnaire"})
    coop_id = current_user.cooperative_id if current_user else None
    code = (data.code_yeyasso or "").strip() or None
    if code:
        dup = db.query(Producer).filter(
            Producer.code_yeyasso == code, Producer.is_active == True
        )
        if coop_id is not None:
            dup = dup.filter(Producer.cooperative_id == coop_id)
        if dup.first():
            raise HTTPException(status_code=409, detail=f"Un producteur avec le code « {code} » existe déjà.")
    producer = Producer(
        nom_complet=data.nom_complet.strip(),
        code_yeyasso=code,
        telephone=(data.telephone or "").strip() or None,
        localite=(data.localite or "").strip() or None,
        section=(data.section or "").strip() or None,
        sexe=data.sexe or None,
        cooperative_id=coop_id,
        is_active=True,
    )
    db.add(producer)
    db.commit()
    db.refresh(producer)
    return producer


@router.get("/producers/{producer_id:int}", response_model=ProducerResponse)
def get_producer(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician", "viewer", "gestionnaire"})
    producer = db.query(Producer).filter(
        Producer.id == producer_id,
        Producer.is_active == True,
    ).first()
    # Cloisonnement : producteur d'une autre coopérative invisible.
    if (producer and current_user is not None and current_user.cooperative_id is not None
            and producer.cooperative_id != current_user.cooperative_id):
        producer = None
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    return producer


# ----------------------------------------------------------------------------
# Drill-down CacaoGuard
# ----------------------------------------------------------------------------

def _get_producer_or_404(db: Session, producer_id: int, current_user: User | None = None) -> Producer:
    producer = db.query(Producer).filter(Producer.id == producer_id).first()
    # Cloisonnement : un producteur d'une autre coopérative est invisible (404).
    if (producer and current_user is not None and current_user.cooperative_id is not None
            and producer.cooperative_id != current_user.cooperative_id):
        producer = None
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    return producer


def _child_summary(child: Child, *, redact: bool) -> dict:
    if redact:
        first_initial = child.first_name[:1].upper() if child.first_name else "?"
        first_name = first_initial
        last_name = "Confidentiel"
    else:
        first_name = child.first_name
        last_name = child.last_name
    return {
        "id": child.id,
        "first_name": first_name,
        "last_name": last_name,
        "gender": child.gender,
        "school_status": child.school_status.value if child.school_status else None,
        "is_working_on_farm": child.is_working_on_farm,
        "work_frequency": child.work_frequency.value if child.work_frequency else None,
        "risk_score": float(child.risk_score or 0),
        "risk_level": child.risk_level.value if child.risk_level else None,
        "last_assessment_date": child.last_assessment_date,
        "is_active": child.is_active,
        "privacy_redacted": redact,
    }


@router.get("/producers/{producer_id:int}/children")
def list_producer_children(
    producer_id: int,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician", "viewer", "gestionnaire"})
    producer = _get_producer_or_404(db, producer_id, current_user)
    query = db.query(Child).filter(Child.producer_id == producer_id)
    if not include_inactive:
        query = query.filter(Child.is_active == True)

    redact = not _can_view_sensitive(current_user)
    children = query.order_by(Child.created_at.desc()).all()
    record_privacy_access(
        db,
        current_user,
        action="list_producer_children",
        source_entity="children",
        source_id=producer_id,
        redacted=redact,
        metadata={"producer_id": producer_id, "count": len(children)},
    )
    db.commit()
    return [_child_summary(c, redact=redact) for c in children]


@router.get("/producers/{producer_id:int}/assessments")
def list_producer_assessments(
    producer_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    _get_producer_or_404(db, producer_id, current_user)
    require_role(current_user, {"admin", "agronomist", "technician", "gestionnaire"})

    items = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.producer_id == producer_id)
        .order_by(RiskAssessment.assessment_date.desc(), RiskAssessment.id.desc())
        .limit(limit)
        .all()
    )
    record_privacy_access(
        db,
        current_user,
        action="list_producer_assessments",
        source_entity="risk_assessments",
        source_id=producer_id,
        metadata={"producer_id": producer_id, "count": len(items)},
    )
    db.commit()
    return [
        {
            "id": a.id,
            "child_id": a.child_id,
            "assessment_type": a.assessment_type.value if a.assessment_type else None,
            "assessment_date": a.assessment_date,
            "overall_risk_score": float(a.overall_risk_score or 0),
            "overall_risk_level": a.overall_risk_level.value if a.overall_risk_level else None,
            "status": a.status.value if a.status else None,
            "methodology_version": a.methodology_version,
        }
        for a in items
    ]


@router.get("/producers/{producer_id:int}/visits")
def list_producer_visits(
    producer_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician", "viewer", "gestionnaire"})
    _get_producer_or_404(db, producer_id, current_user)
    visits = (
        db.query(MonitoringVisit)
        .filter(MonitoringVisit.producer_id == producer_id)
        .order_by(MonitoringVisit.scheduled_date.desc())
        .limit(limit)
        .all()
    )
    include_sensitive = _can_view_sensitive(current_user)
    record_privacy_access(
        db,
        current_user,
        action="list_producer_visits",
        source_entity="monitoring_visits",
        source_id=producer_id,
        redacted=not include_sensitive,
        metadata={"producer_id": producer_id, "count": len(visits)},
    )
    db.commit()
    return [visit_to_dict(v, include_sensitive=include_sensitive) for v in visits]


@router.get("/producers/{producer_id:int}/remediation-plans")
def list_producer_remediation_plans(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    _get_producer_or_404(db, producer_id, current_user)
    require_role(current_user, {"admin", "agronomist"})

    plans = (
        db.query(RemediationPlan)
        .filter(RemediationPlan.producer_id == producer_id)
        .order_by(RemediationPlan.created_at.desc())
        .all()
    )
    record_privacy_access(
        db,
        current_user,
        action="list_producer_remediation_plans",
        source_entity="remediation_plans",
        source_id=producer_id,
        metadata={"producer_id": producer_id, "count": len(plans)},
    )
    db.commit()
    return [plan_to_dict(p) for p in plans]


@router.get("/producers/{producer_id:int}/complaints")
def list_producer_complaints(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    _get_producer_or_404(db, producer_id, current_user)
    require_role(current_user, {"admin", "agronomist"})

    items = (
        db.query(Complaint)
        .filter(Complaint.producer_id == producer_id)
        .order_by(Complaint.received_date.desc())
        .all()
    )
    record_privacy_access(
        db,
        current_user,
        action="list_producer_complaints",
        source_entity="complaints",
        source_id=producer_id,
        metadata={"producer_id": producer_id, "count": len(items)},
    )
    db.commit()
    return [
        {
            "id": c.id,
            "reference": c.complaint_reference,
            "complaint_type": c.complaint_type.value if c.complaint_type else None,
            "severity": c.severity.value if c.severity else None,
            "status": c.status.value if c.status else None,
            "received_date": c.received_date,
            "investigation_end_date": c.investigation_end_date,
        }
        for c in items
    ]


@router.get("/producers/{producer_id:int}/traceability-status")
def get_producer_traceability_status(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Etat actuel de tracabilite pour un producteur.

    Retourne {is_blocked, active_blocks, resolved_blocks_count, last_resolution}.
    Utile pour la pipeline export (passe/bloque avant expedition).
    """
    require_role(current_user, {"admin", "agronomist", "technician", "viewer", "gestionnaire"})
    _get_producer_or_404(db, producer_id, current_user)

    active = (
        db.query(TraceabilityBlock)
        .filter(
            TraceabilityBlock.producer_id == producer_id,
            TraceabilityBlock.status == BlockStatus.ACTIVE,
        )
        .all()
    )
    resolved_count = (
        db.query(TraceabilityBlock)
        .filter(
            TraceabilityBlock.producer_id == producer_id,
            TraceabilityBlock.status == BlockStatus.RESOLVED,
        )
        .count()
    )
    last_resolution = (
        db.query(TraceabilityBlock)
        .filter(
            TraceabilityBlock.producer_id == producer_id,
            TraceabilityBlock.status == BlockStatus.RESOLVED,
        )
        .order_by(TraceabilityBlock.actual_resolution_date.desc().nullslast())
        .first()
    )

    return {
        "producer_id": producer_id,
        "is_blocked": len(active) > 0,
        "active_blocks_count": len(active),
        "active_blocks": [
            {
                "id": b.id,
                "reason": b.block_reason.value if b.block_reason else None,
                "description": b.block_description,
                "block_start_date": b.block_start_date,
                "expected_resolution_date": b.expected_resolution_date,
                "related_case_id": b.related_case_id,
            }
            for b in active
        ],
        "resolved_blocks_count": resolved_count,
        "last_resolution": {
            "id": last_resolution.id,
            "actual_resolution_date": last_resolution.actual_resolution_date,
            "resolution_notes": last_resolution.resolution_notes,
        } if last_resolution else None,
    }


_RISK_LEVEL_ORDER = [
    RiskLevel.NONE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL,
]


def _max_risk_level(levels: List[RiskLevel]) -> RiskLevel:
    if not levels:
        return RiskLevel.NONE
    indexed = [(_RISK_LEVEL_ORDER.index(l), l) for l in levels if l in _RISK_LEVEL_ORDER]
    if not indexed:
        return RiskLevel.NONE
    return max(indexed)[1]


@router.post("/producers/{producer_id:int}/calculate-risk")
def calculate_producer_risk(
    producer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Score de risque agrege au niveau producteur.

    Agrege le risque des enfants actifs + presence de blocs actifs + plaintes
    ouvertes. Retourne un niveau de risque global (max des enfants) et des
    indicateurs cles pour la dashboard producteur.
    """
    require_role(current_user, {"admin", "agronomist", "technician", "gestionnaire"})
    producer = _get_producer_or_404(db, producer_id, current_user)

    children = db.query(Child).filter(
        Child.producer_id == producer_id,
        Child.is_active == True,
    ).all()
    scores = [float(c.risk_score or 0) for c in children]
    levels = [c.risk_level for c in children if c.risk_level]

    active_blocks = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id == producer_id,
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).count()
    open_complaints = db.query(Complaint).filter(
        Complaint.producer_id == producer_id,
        Complaint.status.in_(["received", "under_review", "investigating", "escalated"]),
    ).count()

    aggregate_level = _max_risk_level(levels)
    record_privacy_access(
        db,
        current_user,
        action="calculate_producer_risk",
        source_entity="producers",
        source_id=producer_id,
        metadata={"children_count": len(children), "blocks": active_blocks},
    )
    db.commit()

    return {
        "producer_id": producer_id,
        "producer_name": producer.nom_complet,
        "aggregate_risk_level": aggregate_level.value,
        "children_count": len(children),
        "children_risk_avg": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "children_risk_max": max(scores) if scores else 0.0,
        "children_at_high_or_critical": sum(
            1 for c in children if c.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        ),
        "active_traceability_blocks": active_blocks,
        "open_complaints": open_complaints,
        "requires_intervention": (
            aggregate_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
            or active_blocks > 0
            or open_complaints > 0
        ),
    }
