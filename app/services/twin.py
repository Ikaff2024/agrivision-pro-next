"""
Jumeau numérique de parcelle (FEATURE-PARCEL-360) — couche DESCRIPTIVE.

Agrège, pour une parcelle, tous les signaux DÉJÀ présents en base (diagnostic,
score EUDR, déforestation, agroforesterie, récoltes, blocage CacaoGuard,
délimitation) en une vue unifiée, puis en déduit des ALERTES par RÈGLES
déterministes — explicables comme le scoring EUDR. Aucune prédiction, aucune
fausse précision : c'est le socle fiable avant un éventuel modèle prédictif.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    DeforestationCheck,
    Diagnostic,
    Harvest,
    Plantation,
    PlantationBoundary,
    Producer,
)
from app.eudr.scoring import compute_eudr_score

# Pondération de sévérité pour classer les parcelles (vue coop « à risque »).
SEVERITY_WEIGHT = {"high": 4, "medium": 2, "low": 1}

# Seuils explicables
RECENT_DIAG_DAYS = 365      # diagnostic considéré récent < 12 mois
OLD_ORCHARD_YEARS = 25      # verger vieillissant
LOW_YIELD_KG_HA = 300.0     # rendement cacao faible (réf. ~400-600 kg/ha)


def _latest_diagnostic(db: Session, pid: int):
    return (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == pid)
        .order_by(Diagnostic.created_at.desc())
        .first()
    )


def _latest_deforestation(db: Session, pid: int):
    return (
        db.query(DeforestationCheck)
        .filter(DeforestationCheck.plantation_id == pid)
        .order_by(DeforestationCheck.check_date.desc().nullslast(), DeforestationCheck.id.desc())
        .first()
    )


def _active_block(db: Session, producer_id: Optional[int]):
    if not producer_id:
        return None
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
    except ImportError:
        return None
    return (
        db.query(TraceabilityBlock)
        .filter(TraceabilityBlock.producer_id == producer_id,
                TraceabilityBlock.status == BlockStatus.ACTIVE)
        .first()
    )


def _days_since(dt) -> Optional[int]:
    if not dt:
        return None
    d = dt.date() if hasattr(dt, "date") else dt
    try:
        return (date.today() - d).days
    except Exception:
        return None


def build_twin(db: Session, plantation: Plantation) -> dict:
    """Vue unifiée (jumeau) d'une parcelle à partir des données existantes."""
    pid = plantation.id
    diag = _latest_diagnostic(db, pid)
    eudr = compute_eudr_score(plantation, db)
    defo = _latest_deforestation(db, pid)
    block = _active_block(db, plantation.producer_id)
    boundary = plantation.boundary
    producer = (
        db.query(Producer).filter(Producer.id == plantation.producer_id).first()
        if plantation.producer_id else None
    )

    harvests = db.query(Harvest).filter(Harvest.plantation_id == pid).all()
    total_kg = round(sum(float(h.quantity_kg or 0) for h in harvests), 1)
    last_harvest = max((h.harvest_date for h in harvests if h.harvest_date), default=None)
    ha = plantation.hectares or (boundary.area_hectares if boundary else None)
    yield_kg_ha = round(total_kg / ha, 1) if (ha and total_kg) else None

    # Agroforesterie : réutilise le calcul existant (DRY), best-effort.
    agro = None
    try:
        from app.api.routes import _compute_metrics
        agro = _compute_metrics(plantation.agro_records or [])
    except Exception:
        agro = None

    age = diag.plantation_age_years if diag else None

    return {
        "plantation": {
            "id": pid, "name": plantation.name, "owner_name": plantation.owner_name,
            "producer_name": producer.nom_complet if producer else None,
            "region": plantation.region, "country": plantation.country,
            "hectares": plantation.hectares,
            "has_gps": bool(plantation.latitude and plantation.longitude),
            "age_years": age,
        },
        "diagnostic": {
            "available": diag is not None,
            "global_score": diag.global_score if diag else None,
            "risk_level": diag.global_risk_level if diag else None,
            "date": diag.created_at.isoformat() if diag and diag.created_at else None,
            "days_since": _days_since(diag.created_at) if diag else None,
        },
        "eudr": {
            "status": eudr.status, "score": eudr.score, "max_score": eudr.max_score,
            "has_polygon": eudr.has_polygon,
            "rules_failed": [r.rule_id for r in eudr.rules if not r.passed],
        },
        "deforestation": {
            "verdict": defo.verdict if defo else None,
            "date": defo.check_date.isoformat() if defo and defo.check_date else None,
        },
        "agroforestry": agro,
        "harvests": {
            "total_kg": total_kg, "count": len(harvests),
            "last_date": last_harvest.isoformat() if last_harvest else None,
            "yield_kg_ha": yield_kg_ha,
        },
        "cacaoguard": {
            "blocked": block is not None,
            "reason": (block.block_reason.value if block and getattr(block, "block_reason", None) else None),
        },
        "boundary": {
            "has_polygon": boundary is not None,
            "area_hectares": boundary.area_hectares if boundary else None,
        },
    }


def compute_alerts(twin: dict) -> list[dict]:
    """Alertes par règles déterministes (sévérité high|medium|low), triées."""
    alerts: list[dict] = []

    def add(severity, code, label, reco):
        alerts.append({"severity": severity, "code": code, "label": label, "recommendation": reco})

    eudr, defo, diag = twin["eudr"], twin["deforestation"], twin["diagnostic"]
    cg, hv, pl = twin["cacaoguard"], twin["harvests"], twin["plantation"]

    if not eudr["has_polygon"]:
        add("high", "no_polygon", "Parcelle non délimitée", "Tracer le polygone sur la carte (requis EUDR).")
    if eudr["status"] == "non_conforme":
        add("high", "eudr_non_conforme", "Non conforme EUDR", "Traiter les blocages de conformité (page EUDR).")
    elif eudr["status"] == "a_verifier":
        add("medium", "eudr_a_verifier", "Conformité EUDR à vérifier", "Compléter les contrôles manquants.")

    verdict = (defo["verdict"] or "").lower()
    if verdict == "deforestation_detected":
        add("high", "deforestation", "Déforestation détectée", "Vérifier/documenter ; risque de non-conformité EUDR.")
    elif defo["verdict"] is None or verdict == "inconclusive":
        add("medium", "deforestation_todo", "Contrôle déforestation à faire", "Lancer le contrôle satellite (page EUDR).")

    if cg["blocked"]:
        add("high", "cacaoguard_block", "Blocage traçabilité CacaoGuard", "Traiter via le plan de remédiation.")

    if not diag["available"]:
        add("medium", "no_diagnostic", "Aucun diagnostic agronomique", "Réaliser un diagnostic terrain.")
    else:
        if diag["days_since"] is not None and diag["days_since"] > RECENT_DIAG_DAYS:
            add("medium", "diagnostic_old", "Diagnostic de plus de 12 mois", "Planifier un nouveau diagnostic.")
        if (diag["risk_level"] or "").lower() in ("élevé", "eleve", "high"):
            add("high", "agro_risk_high", "Risque agronomique élevé", "Intervention agronomique prioritaire.")

    if pl["age_years"] is not None and pl["age_years"] >= OLD_ORCHARD_YEARS:
        add("medium", "old_orchard", f"Verger âgé (~{int(pl['age_years'])} ans)", "Envisager une replantation progressive.")

    if hv["count"] == 0:
        add("low", "no_harvest", "Aucune récolte enregistrée", "Saisir les récoltes pour suivre la production.")
    elif hv["yield_kg_ha"] is not None and hv["yield_kg_ha"] < LOW_YIELD_KG_HA:
        add("medium", "low_yield", f"Rendement faible ({hv['yield_kg_ha']} kg/ha)",
            "Diagnostiquer les causes (sol, ombrage, âge des plants).")

    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda x: order.get(x["severity"], 3))
    return alerts


def build_coop_risk(
    db: Session,
    coop_id: Optional[int],
    *,
    limit: int = 50,
    offset: int = 0,
    severity: Optional[str] = None,
) -> dict:
    """Vue coopérative : alertes du jumeau agrégées sur TOUTES les parcelles, classées par risque.

    Calcul BATCHÉ (un petit nombre de requêtes quel que soit le nombre de
    parcelles) pour rester scalable jusqu'à des milliers de parcelles : on ne
    construit pas un jumeau complet par parcelle (trop de requêtes), on charge
    les signaux en lot puis on réutilise EXACTEMENT `compute_alerts` sur une vue
    allégée. L'EUDR ici se limite aux signaux légers (polygone + déforestation) ;
    le score EUDR complet reste sur la fiche parcelle.

    FAIL-CLOSED : sans coopérative, renvoie une vue vide.
    """
    empty = {
        "total_parcels": 0, "flagged_count": 0,
        "by_worst": {"high": 0, "medium": 0, "low": 0},
        "alert_totals": {"high": 0, "medium": 0, "low": 0},
        "limit": limit, "offset": offset, "returned": 0, "parcels": [],
    }
    if coop_id is None:
        return empty

    plantations = db.query(Plantation).filter(Plantation.cooperative_id == coop_id).all()
    if not plantations:
        return empty
    pids = [p.id for p in plantations]
    prod_ids = list({p.producer_id for p in plantations if p.producer_id})

    producers = (
        {pr.id: pr for pr in db.query(Producer).filter(Producer.id.in_(prod_ids)).all()}
        if prod_ids else {}
    )

    # Dernier diagnostic par parcelle (une requête, on garde le plus récent).
    diag_map: dict = {}
    for r in (
        db.query(
            Diagnostic.plantation_id, Diagnostic.global_risk_level,
            Diagnostic.created_at, Diagnostic.plantation_age_years,
        )
        .filter(Diagnostic.plantation_id.in_(pids))
        .order_by(Diagnostic.plantation_id, Diagnostic.created_at.desc())
        .all()
    ):
        diag_map.setdefault(r.plantation_id, r)

    # Parcelles délimitées (polygone).
    poly = {
        pid for (pid,) in
        db.query(PlantationBoundary.plantation_id)
        .filter(PlantationBoundary.plantation_id.in_(pids)).all()
    }

    # Dernier contrôle déforestation par parcelle.
    defo_map: dict = {}
    for r in (
        db.query(DeforestationCheck.plantation_id, DeforestationCheck.verdict)
        .filter(DeforestationCheck.plantation_id.in_(pids))
        .order_by(
            DeforestationCheck.plantation_id,
            DeforestationCheck.check_date.desc().nullslast(),
            DeforestationCheck.id.desc(),
        ).all()
    ):
        defo_map.setdefault(r.plantation_id, r)

    # Blocages CacaoGuard actifs (niveau producteur).
    blocked: set = set()
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
        if prod_ids:
            blocked = {
                pid for (pid,) in
                db.query(TraceabilityBlock.producer_id).filter(
                    TraceabilityBlock.producer_id.in_(prod_ids),
                    TraceabilityBlock.status == BlockStatus.ACTIVE,
                ).all()
            }
    except ImportError:
        blocked = set()

    # Récoltes : total + nombre par parcelle (une requête groupée).
    harv: dict = {}
    for pid_, total, cnt in (
        db.query(
            Harvest.plantation_id,
            func.coalesce(func.sum(Harvest.quantity_kg), 0),
            func.count(Harvest.id),
        ).filter(Harvest.plantation_id.in_(pids)).group_by(Harvest.plantation_id).all()
    ):
        harv[pid_] = (float(total or 0), int(cnt or 0))

    flagged: list = []
    by_worst = {"high": 0, "medium": 0, "low": 0}
    alert_totals = {"high": 0, "medium": 0, "low": 0}
    for p in plantations:
        d = diag_map.get(p.id)
        defo = defo_map.get(p.id)
        total_kg, hcount = harv.get(p.id, (0.0, 0))
        ha = p.hectares
        yield_kg_ha = round(total_kg / ha, 1) if (ha and total_kg) else None
        lite = {
            "plantation": {"age_years": d.plantation_age_years if d else None},
            "eudr": {"has_polygon": p.id in poly, "status": None},
            "deforestation": {"verdict": defo.verdict if defo else None},
            "diagnostic": {
                "available": d is not None,
                "days_since": _days_since(d.created_at) if d else None,
                "risk_level": d.global_risk_level if d else None,
            },
            "cacaoguard": {"blocked": p.producer_id in blocked},
            "harvests": {"count": hcount, "yield_kg_ha": yield_kg_ha},
        }
        alerts = compute_alerts(lite)
        if not alerts:
            continue
        counts = {"high": 0, "medium": 0, "low": 0}
        score = 0
        for a in alerts:
            counts[a["severity"]] = counts.get(a["severity"], 0) + 1
            score += SEVERITY_WEIGHT.get(a["severity"], 0)
        worst = "high" if counts["high"] else ("medium" if counts["medium"] else "low")
        by_worst[worst] += 1
        for k in alert_totals:
            alert_totals[k] += counts[k]
        pr = producers.get(p.producer_id) if p.producer_id else None
        flagged.append({
            "plantation_id": p.id, "name": p.name, "owner_name": p.owner_name,
            "producer_name": pr.nom_complet if pr else None,
            "region": p.region, "hectares": p.hectares,
            "risk_score": score, "worst_severity": worst,
            "counts": counts, "alerts": alerts,
        })

    flagged_count = len(flagged)
    if severity in ("high", "medium", "low"):
        flagged = [r for r in flagged if r["counts"][severity] > 0]
    flagged.sort(
        key=lambda r: (r["counts"]["high"], r["counts"]["medium"], r["counts"]["low"], r["risk_score"]),
        reverse=True,
    )
    page = flagged[offset: offset + limit]
    return {
        "total_parcels": len(plantations),
        "flagged_count": flagged_count,
        "by_worst": by_worst,
        "alert_totals": alert_totals,
        "limit": limit, "offset": offset, "returned": len(page),
        "parcels": page,
    }
