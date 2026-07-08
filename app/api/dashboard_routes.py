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
    Cooperative,
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
from app.services.social_scope import coop_alert_ids

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

    # Producteurs sous blocage ACTIF (ex. travail des enfants) : leur volume ne peut
    # pas etre affecte a un lot -> on distinguera plus bas le volume RETENU (bloque)
    # du volume simplement EN ATTENTE d'affectation.
    bp_q = db.query(TraceabilityBlock.producer_id).join(
        Producer, TraceabilityBlock.producer_id == Producer.id
    ).filter(TraceabilityBlock.status == BlockStatus.ACTIVE)
    if coop_id is not None:
        bp_q = bp_q.filter(Producer.cooperative_id == coop_id)
    blocked_producer_ids = {row[0] for row in bp_q.distinct().all()}

    # ── Revenu vital (FarmForce) ──────────────────────────────────────────────
    ff_q = db.query(FarmForceAssessment).join(Producer, FarmForceAssessment.producer_id == Producer.id)
    if coop_id is not None:
        ff_q = ff_q.filter(Producer.cooperative_id == coop_id)
    assessments = ff_q.all()
    ff_total = len(assessments)
    # Seuil de revenu vital PROPRE a la coop (editable admin) ; None => defaut serveur.
    coop_bench = None
    if coop_id is not None:
        _coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
        coop_bench = getattr(_coop, "living_income_benchmark_cfa", None) if _coop else None
    reached = 0
    net_sum = 0.0
    for a in assessments:
        net = float(a.net_income_cfa or 0)
        net_sum += net
        if living_income_assessment(net, coop_bench).get("living_income_status") == "atteint":
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
        # Volume non tracé = récoltes pas encore affectées à un lot physique (lot_id NULL).
        vol_untracked = db.query(func.coalesce(func.sum(Harvest.quantity_kg), 0)).filter(
            Harvest.plantation_id.in_(plant_ids),
            Harvest.lot_id.is_(None),
        ).scalar() or 0
        # Dont volume RETENU : récoltes hors lot d'un producteur sous blocage social
        # actif (ex. travail des enfants). Ce n'est pas « en attente » mais bloqué.
        blocked_plant_ids = [p.id for p in plantations if p.producer_id in blocked_producer_ids]
        if blocked_plant_ids:
            vol_blocked = db.query(func.coalesce(func.sum(Harvest.quantity_kg), 0)).filter(
                Harvest.plantation_id.in_(blocked_plant_ids),
                Harvest.lot_id.is_(None),
            ).scalar() or 0
        else:
            vol_blocked = 0
    else:
        vol_total = 0
        vol_certified = 0
        vol_untracked = 0
        vol_blocked = 0
    vol_total = float(vol_total or 0)
    vol_certified = float(vol_certified or 0)
    vol_untracked = float(vol_untracked or 0)
    vol_blocked = float(vol_blocked or 0)
    vol_pending = max(0.0, vol_untracked - vol_blocked)   # simplement en attente d'affectation
    certified_rate = round(vol_certified / vol_total * 100, 1) if vol_total else 0.0
    untracked_rate = round(vol_untracked / vol_total * 100, 1) if vol_total else 0.0

    # ── Alertes ouvertes — CLOISONNÉES par coopérative. Alert n'a pas de
    # cooperative_id : on résout le périmètre via coop_alert_ids (source_entity →
    # producteur → coop). Sans ce filtre, le compteur fuitait entre coopératives.
    alert_q = db.query(func.count(Alert.id)).filter(Alert.status != AlertStatus.RESOLVED)
    if coop_id is not None:
        allowed_alert_ids = coop_alert_ids(db, coop_id)
        alert_q = alert_q.filter(Alert.id.in_(allowed_alert_ids if allowed_alert_ids else [-1]))
    open_alerts = alert_q.scalar() or 0

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
            "untracked_kg": round(vol_untracked, 1),
            "untracked_rate_pct": untracked_rate,
            "blocked_kg": round(vol_blocked, 1),      # retenu : producteur sous blocage social actif
            "pending_kg": round(vol_pending, 1),      # simplement en attente d'affectation à un lot
        },
        "alerts": {
            "open": open_alerts,
        },
    }


@router.get("/direction/ai-summary")
def direction_ai_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Résumé exécutif rédigé par le moteur IA (fournisseur sélectionné) à partir des
    KPI de direction. Réutilise l'agrégat /dashboard/direction — pas de doublon de
    calcul. Réservé direction ; généré à la demande (coût borné)."""
    data = direction_dashboard(db, current_user)  # réutilise l'agrégat (et le garde-fou de rôle)
    p, e = data["perimeter"], data["eudr"]
    c, li, v = data["child_protection"], data["living_income"], data["volume"]
    facts = (
        f"- Périmètre : {p['producers_active']} producteurs actifs, {p['plantations']} parcelles, {p['total_hectares']} ha.\n"
        f"- EUDR : {e['compliance_rate_pct']}% conformes ({e['conforme']} conformes, {e['a_verifier']} à vérifier, "
        f"{e['non_conforme']} non conformes ; {e['without_polygon']} sans polygone).\n"
        f"- Protection enfant : {c['children_total']} enfants suivis, {c['high_risk_children']} à risque élevé/critique, "
        f"scolarisation {c['school_enrollment_rate_pct']}%, {c['active_traceability_blocks']} blocages traçabilité actifs.\n"
        f"- Revenu vital : {li['assessments']} évaluations, {li['reached_rate_pct']}% au seuil vital, "
        f"revenu net moyen {li['average_net_income_cfa']} FCFA.\n"
        f"- Volumes : {v['total_kg']} kg total, {v['certified_rate_pct']}% certifié.\n"
        f"- Alertes ouvertes : {data['alerts']['open']}."
    )
    prompt = (
        "Tu es analyste pour la DIRECTION d'une coopérative de cacao en Côte d'Ivoire. "
        "À partir UNIQUEMENT des indicateurs ci-dessous, rédige un résumé exécutif en français "
        "(4 à 6 phrases) : 1) la situation d'ensemble, 2) les 2-3 risques prioritaires, "
        "3) 2 recommandations actionnables et chiffrées. Sois concret, n'invente aucun chiffre.\n\n"
        f"INDICATEURS :\n{facts}"
    )
    try:
        from app.services import llm_client
        out = llm_client.chat(db, prompt, max_tokens=500, temperature=0.3)
    except llm_client.LLMNotConfigured as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        import httpx as _httpx
        if isinstance(ex, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(ex).__name__}.")
        raise
    # Suivi du coût (best-effort).
    try:
        from app.db.models import AiUsage
        from app.services.ai_cost import compute_cost_usd
        it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
        db.add(AiUsage(
            cooperative_id=current_user.cooperative_id, user_id=current_user.id,
            plantation_id=None, feature="direction_summary",
            model=out.get("model", ""), input_tokens=it_, output_tokens=ot_,
            cost_usd=compute_cost_usd(it_, ot_, out.get("model")),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return {"summary": (out.get("text") or "").strip(), "model": out.get("model"),
            "generated_at": data["generated_at"]}
