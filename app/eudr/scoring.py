"""
Moteur de scoring EUDR — 5 regles deterministes (Sprint EUDR-01a).

Chaque regle retourne `(passed: bool, reason: str)`. Le score total est
le nombre de regles passees (0-5). Le statut global se deduit :
- >= 4 : conforme (vert)
- 2-3  : a_verifier (orange)
- 0-1  : non_conforme (rouge)

Les regles sont volontairement simples et expliquables a un auditeur EUDR.
Les regles avancees (Hansen forest cover, geocoding chains) viendront en
EUDR-01b/01c.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models import (
    DeforestationCheck,
    Inspection,
    Plantation,
    PlantationBoundary,
)


# ---------------------------------------------------------------------------
# Constantes EUDR-01a
# ---------------------------------------------------------------------------

# Cote d'Ivoire bbox (incl. zones cacao) + ceinture cacao tropicale.
# Source : limites administratives officielles CI + carte ICRAF cacao belt.
CI_BBOX = {"lat_min": 4.3, "lat_max": 10.8, "lon_min": -8.6, "lon_max": -2.5}

# Tolerance entre superficie geometrique et declaree (20% par defaut).
AREA_TOLERANCE_PCT = 0.20

# Fenetre "visite recente" pour l'audit (12 mois standard EUDR/Fairtrade).
RECENT_VISIT_DAYS = 365

# Date butoir EUDR : aucune deforestation post 31/12/2020 (art. 3 du Reglement).
EUDR_CUTOFF_YEAR = 2020


# ---------------------------------------------------------------------------
# Types de sortie
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    rule_id: str
    label: str
    passed: bool
    weight: int = 1
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "passed": self.passed,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class EudrScore:
    plantation_id: int
    methodology_version: str
    score: int           # 0..5
    max_score: int       # 5
    status: str          # "conforme" | "a_verifier" | "non_conforme"
    badge_color: str     # "green" | "orange" | "red"
    rules: list[RuleResult] = field(default_factory=list)
    has_polygon: bool = False
    declared_hectares: Optional[float] = None
    geo_hectares: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "plantation_id": self.plantation_id,
            "methodology_version": self.methodology_version,
            "score": self.score,
            "max_score": self.max_score,
            "status": self.status,
            "badge_color": self.badge_color,
            "has_polygon": self.has_polygon,
            "declared_hectares": self.declared_hectares,
            "geo_hectares": self.geo_hectares,
            "rules": [r.to_dict() for r in self.rules],
        }


METHODOLOGY_VERSION = "eudr-1.1b"


# ---------------------------------------------------------------------------
# Implementation des 5 regles
# ---------------------------------------------------------------------------

def _parse_polygon(geojson_text: Optional[str]) -> Optional[list[list[float]]]:
    """Extrait les coordonnees du premier anneau d'un Polygon GeoJSON.

    Retourne None si invalide / absent. Format attendu : list[ [lng, lat] ].
    """
    if not geojson_text:
        return None
    try:
        geo = json.loads(geojson_text)
    except (json.JSONDecodeError, TypeError):
        return None
    # Accepte Polygon (anneau exterieur) et Feature(Polygon)
    geom = geo.get("geometry", geo)
    if geom.get("type") not in ("Polygon",):
        return None
    coords = geom.get("coordinates")
    if not coords or not isinstance(coords, list) or not coords[0]:
        return None
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    return ring


def rule_polygon_valid(boundary: Optional[PlantationBoundary]) -> RuleResult:
    """R1 : un polygone valide (>= 3 points) doit etre enregistre."""
    if boundary is None:
        return RuleResult(
            "polygon_valid", "Polygone enregistre", False,
            detail="Aucune delimitation cartographique sur la plantation.",
        )
    ring = _parse_polygon(boundary.geojson)
    if ring is None:
        return RuleResult(
            "polygon_valid", "Polygone enregistre", False,
            detail="GeoJSON invalide ou type non Polygon.",
        )
    if (boundary.points_count or len(ring)) < 4:
        # 3 sommets distincts + fermeture = 4 entrees attendues
        return RuleResult(
            "polygon_valid", "Polygone enregistre", False,
            detail=f"Polygone insuffisant ({boundary.points_count or len(ring)} points).",
        )
    return RuleResult(
        "polygon_valid", "Polygone enregistre", True,
        detail=f"{boundary.points_count or len(ring)} sommets, methode {boundary.method or 'manual'}.",
    )


def rule_area_matches(
    plantation: Plantation, boundary: Optional[PlantationBoundary],
) -> RuleResult:
    """R2 : superficie declaree coherente avec la geometrie (tolerance 20%)."""
    declared = plantation.hectares
    geo = boundary.area_hectares if boundary else None
    if declared is None or geo is None:
        return RuleResult(
            "area_matches", "Superficie coherente", False, detail=(
                "Aire geometrique manquante." if geo is None
                else "Aire declaree manquante sur la plantation."
            ),
        )
    if declared <= 0:
        return RuleResult(
            "area_matches", "Superficie coherente", False,
            detail="Superficie declaree <= 0.",
        )
    ratio = abs(geo - declared) / declared
    passed = ratio <= AREA_TOLERANCE_PCT
    return RuleResult(
        "area_matches", "Superficie coherente", passed, detail=(
            f"Declare {declared:.2f} ha vs geometrique {geo:.2f} ha "
            f"(ecart {ratio * 100:.1f}%, tolerance {int(AREA_TOLERANCE_PCT * 100)}%)."
        ),
    )


def _point_in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lon_min"] <= lon <= bbox["lon_max"]
    )


def rule_gps_in_cocoa_zone(
    plantation: Plantation, boundary: Optional[PlantationBoundary],
) -> RuleResult:
    """R3 : tous les sommets du polygone (ou le point GPS si pas de polygone)
    doivent tomber dans la bbox cacao officielle Cote d'Ivoire."""
    if boundary is not None:
        ring = _parse_polygon(boundary.geojson)
        if ring is None:
            return RuleResult(
                "gps_in_cocoa_zone", "Localisation dans zone cacao", False,
                detail="Polygone illisible pour verification geographique.",
            )
        outside = [(lon, lat) for lon, lat in ring if not _point_in_bbox(lat, lon, CI_BBOX)]
        if outside:
            return RuleResult(
                "gps_in_cocoa_zone", "Localisation dans zone cacao", False,
                detail=f"{len(outside)} sommet(s) hors bbox CI (premier : {outside[0]}).",
            )
        return RuleResult(
            "gps_in_cocoa_zone", "Localisation dans zone cacao", True,
            detail=f"Tous les {len(ring)} sommets dans la zone cacao CI.",
        )
    # Fallback : point GPS unique
    if plantation.latitude is None or plantation.longitude is None:
        return RuleResult(
            "gps_in_cocoa_zone", "Localisation dans zone cacao", False,
            detail="Aucune coordonnee GPS sur la plantation.",
        )
    in_zone = _point_in_bbox(plantation.latitude, plantation.longitude, CI_BBOX)
    return RuleResult(
        "gps_in_cocoa_zone", "Localisation dans zone cacao", in_zone, detail=(
            f"Point GPS ({plantation.latitude:.4f}, {plantation.longitude:.4f}) "
            f"{'dans' if in_zone else 'hors'} bbox cacao CI."
        ),
    )


def rule_recent_inspection(
    plantation: Plantation, db: Session, today: Optional[date] = None,
) -> RuleResult:
    """R4 : une inspection / visite enregistree dans les 12 derniers mois.

    Compte les `Inspection` (modele AgriVision, champ `date` DateTime) sur
    la plantation. Si CacaoGuard `MonitoringVisit` est disponible, on prend
    le plus recent des deux pour ne pas penaliser une coop qui ne passe que
    par les visites monitoring CacaoGuard.
    """
    today = today or date.today()

    last_inspection = (
        db.query(Inspection)
        .filter(Inspection.plantation_id == plantation.id, Inspection.date.isnot(None))
        .order_by(Inspection.date.desc())
        .first()
    )
    last_dt: Optional[date] = (
        last_inspection.date.date() if last_inspection and last_inspection.date else None
    )

    # Fallback : MonitoringVisit CacaoGuard sur le producteur (visites terrain)
    try:
        from app.db.models_social import MonitoringVisit, VisitStatus
        if plantation.producer_id is not None:
            last_visit = (
                db.query(MonitoringVisit)
                .filter(
                    MonitoringVisit.producer_id == plantation.producer_id,
                    MonitoringVisit.status == VisitStatus.COMPLETED,
                    MonitoringVisit.actual_date.isnot(None),
                )
                .order_by(MonitoringVisit.actual_date.desc())
                .first()
            )
            if last_visit and last_visit.actual_date:
                if last_dt is None or last_visit.actual_date > last_dt:
                    last_dt = last_visit.actual_date
    except ImportError:
        pass

    if last_dt is None:
        return RuleResult(
            "recent_inspection", "Inspection < 12 mois", False,
            detail="Aucune inspection / visite monitoring enregistree.",
        )
    delta_days = (today - last_dt).days
    passed = delta_days <= RECENT_VISIT_DAYS
    return RuleResult(
        "recent_inspection", "Inspection < 12 mois", passed, detail=(
            f"Derniere inspection/visite le {last_dt} "
            f"({delta_days} jour(s) - seuil {RECENT_VISIT_DAYS})."
        ),
    )


def rule_no_active_traceability_block(plantation: Plantation, db: Session) -> RuleResult:
    """R5 : aucun blocage tracabilite CacaoGuard actif sur le producteur."""
    # Import local pour eviter cycle si models_social pas dispo en dev
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
    except ImportError:
        return RuleResult(
            "no_active_block", "Aucun blocage CacaoGuard", True,
            detail="Module social non charge (mode degrade).",
        )
    if plantation.producer_id is None:
        return RuleResult(
            "no_active_block", "Aucun blocage CacaoGuard", True,
            detail="Pas de producteur rattache (regle non applicable).",
        )
    active = (
        db.query(TraceabilityBlock)
        .filter(
            TraceabilityBlock.producer_id == plantation.producer_id,
            TraceabilityBlock.status == BlockStatus.ACTIVE,
        )
        .first()
    )
    if active is None:
        return RuleResult(
            "no_active_block", "Aucun blocage CacaoGuard", True,
            detail="Aucun blocage actif sur le producteur.",
        )
    return RuleResult(
        "no_active_block", "Aucun blocage CacaoGuard", False, detail=(
            f"Blocage actif : {active.block_reason.value if active.block_reason else 'non specifie'}"
            f" (id {active.id})."
        ),
    )


def rule_no_deforestation(plantation: Plantation, db: Session) -> RuleResult:
    """R6 (EUDR-01b) : aucune deforestation depuis la date butoir (31/12/2020).

    Cadre extensible : consomme le dernier `DeforestationCheck` enregistre sur
    la plantation. La source peut etre Hansen GFC / Global Forest Watch une fois
    l'integration satellite branchee, ou une saisie manuelle / constat terrain.

    Verdicts :
      - clear                 -> PASSE (pas de perte de couvert post-2020)
      - deforestation_detected-> ECHEC (perte de couvert detectee)
      - inconclusive / absent -> ECHEC (controle a realiser)
    """
    label = "Pas de deforestation post-2020"
    last = (
        db.query(DeforestationCheck)
        .filter(DeforestationCheck.plantation_id == plantation.id)
        .order_by(DeforestationCheck.check_date.desc().nullslast(),
                  DeforestationCheck.id.desc())
        .first()
    )
    if last is None:
        return RuleResult(
            "no_deforestation", label, False,
            detail="Aucun controle de deforestation enregistre (a realiser).",
        )

    verdict = (last.verdict or "inconclusive").lower()
    src = last.source or "non specifiee"
    when = last.check_date.date().isoformat() if last.check_date else "date inconnue"

    if verdict == "clear":
        return RuleResult(
            "no_deforestation", label, True,
            detail=f"Controle {src} du {when} : aucune perte de couvert depuis {EUDR_CUTOFF_YEAR}.",
        )
    if verdict == "deforestation_detected":
        year = f" (perte detectee en {last.forest_loss_year})" if last.forest_loss_year else ""
        return RuleResult(
            "no_deforestation", label, False,
            detail=f"Controle {src} du {when} : deforestation detectee{year}.",
        )
    return RuleResult(
        "no_deforestation", label, False,
        detail=f"Controle {src} du {when} : resultat non concluant, verification requise.",
    )


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def _status_from_score(score: int, max_score: int = 5) -> tuple[str, str]:
    """Retourne (status, badge_color) selon le seuil EUDR-01a.

    Avec max_score = 5 : >=4 conforme, 2-3 a_verifier, 0-1 non_conforme.
    Generalise au prorata si max change : 80%+, 40-79%, < 40%.
    """
    if max_score <= 0:
        return "a_verifier", "orange"
    pct = score / max_score
    if pct >= 0.8:
        return "conforme", "green"
    if pct >= 0.4:
        return "a_verifier", "orange"
    return "non_conforme", "red"


def compute_eudr_score(
    plantation: Plantation,
    db: Session,
    today: Optional[date] = None,
) -> EudrScore:
    """Calcule le score EUDR-01a d'une plantation.

    Charge les dependances (boundary, inspections, blocs) via la session.
    """
    boundary = plantation.boundary  # relation 1-1
    rules = [
        rule_polygon_valid(boundary),
        rule_area_matches(plantation, boundary),
        rule_gps_in_cocoa_zone(plantation, boundary),
        rule_recent_inspection(plantation, db, today=today),
        rule_no_active_traceability_block(plantation, db),
        rule_no_deforestation(plantation, db),
    ]
    score = sum(r.weight for r in rules if r.passed)
    max_score = sum(r.weight for r in rules)
    status, color = _status_from_score(score, max_score)
    return EudrScore(
        plantation_id=plantation.id,
        methodology_version=METHODOLOGY_VERSION,
        score=score,
        max_score=max_score,
        status=status,
        badge_color=color,
        rules=rules,
        has_polygon=boundary is not None,
        declared_hectares=plantation.hectares,
        geo_hectares=boundary.area_hectares if boundary else None,
    )
