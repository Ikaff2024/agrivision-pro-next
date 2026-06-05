"""Jumeau numérique de parcelle (FEATURE-PARCEL-360).

GET /plantations/{id}/twin : vue agrégée (diagnostic, EUDR, déforestation,
agroforesterie, récoltes, CacaoGuard, délimitation) + alertes par règles.
Lecture seule, scope coopérative.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, User
from app.services.twin import build_twin, compute_alerts

router = APIRouter(tags=["Jumeau de parcelle"])


@router.get("/plantations/{plantation_id}/twin")
def get_plantation_twin(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Jumeau d'une parcelle : agrégation des signaux existants + alertes actionnables."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if current_user.cooperative_id is not None and plantation.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre coopérative.")

    twin = build_twin(db, plantation)
    alerts = compute_alerts(twin)
    return {"twin": twin, "alerts": alerts, "alert_count": len(alerts)}
