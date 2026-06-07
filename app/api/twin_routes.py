"""Jumeau numérique de parcelle (FEATURE-PARCEL-360).

GET /plantations/{id}/twin : vue agrégée (diagnostic, EUDR, déforestation,
agroforesterie, récoltes, CacaoGuard, délimitation) + alertes par règles.
Lecture seule, scope coopérative.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, User
from app.services.twin import build_coop_risk, build_twin, compute_alerts
from app.services.weather import get_weather

router = APIRouter(tags=["Jumeau de parcelle"])


@router.get("/twin/at-risk")
async def get_coop_twin_at_risk(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None, description="Filtrer : high|medium|low"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vue coopérative : parcelles classées par risque (alertes du jumeau agrégées).

    Scopée à la coopérative de l'utilisateur. Calcul batché → scalable jusqu'à
    des milliers de parcelles. Liste priorisée (parcelles à traiter d'abord).
    """
    sev = severity if severity in ("high", "medium", "low") else None
    return build_coop_risk(
        db, current_user.cooperative_id, limit=limit, offset=offset, severity=sev,
    )


@router.get("/plantations/{plantation_id}/twin")
async def get_plantation_twin(
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
    # Météo courante (Open-Meteo, best-effort) — complète la vue 360°.
    twin["weather"] = await get_weather(plantation.latitude, plantation.longitude)
    alerts = compute_alerts(twin)
    return {"twin": twin, "alerts": alerts, "alert_count": len(alerts)}
