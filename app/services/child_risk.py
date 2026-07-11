"""
Jumeau numérique — Palier 2 (prédictif LÉGER & EXPLICABLE).

Indicateur PRÉCOCE de risque de travail d'enfant au niveau du MÉNAGE (producteur),
destiné à PRIORISER les enquêtes de terrain — jamais à rendre un verdict automatique.

Principe (comme le scoring EUDR et le jumeau de parcelle) : on combine des signaux
DÉJÀ collectés (enfants recensés, scolarisation, travail déclaré, tâches dangereuses,
écart au revenu vital, signalements) via des poids TRANSPARENTS. Chaque facteur qui
contribue est renvoyé avec son libellé → l'agronome voit POURQUOI un ménage est
signalé. Aucune boîte noire, aucune donnée personnelle d'enfant exposée hors périmètre.

⚠️ AIDE À LA DÉCISION : le score déclenche une VISITE / ENQUÊTE humaine, il ne
constitue ni une preuve, ni une sanction, ni un blocage.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

# Âge scolaire retenu (Côte d'Ivoire : scolarisation obligatoire 6–16 ans).
SCHOOL_AGE_MIN = 6
SCHOOL_AGE_MAX = 16
ASSESSMENT_FRESH_DAYS = 365   # évaluation considérée récente < 12 mois

# Poids EXPLICABLES (points). Sommés puis plafonnés à 100. Ajustables ici seulement.
W = {
    "dangerous_task":       40,   # tâche dangereuse déclarée sur un enfant (signal fort)
    "working_regular":      30,   # enfant travaillant régulièrement/quotidiennement
    "working_occasional":   15,   # enfant travaillant occasionnellement
    "out_of_school":        20,   # enfant en âge scolaire déscolarisé
    "low_attendance":       10,   # fréquentation scolaire faible (<50 %)
    "living_income_gap":    15,   # ménage sous le seuil de revenu vital (pauvreté = facteur)
    "child_complaint":      25,   # signalement travail d'enfant lié au producteur (non classé infondé)
}

LEVEL_HIGH = 55
LEVEL_MEDIUM = 25

DISCLAIMER = (
    "Indicateur d'aide à la décision : il PRIORISE les ménages à visiter/enquêter, "
    "il ne constitue ni preuve, ni sanction, ni blocage. La confirmation passe par "
    "une enquête de terrain (visite de monitoring / fiche SSRTE)."
)


def child_age(dob) -> Optional[int]:
    if not dob:
        return None
    d = dob.date() if hasattr(dob, "date") else dob
    try:
        today = date.today()
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except Exception:
        return None


def _level(score: int) -> str:
    if score >= LEVEL_HIGH:
        return "eleve"
    if score >= LEVEL_MEDIUM:
        return "moyen"
    return "faible"


def _evaluate(sig: dict) -> dict:
    """Cœur de scoring, à partir de signaux déjà agrégés. Renvoie score + facteurs.

    `sig` attend : dangerous_children, working_regular_children,
    working_occasional_children, out_of_school_children, low_attendance_children (int),
    living_income_gap (bool), living_income_pct (float|None), child_complaints (int),
    has_children, recent_assessment, has_living_income (bool), already_followed (bool).
    """
    factors: list[dict] = []
    score = 0

    def add(code, severity, weight, label, detail=None):
        nonlocal score
        score += weight
        factors.append({"code": code, "severity": severity, "weight": weight,
                        "label": label, "detail": detail})

    n = sig.get("dangerous_children", 0)
    if n:
        add("dangerous_task", "high", W["dangerous_task"],
            "Tâche dangereuse déclarée sur un enfant", f"{n} enfant(s) concerné(s)")

    nr = sig.get("working_regular_children", 0)
    if nr:
        add("working_regular", "high", W["working_regular"],
            "Enfant travaillant régulièrement", f"{nr} enfant(s)")
    else:
        no = sig.get("working_occasional_children", 0)
        if no:
            add("working_occasional", "medium", W["working_occasional"],
                "Enfant travaillant occasionnellement", f"{no} enfant(s)")

    nos = sig.get("out_of_school_children", 0)
    if nos:
        add("out_of_school", "high", W["out_of_school"],
            "Enfant en âge scolaire déscolarisé", f"{nos} enfant(s)")

    nla = sig.get("low_attendance_children", 0)
    if nla:
        add("low_attendance", "medium", W["low_attendance"],
            "Fréquentation scolaire faible (<50 %)", f"{nla} enfant(s)")

    if sig.get("living_income_gap"):
        pct = sig.get("living_income_pct")
        detail = f"{pct:.0f}% du seuil" if isinstance(pct, (int, float)) else None
        add("living_income_gap", "medium", W["living_income_gap"],
            "Ménage sous le seuil de revenu vital", detail)

    nc = sig.get("child_complaints", 0)
    if nc:
        add("child_complaint", "high", W["child_complaint"],
            "Signalement lié au travail d'enfant", f"{nc} signalement(s) ouvert(s)")

    score = min(100, score)
    level = _level(score)

    # Complétude des données (pilote la FIABILITÉ du score et la recommandation).
    present = sum(1 for k in ("has_children", "recent_assessment", "has_living_income") if sig.get(k))
    data_completeness = round(present / 3, 2)

    already = bool(sig.get("already_followed"))
    if already:
        reco = "Cas déjà suivi — poursuivre le plan de remédiation jusqu'à clôture."
    elif level == "eleve":
        reco = "Priorité : planifier une visite de monitoring / enquête SSRTE du ménage."
    elif level == "moyen":
        reco = "À surveiller : intégrer à la prochaine tournée de monitoring."
    elif data_completeness < 0.5:
        reco = "Données incomplètes — réaliser un premier recensement/évaluation du ménage."
    else:
        reco = "Aucune priorité d'enquête particulière."

    factors.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["severity"], 3))
    return {
        "score": score,
        "level": level,
        "factors": factors,
        "data_completeness": data_completeness,
        "already_followed": already,
        "recommendation": reco,
        "disclaimer": DISCLAIMER,
    }


# ── Agrégation des signaux d'un producteur ────────────────────────────────────

def _child_signals(children) -> dict:
    """Compte les signaux enfant à partir d'une liste d'objets Child ACTIFS."""
    dangerous = reg = occ = oos = low_att = 0
    recent = False
    today = date.today()
    for c in children:
        tasks = c.dangerous_tasks_performed or []
        if isinstance(tasks, list) and len(tasks) > 0:
            dangerous += 1
        wf = getattr(c.work_frequency, "value", c.work_frequency)
        if c.is_working_on_farm and wf in ("regular", "daily"):
            reg += 1
        elif c.is_working_on_farm and wf == "occasional":
            occ += 1
        age = child_age(c.date_of_birth)
        ss = getattr(c.school_status, "value", c.school_status)
        if age is not None and SCHOOL_AGE_MIN <= age <= SCHOOL_AGE_MAX and ss in ("dropped_out", "never_enrolled"):
            oos += 1
        try:
            if c.school_attendance_rate is not None and float(c.school_attendance_rate) < 50:
                low_att += 1
        except (TypeError, ValueError):
            pass
        if c.last_assessment_date and (today - c.last_assessment_date).days <= ASSESSMENT_FRESH_DAYS:
            recent = True
    return {
        "dangerous_children": dangerous,
        "working_regular_children": reg,
        "working_occasional_children": occ,
        "out_of_school_children": oos,
        "low_attendance_children": low_att,
        "has_children": len(children) > 0,
        "recent_assessment": recent,
    }


def assess_producer_child_risk(db: Session, producer) -> dict:
    """Évaluation d'un producteur (vue fiche). Requêtes ciblées, best-effort."""
    from app.db.models_social import (
        Child, Complaint, ComplaintStatus, ComplaintType,
    )

    children = (
        db.query(Child)
        .filter(Child.producer_id == producer.id, Child.is_active.is_(True))
        .all()
    )
    sig = _child_signals(children)

    # Revenu vital (écart) — réutilise le verdict FarmForce.
    li_gap, li_pct, has_li = False, None, False
    try:
        from app.db.models import FarmForceAssessment
        from app.services.farmforce_reports import living_income_assessment
        ff = (
            db.query(FarmForceAssessment.net_income_cfa)
            .filter(FarmForceAssessment.producer_id == producer.id)
            .order_by(FarmForceAssessment.created_at.desc())
            .first()
        )
        if ff and ff[0] is not None:
            has_li = True
            li = living_income_assessment(ff[0])
            li_gap = li.get("living_income_status") == "ecart"
            li_pct = li.get("living_income_pct")
    except Exception:
        pass
    sig.update(living_income_gap=li_gap, living_income_pct=li_pct, has_living_income=has_li)

    # Signalements travail d'enfant ouverts (non classés infondés/clos).
    child_types = [ComplaintType.CHILD_LABOR, ComplaintType.EXPLOITATION,
                   ComplaintType.TRAFFICKING, ComplaintType.ABUSE]
    closed = [ComplaintStatus.UNSUBSTANTIATED, ComplaintStatus.CLOSED]
    sig["child_complaints"] = (
        db.query(func.count(Complaint.id))
        .filter(Complaint.producer_id == producer.id,
                Complaint.complaint_type.in_(child_types),
                ~Complaint.status.in_(closed))
        .scalar() or 0
    )

    # Déjà suivi ? (remédiation active ou blocage)
    sig["already_followed"] = _already_followed(db, producer.id)

    result = _evaluate(sig)
    result.update(producer_id=producer.id,
                  producer_name=getattr(producer, "nom_complet", None),
                  children_count=len(children))
    return result


def _already_followed(db: Session, producer_id: int) -> bool:
    from app.db.models_social import (
        BlockStatus, RemediationPlan, RemediationStatus, TraceabilityBlock,
    )
    active = ("pending_approval", "approved", "in_progress", "escalated")
    rem = (
        db.query(RemediationPlan.id)
        .filter(RemediationPlan.producer_id == producer_id,
                RemediationPlan.status.in_([RemediationStatus(s) for s in active]))
        .first()
    )
    if rem:
        return True
    blk = (
        db.query(TraceabilityBlock.id)
        .filter(TraceabilityBlock.producer_id == producer_id,
                TraceabilityBlock.status == BlockStatus.ACTIVE)
        .first()
    )
    return blk is not None


# ── Vue coopérative : ménages à enquêter en priorité (batché) ─────────────────

def build_coop_child_risk(
    db: Session,
    coop_id: Optional[int],
    *,
    limit: int = 50,
    offset: int = 0,
    level: Optional[str] = None,
) -> dict:
    """Classement des ménages par priorité d'enquête. FAIL-CLOSED sans coopérative."""
    empty = {
        "total_producers": 0, "flagged_count": 0,
        "by_level": {"eleve": 0, "moyen": 0, "faible": 0},
        "limit": limit, "offset": offset, "returned": 0, "households": [],
        "disclaimer": DISCLAIMER,
    }
    if coop_id is None:
        return empty

    from app.db.models import Producer
    from app.db.models_social import (
        BlockStatus, Child, Complaint, ComplaintStatus, ComplaintType,
        RemediationPlan, RemediationStatus, TraceabilityBlock,
    )

    producers = db.query(Producer).filter(Producer.cooperative_id == coop_id).all()
    if not producers:
        return empty
    prod_ids = [p.id for p in producers]

    # Enfants actifs groupés par producteur (une requête).
    children_by_prod: dict = {}
    for c in db.query(Child).filter(Child.producer_id.in_(prod_ids), Child.is_active.is_(True)).all():
        children_by_prod.setdefault(c.producer_id, []).append(c)

    # Revenu vital le plus récent par producteur.
    ff_net: dict = {}
    try:
        from app.db.models import FarmForceAssessment
        for r in (
            db.query(FarmForceAssessment.producer_id, FarmForceAssessment.net_income_cfa,
                     FarmForceAssessment.created_at)
            .filter(FarmForceAssessment.producer_id.in_(prod_ids))
            .order_by(FarmForceAssessment.producer_id, FarmForceAssessment.created_at.desc())
            .all()
        ):
            ff_net.setdefault(r.producer_id, r.net_income_cfa)
    except Exception:
        ff_net = {}

    # Signalements travail d'enfant ouverts, comptés par producteur.
    child_types = [ComplaintType.CHILD_LABOR, ComplaintType.EXPLOITATION,
                   ComplaintType.TRAFFICKING, ComplaintType.ABUSE]
    closed = [ComplaintStatus.UNSUBSTANTIATED, ComplaintStatus.CLOSED]
    complaint_count: dict = {}
    for pr_id, cnt in (
        db.query(Complaint.producer_id, func.count(Complaint.id))
        .filter(Complaint.producer_id.in_(prod_ids),
                Complaint.complaint_type.in_(child_types),
                ~Complaint.status.in_(closed))
        .group_by(Complaint.producer_id).all()
    ):
        complaint_count[pr_id] = int(cnt)

    # Déjà suivi : remédiation active OU blocage actif.
    followed: set = set()
    active = ("pending_approval", "approved", "in_progress", "escalated")
    for (pr_id,) in (
        db.query(RemediationPlan.producer_id)
        .filter(RemediationPlan.producer_id.in_(prod_ids),
                RemediationPlan.status.in_([RemediationStatus(s) for s in active])).all()
    ):
        followed.add(pr_id)
    for (pr_id,) in (
        db.query(TraceabilityBlock.producer_id)
        .filter(TraceabilityBlock.producer_id.in_(prod_ids),
                TraceabilityBlock.status == BlockStatus.ACTIVE).all()
    ):
        followed.add(pr_id)

    from app.services.farmforce_reports import living_income_assessment

    flagged: list = []
    by_level = {"eleve": 0, "moyen": 0, "faible": 0}
    for p in producers:
        kids = children_by_prod.get(p.id, [])
        sig = _child_signals(kids)
        net = ff_net.get(p.id)
        if net is not None:
            li = living_income_assessment(net)
            sig.update(living_income_gap=li.get("living_income_status") == "ecart",
                       living_income_pct=li.get("living_income_pct"), has_living_income=True)
        else:
            sig.update(living_income_gap=False, living_income_pct=None, has_living_income=False)
        sig["child_complaints"] = complaint_count.get(p.id, 0)
        sig["already_followed"] = p.id in followed

        ev = _evaluate(sig)
        by_level[ev["level"]] += 1
        if ev["level"] == "faible":
            continue   # on ne liste que les ménages à surveiller/prioriser
        flagged.append({
            "producer_id": p.id, "producer_name": p.nom_complet,
            "children_count": len(kids),
            "score": ev["score"], "level": ev["level"],
            "already_followed": ev["already_followed"],
            "data_completeness": ev["data_completeness"],
            "recommendation": ev["recommendation"],
            "factors": ev["factors"],
        })

    flagged_count = len(flagged)
    if level in ("eleve", "moyen", "faible"):
        flagged = [r for r in flagged if r["level"] == level]
    order = {"eleve": 0, "moyen": 1, "faible": 2}
    flagged.sort(key=lambda r: (order.get(r["level"], 3), -r["score"]))
    page = flagged[offset: offset + limit]
    return {
        "total_producers": len(producers),
        "flagged_count": flagged_count,
        "by_level": by_level,
        "limit": limit, "offset": offset, "returned": len(page),
        "households": page,
        "disclaimer": DISCLAIMER,
    }
