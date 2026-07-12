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
    FarmForceAssessment,
    Harvest,
    Plantation,
    PlantationBoundary,
    PlantationCertification,
    Producer,
)
from app.eudr.scoring import compute_eudr_score

# Pondération de sévérité pour classer les parcelles (vue coop « à risque »).
SEVERITY_WEIGHT = {"high": 4, "medium": 2, "low": 1}

# Seuils explicables
RECENT_DIAG_DAYS = 365      # diagnostic considéré récent < 12 mois
OLD_ORCHARD_YEARS = 25      # verger vieillissant
LOW_YIELD_KG_HA = 300.0     # rendement cacao faible (réf. ~400-600 kg/ha)

# Tendance de rendement (Palier 2, prédictif LÉGER & EXPLICABLE) : on compare le
# rendement kg/ha de la dernière campagne à la précédente. Aucune extrapolation ;
# on n'affiche une tendance que si ≥ 2 campagnes de données (sinon « insuffisant »).
YIELD_TREND_MIN_YEARS = 2
YIELD_TREND_DELTA_PCT = 15.0   # seuil de variation jugée significative (hausse/baisse)


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


def _is_future(dt) -> bool:
    """True si l'échéance est dans le futur (ou absente = sans expiration)."""
    if dt is None:
        return True
    try:
        d = dt.date() if hasattr(dt, "date") else dt
        return d >= date.today()
    except Exception:
        return True


def _living_income_block(net_income) -> dict:
    """Bloc revenu vital à partir du revenu net (réutilise le verdict FarmForce)."""
    if net_income is None:
        return {"available": False}
    from app.services.farmforce_reports import living_income_assessment
    li = living_income_assessment(net_income)
    return {
        "available": True,
        "net_income_cfa": round(float(net_income), 0),
        "status": li.get("living_income_status"),           # atteint | ecart | None
        "pct": li.get("living_income_pct"),
        "benchmark_cfa": li.get("living_income_benchmark_cfa"),
    }


def _cert_block(expirations: list) -> dict:
    """Bloc certification à partir des dates d'expiration des liens de la parcelle."""
    if not expirations:
        return {"count": 0, "has_active": False, "needs_renewal": False}
    active = sum(1 for e in expirations if _is_future(e))
    return {
        "count": len(expirations),
        "has_active": active > 0,
        "needs_renewal": active == 0,   # toutes expirées → renouvellement requis
    }


_ACTIVE_REMEDIATION = ("pending_approval", "approved", "in_progress", "escalated")


def _active_remediation_count(db: Session, producer_id: Optional[int]) -> int:
    """Nb de plans de remédiation ACTIFS du producteur (protection de l'enfant)."""
    if not producer_id:
        return 0
    try:
        from app.db.models_social import RemediationPlan, RemediationStatus
    except ImportError:
        return 0
    statuses = [RemediationStatus(s) for s in _ACTIVE_REMEDIATION]
    return (
        db.query(RemediationPlan)
        .filter(RemediationPlan.producer_id == producer_id,
                RemediationPlan.status.in_(statuses))
        .count()
    )


def compute_yield_trend(harvests, hectares) -> dict:
    """Trajectoire de rendement (kg/ha) par campagne (année), + direction explicable.

    Groupe les récoltes par ANNÉE (robuste, indépendant du paramétrage des campagnes),
    divise par la surface, puis compare la dernière campagne à la précédente. Renvoie
    `available=False` tant qu'on n'a pas au moins 2 campagnes (pas de fausse précision).
    """
    if not hectares or hectares <= 0:
        return {"available": False, "reason": "surface (ha) inconnue"}
    by_year: dict = {}
    for h in harvests:
        d = h.harvest_date
        if not d:
            continue
        by_year[d.year] = by_year.get(d.year, 0.0) + float(h.quantity_kg or 0)
    years = sorted(by_year)
    if len(years) < YIELD_TREND_MIN_YEARS:
        return {"available": False, "reason": "données insuffisantes (< 2 campagnes)",
                "n_years": len(years)}
    series = [{"year": y, "kg": round(by_year[y], 1),
               "yield_kg_ha": round(by_year[y] / hectares, 1)} for y in years]
    latest, previous = series[-1]["yield_kg_ha"], series[-2]["yield_kg_ha"]
    pct = round((latest - previous) / previous * 100, 1) if previous and previous > 0 else None
    if pct is None:
        direction = "indetermine"
    elif pct <= -YIELD_TREND_DELTA_PCT:
        direction = "baisse"
    elif pct >= YIELD_TREND_DELTA_PCT:
        direction = "hausse"
    else:
        direction = "stable"
    return {
        "available": True, "n_years": len(years), "series": series,
        "latest_year": years[-1], "previous_year": years[-2],
        "latest_yield_kg_ha": latest, "previous_yield_kg_ha": previous,
        "pct_change": pct, "direction": direction,
    }


def _geometry_block(db: Session, plantation: Plantation, boundary) -> dict:
    """Validité du polygone + chevauchements avec les autres parcelles de la coop.

    Best-effort : si le module géo (shapely) est indisponible, renvoie available=False.
    """
    from app.services.geo import find_overlaps, geo_available, validate_geometry
    if not geo_available():
        return {"available": False, "reason": "module géo non disponible"}
    val = (validate_geometry(boundary.geojson) if boundary
           else {"available": True, "valid": False, "reason": "Parcelle non délimitée."})
    ovl = find_overlaps(db, plantation)
    return {
        "available": True,
        "valid": val.get("valid"),
        "reason": val.get("reason"),
        "repairable": val.get("repairable"),
        "overlaps": ovl.get("overlaps", []),
        "overlap_count": ovl.get("count", 0),
    }


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

    # Dimensions sociale / économique / certification (nourrissent aussi la vue « à risque »).
    ff = (
        db.query(FarmForceAssessment.net_income_cfa)
        .filter(FarmForceAssessment.producer_id == plantation.producer_id)
        .order_by(FarmForceAssessment.created_at.desc())
        .first()
        if plantation.producer_id else None
    )
    cert_exps = [
        exp for (exp,) in
        db.query(PlantationCertification.date_expiration)
        .filter(PlantationCertification.plantation_id == pid).all()
    ]
    rem_active = _active_remediation_count(db, plantation.producer_id)

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
        "yield_trend": compute_yield_trend(harvests, ha),
        "geometry": _geometry_block(db, plantation, boundary),
        "cacaoguard": {
            "blocked": block is not None,
            "reason": (block.block_reason.value if block and getattr(block, "block_reason", None) else None),
            "remediation_active": rem_active,
        },
        "living_income": _living_income_block(ff[0] if ff else None),
        "certification": _cert_block(cert_exps),
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

    # Géométrie : polygone invalide (rejet EUDR) et chevauchement de parcelles
    # (double-mapping). Absents de la vue coop batchée (`geometry` non calculé).
    geo = twin.get("geometry") or {}
    if geo.get("available"):
        if geo.get("valid") is False and geo.get("reason") != "Parcelle non délimitée.":
            add("high", "geometry_invalid", "Polygone invalide",
                "Corriger le tracé (auto-intersection) — un polygone invalide fait rejeter le dossier EUDR.")
        if geo.get("overlap_count"):
            add("high", "plot_overlap", f"Chevauchement avec {geo['overlap_count']} parcelle(s)",
                "Vérifier la délimitation : double-mapping possible (risque de fraude / rejet EUDR).")

    # Tendance de rendement (Palier 2) — signalée seulement en BAISSE significative.
    # (Absente de la vue coop batchée : `yield_trend` n'y est pas calculé → pas d'alerte.)
    yt = twin.get("yield_trend") or {}
    if yt.get("available") and yt.get("direction") == "baisse":
        pct = yt.get("pct_change")
        label = "Rendement en baisse" + (f" ({pct:.0f}%)" if isinstance(pct, (int, float)) else "")
        add("medium", "yield_declining", label,
            "Diagnostiquer la cause (âge des plants, sol, maladies) et planifier une action.")

    # Dimensions sociale / économique / certification — signaux ACTIONNABLES seulement
    # (on ne signale PAS la simple absence de donnée, pour ne pas noyer la vue « à risque »).
    if (cg or {}).get("remediation_active", 0):
        add("high", "remediation_active", "Plan de remédiation en cours",
            "Suivre le plan de protection de l'enfant jusqu'à clôture.")
    li = twin.get("living_income") or {}
    if li.get("available") and li.get("status") == "ecart":
        pct = li.get("pct")
        label = "Revenu vital non atteint" + (
            f" ({pct:.0f}% du seuil)" if isinstance(pct, (int, float)) else "")
        add("high", "living_income_gap", label,
            "Renforcer les revenus (diversification, productivité, primes durabilité).")
    cert = twin.get("certification") or {}
    if cert.get("needs_renewal"):
        add("medium", "cert_expired", "Certification expirée",
            "Planifier le renouvellement de la certification.")

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

    # Revenu net le plus récent par producteur (revenu vital).
    ff_net: dict = {}
    if prod_ids:
        for r in (
            db.query(FarmForceAssessment.producer_id, FarmForceAssessment.net_income_cfa,
                     FarmForceAssessment.created_at)
            .filter(FarmForceAssessment.producer_id.in_(prod_ids))
            .order_by(FarmForceAssessment.producer_id, FarmForceAssessment.created_at.desc())
            .all()
        ):
            ff_net.setdefault(r.producer_id, r.net_income_cfa)

    # Certifications par parcelle (dates d'expiration).
    cert_exps: dict = {}
    for pid_, exp in (
        db.query(PlantationCertification.plantation_id, PlantationCertification.date_expiration)
        .filter(PlantationCertification.plantation_id.in_(pids)).all()
    ):
        cert_exps.setdefault(pid_, []).append(exp)

    # Plans de remédiation actifs par producteur (protection de l'enfant).
    rem_count: dict = {}
    try:
        from app.db.models_social import RemediationPlan, RemediationStatus
        if prod_ids:
            statuses = [RemediationStatus(s) for s in _ACTIVE_REMEDIATION]
            for pr_id, cnt in (
                db.query(RemediationPlan.producer_id, func.count(RemediationPlan.id))
                .filter(RemediationPlan.producer_id.in_(prod_ids),
                        RemediationPlan.status.in_(statuses))
                .group_by(RemediationPlan.producer_id).all()
            ):
                rem_count[pr_id] = int(cnt)
    except ImportError:
        rem_count = {}

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
            "cacaoguard": {
                "blocked": p.producer_id in blocked,
                "remediation_active": rem_count.get(p.producer_id, 0),
            },
            "harvests": {"count": hcount, "yield_kg_ha": yield_kg_ha},
            "living_income": (
                _living_income_block(ff_net.get(p.producer_id)) if p.producer_id
                else {"available": False}
            ),
            "certification": _cert_block(cert_exps.get(p.id, [])),
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
