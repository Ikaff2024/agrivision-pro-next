"""Cache du score EUDR par parcelle — P1 « passage à l'échelle » (7000+ parcelles).

`compute_eudr_score` recalcule le score à la volée (≈4-5 requêtes par parcelle). À
7000 parcelles, le recalcul EN BOUCLE dans les agrégats (dashboard direction, EUDR
summary / readiness / liste) génère des dizaines de milliers de requêtes par page →
lent / timeout. On stocke donc le résultat sur la plantation (colonnes `eudr_*`) et
les agrégats LISENT ces colonnes (0 requête supplémentaire par parcelle).

Stratégie de fraîcheur :
- `refresh_plantation_eudr` : recalcule + écrit le cache d'une parcelle (à appeler sur
  les mutations qui changent le score : délimitation, contrôle déforestation, blocage…).
- `refresh_all_eudr` : recompute en masse (backfill, après un gros import, ou tâche de nuit).
- `ensure_scores` : pour un agrégat, calcule paresseusement les parcelles jamais évaluées
  (cache NULL) en une passe, puis tout est lisible depuis les colonnes.

Note : la règle « inspection < 12 mois » dérive avec le temps sans mutation → un
recompute périodique (`refresh_all_eudr`) garde le cache juste. Un décalage de quelques
heures sur une fenêtre de 365 jours est négligeable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.db.models import Plantation
from app.eudr.scoring import compute_eudr_score


def refresh_plantation_eudr(plantation: Plantation, db: Session):
    """Recalcule le score EUDR d'une parcelle et l'écrit dans le cache (sans commit)."""
    s = compute_eudr_score(plantation, db)
    plantation.eudr_score = s.score
    plantation.eudr_max_score = s.max_score
    plantation.eudr_status = s.status
    plantation.eudr_color = s.badge_color
    plantation.eudr_has_polygon = s.has_polygon
    plantation.eudr_rules_failed = [r.rule_id for r in s.rules if not r.passed]
    plantation.eudr_computed_at = datetime.now(timezone.utc)
    return s


def refresh_all_eudr(db: Session, coop_id: Optional[int] = None) -> int:
    """Recompute en masse (backfill / après import / nuit). Retourne le nombre de parcelles."""
    q = db.query(Plantation)
    if coop_id is not None:
        q = q.filter(Plantation.cooperative_id == coop_id)
    count = 0
    for p in q.all():
        refresh_plantation_eudr(p, db)
        count += 1
    db.commit()
    return count


def ensure_scores(plantations: Iterable[Plantation], db: Session) -> None:
    """Calcule paresseusement les parcelles dont le cache est vide (1 commit groupé).

    Après cet appel, chaque parcelle a `eudr_status/score/...` lisibles directement.
    Auto-réparant : la 1re lecture après un import peuple le cache, les suivantes sont
    instantanées.
    """
    dirty = False
    for p in plantations:
        if p.eudr_computed_at is None:
            refresh_plantation_eudr(p, db)
            dirty = True
    if dirty:
        db.commit()


def cached_dict(plantation: Plantation) -> dict:
    """Vue dict du cache d'une parcelle (valeurs sûres si jamais calculé)."""
    return {
        "status": plantation.eudr_status or "a_verifier",
        "score": plantation.eudr_score or 0,
        "max_score": plantation.eudr_max_score or 0,
        "has_polygon": bool(plantation.eudr_has_polygon),
        "rules_failed": plantation.eudr_rules_failed or [],
    }
