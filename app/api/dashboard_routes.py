"""
Tableau de bord direction — vue executive agregee, en LECTURE SEULE.

Consolide les indicateurs strategiques deja produits par les modules existants
(EUDR, travail des enfants / SSRTE, revenu vital FarmForce, volumes & certification)
en une seule reponse, cloisonnee par cooperative de l'utilisateur connecte.

Aucune ecriture, aucune migration : ce module ne fait qu'agreger l'existant.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import (
    FarmForceAssessment,
    Harvest,
    Plantation,
    PlantationCertification,
    Producer,
    User,
)
from app.db.models_social import (
    Alert,
    AlertStatus,
    BlockStatus,
    Child,
    RiskLevel,
    SchoolStatus,
    SsrtePlantationVisit,
    TraceabilityBlock,
)
from app.eudr.scoring import compute_eudr_score
from app.eudr.score_cache import ensure_scores
from app.services.farmforce_reports import living_income_assessment

router = APIRouter(prefix="/dashboard", tags=["Tableau de bord direction"])


@router.get("/direction")
def direction_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """KPIs strategiques pour la direction de la cooperative (lecture seule)."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Tableau de bord direction reserve a la direction.")

    coop_id = current_user.cooperative_id

    def scope_producers(q):
        return q.filter(Producer.cooperative_id == coop_id) if coop_id is not None else q

    def scope_plantations(q):
        return q.filter(Plantation.cooperative_id == coop_id) if coop_id is not None else q

    # ── Periметre ────────────────────────────────────────────────────────────
    producers_active = scope_producers(
        db.query(func.count(Producer.id)).filter(Producer.is_active == True)
    ).scalar() or 0
    plantations = scope_plantations(db.query(Plantation)).all()
    total_plantations = len(plantations)
    total_hectares = round(sum(float(p.hectares or 0) for p in plantations), 2)

    # ── EUDR : conformite parcellaire ─────────────────────────────────────────
    eudr_counts = {"conforme": 0, "a_verifier": 0, "non_conforme": 0}
    with_polygon = 0
    total_score = 0
    total_max = 0
    ensure_scores(plantations, db)  # cache EUDR (P1) : 1 passe, puis lecture des colonnes
    for p in plantations:
        eudr_counts[p.eudr_status] = eudr_counts.get(p.eudr_status, 0) + 1
        if p.eudr_has_polygon:
            with_polygon += 1
        total_score += p.eudr_score or 0
        total_max += p.eudr_max_score or 0
    eudr_compliance_rate = round(eudr_counts["conforme"] / total_plantations * 100, 1) if total_plantations else 0.0
    eudr_avg_score = round(total_score / total_max * 100, 1) if total_max else 0.0

    # ── Travail des enfants / SSRTE ───────────────────────────────────────────
    child_q = db.query(func.count(Child.id)).join(Producer, Child.producer_id == Producer.id).filter(Child.is_active == True)
    if coop_id is not None:
        child_q = child_q.filter(Producer.cooperative_id == coop_id)
    children_total = child_q.scalar() or 0

    def child_count(*filters):
        q = db.query(func.count(Child.id)).join(Producer, Child.producer_id == Producer.id).filter(Child.is_active == True, *filters)
        if coop_id is not None:
            q = q.filter(Producer.cooperative_id == coop_id)
        return q.scalar() or 0

    high_risk_children = child_count(Child.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
    enrolled_children = child_count(Child.school_status == SchoolStatus.ENROLLED)

    susp_q = db.query(func.count(SsrtePlantationVisit.id)).join(
        Producer, SsrtePlantationVisit.producer_id == Producer.id
    ).filter(SsrtePlantationVisit.suspected_child_labor == True)
    if coop_id is not None:
        susp_q = susp_q.filter(Producer.cooperative_id == coop_id)
    suspected_visits = susp_q.scalar() or 0

    block_q = db.query(func.count(TraceabilityBlock.id)).join(
        Producer, TraceabilityBlock.producer_id == Producer.id
    ).filter(TraceabilityBlock.status == BlockStatus.ACTIVE)
    if coop_id is not None:
        block_q = block_q.filter(Producer.cooperative_id == coop_id)
    active_blocks = block_q.scalar() or 0

    # ── Revenu vital (FarmForce) ──────────────────────────────────────────────
    ff_q = db.query(FarmForceAssessment).join(Producer, FarmForceAssessment.producer_id == Producer.id)
    if coop_id is not None:
        ff_q = ff_q.filter(Producer.cooperative_id == coop_id)
    assessments = ff_q.all()
    ff_total = len(assessments)
    reached = 0
    net_sum = 0.0
    for a in assessments:
        net = float(a.net_income_cfa or 0)
        net_sum += net
        if living_income_assessment(net).get("living_income_status") == "atteint":
            reached += 1
    living_income_reached_rate = round(reached / ff_total * 100, 1) if ff_total else 0.0
    avg_net_income = round(net_sum / ff_total, 0) if ff_total else 0.0

    # ── Volumes & certification ───────────────────────────────────────────────
    plant_ids = [p.id for p in plantations]
    if plant_ids:
        vol_total = db.query(func.coalesce(func.sum(Harvest.quantity_kg), 0)).filter(
            Harvest.plantation_id.in_(plant_ids)
        ).scalar() or 0
        # Parcelles portant au moins une certification (FT, RA, …).
        certified_plant_ids = [
            row[0] for row in db.query(PlantationCertification.plantation_id)
            .filter(PlantationCertification.plantation_id.in_(plant_ids))
            .distinct().all()
        ]
        # Volume certifié = récoltes sous certification commerciale OU issues d'une parcelle certifiée.
        vol_certified = db.query(func.coalesce(func.sum(Harvest.quantity_kg), 0)).filter(
            Harvest.plantation_id.in_(plant_ids),
            (Harvest.certification_id.isnot(None)) | (Harvest.plantation_id.in_(certified_plant_ids or [-1])),
        ).scalar() or 0
    else:
        vol_total = 0
        vol_certified = 0
    vol_total = float(vol_total or 0)
    vol_certified = float(vol_certified or 0)
    certified_rate = round(vol_certified / vol_total * 100, 1) if vol_total else 0.0

    # ── Alertes ouvertes (globales : Alert est polymorphe, sans producer_id) ──
    open_alerts = db.query(func.count(Alert.id)).filter(Alert.status != AlertStatus.RESOLVED).scalar() or 0

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "cooperative_id": coop_id,
        "scope": "cooperative" if coop_id is not None else "global",
        "perimeter": {
            "producers_active": producers_active,
            "plantations": total_plantations,
            "total_hectares": total_hectares,
        },
        "eudr": {
            "conforme": eudr_counts["conforme"],
            "a_verifier": eudr_counts["a_verifier"],
            "non_conforme": eudr_counts["non_conforme"],
            "with_polygon": with_polygon,
            "without_polygon": total_plantations - with_polygon,
            "compliance_rate_pct": eudr_compliance_rate,
            "average_score_pct": eudr_avg_score,
        },
        "child_protection": {
            "children_total": children_total,
            "high_risk_children": high_risk_children,
            "school_enrollment_rate_pct": round(enrolled_children / children_total * 100, 1) if children_total else 0.0,
            "suspected_child_labor_visits": suspected_visits,
            "active_traceability_blocks": active_blocks,
        },
        "living_income": {
            "assessments": ff_total,
            "reached": reached,
            "reached_rate_pct": living_income_reached_rate,
            "average_net_income_cfa": avg_net_income,
        },
        "volume": {
            "total_kg": round(vol_total, 1),
            "certified_kg": round(vol_certified, 1),
            "certified_rate_pct": certified_rate,
        },
        "alerts": {
            "open": open_alerts,
        },
    }
