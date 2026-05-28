"""
Routes EUDR (EU Deforestation Regulation) — Sprint EUDR-01a.

Endpoints :
- GET /plantations/{id}/eudr-score    : breakdown des 5 regles + statut
- GET /plantations/{id}/eudr-status   : version condensee (badge + score)
- GET /eudr/cooperative-summary       : agrege par cooperative
- GET /eudr/plantations               : liste plantations triee par risque

Tous les endpoints sont en lecture seule (le polygone se sauve via
POST /plantations/{id}/boundary qui existe deja dans routes.py).

Permissions :
- admin/agronomist : voient toutes les plantations de leur coop
- technician : voient les plantations qui leur sont assignees
- viewer : interdit
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, User
from app.eudr.scoring import compute_eudr_score

router = APIRouter(prefix="", tags=["EUDR - conformite parcellaire"])


def _accessible_plantations(db: Session, user: User) -> list[Plantation]:
    """Liste des plantations visibles pour `user` (scoping cooperative)."""
    query = db.query(Plantation)
    if user.cooperative_id is not None:
        query = query.filter(Plantation.cooperative_id == user.cooperative_id)
    if user.role == "technician":
        # Reuse de PlantationAssignment si disponible
        try:
            from app.db.models import PlantationAssignment
            assigned_ids = [
                a.plantation_id for a in db.query(PlantationAssignment).filter(
                    PlantationAssignment.technician_id == user.id,
                    PlantationAssignment.is_active == True,
                ).all()
            ]
            if assigned_ids:
                query = query.filter(Plantation.id.in_(assigned_ids))
            else:
                return []
        except ImportError:
            pass
    return query.all()


def _check_access(plantation: Plantation, user: User) -> None:
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    if user.cooperative_id is not None and plantation.cooperative_id != user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre cooperative.")


@router.get("/plantations/{plantation_id}/eudr-score")
def get_eudr_score(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne le breakdown complet des 5 regles EUDR + statut."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    score = compute_eudr_score(plantation, db)
    return score.to_dict()


@router.get("/plantations/{plantation_id}/eudr-status")
def get_eudr_status(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Version condensee pour les badges (status + score sans le detail)."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    s = compute_eudr_score(plantation, db)
    return {
        "plantation_id": s.plantation_id,
        "score": s.score,
        "max_score": s.max_score,
        "status": s.status,
        "badge_color": s.badge_color,
        "has_polygon": s.has_polygon,
        "methodology_version": s.methodology_version,
    }


@router.get("/eudr/cooperative-summary")
def get_cooperative_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """KPIs cooperative : % conformes, % a verifier, % non conformes."""
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    plantations = _accessible_plantations(db, current_user)
    if not plantations:
        return {
            "total": 0,
            "conforme": 0,
            "a_verifier": 0,
            "non_conforme": 0,
            "with_polygon": 0,
            "without_polygon": 0,
            "average_score": 0.0,
            "compliance_rate_pct": 0.0,
        }

    by_status = {"conforme": 0, "a_verifier": 0, "non_conforme": 0}
    with_poly = 0
    total_score = 0
    total_max = 0
    for p in plantations:
        s = compute_eudr_score(p, db)
        by_status[s.status] = by_status.get(s.status, 0) + 1
        if s.has_polygon:
            with_poly += 1
        total_score += s.score
        total_max += s.max_score

    total = len(plantations)
    avg = (total_score / total_max * 100) if total_max else 0
    return {
        "total": total,
        "conforme": by_status["conforme"],
        "a_verifier": by_status["a_verifier"],
        "non_conforme": by_status["non_conforme"],
        "with_polygon": with_poly,
        "without_polygon": total - with_poly,
        "average_score_pct": round(avg, 1),
        "compliance_rate_pct": round(by_status["conforme"] / total * 100, 1) if total else 0,
    }


@router.get("/eudr/plantations")
def list_plantations_with_eudr(
    sort: str = Query("risk", pattern="^(risk|score|name)$"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les plantations accessibles avec leur score EUDR.

    `sort=risk` : non_conforme d'abord puis a_verifier puis conforme.
    `sort=score` : score ascendant (faibles d'abord).
    `sort=name` : ordre alphabetique.
    """
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    plantations = _accessible_plantations(db, current_user)

    enriched = []
    for p in plantations[:limit]:
        s = compute_eudr_score(p, db)
        enriched.append({
            "id": p.id,
            "name": p.name,
            "producer_id": p.producer_id,
            "owner_name": p.owner_name,
            "region": p.region,
            "hectares": p.hectares,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "eudr_score": s.score,
            "eudr_max": s.max_score,
            "eudr_status": s.status,
            "eudr_color": s.badge_color,
            "has_polygon": s.has_polygon,
            "rules_failed": [r.rule_id for r in s.rules if not r.passed],
        })

    if sort == "name":
        enriched.sort(key=lambda x: (x["name"] or "").lower())
    elif sort == "score":
        enriched.sort(key=lambda x: x["eudr_score"])
    else:  # risk
        status_order = {"non_conforme": 0, "a_verifier": 1, "conforme": 2}
        enriched.sort(key=lambda x: (status_order.get(x["eudr_status"], 9), x["eudr_score"]))

    return {"count": len(enriched), "plantations": enriched}
