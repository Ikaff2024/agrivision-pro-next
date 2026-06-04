"""
Veille Marché Cacao (module premium).

GET /market/intelligence : prix (CCC officiel + cours Londres/NY indicatifs),
actualités filtrables et synthèse IA. L'appel Claude se fait CÔTÉ SERVEUR
(clé protégée), avec cache partagé et suivi de coût (AiUsage).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Cooperative, User
from app.services.market_intel import get_market_intelligence

logger = logging.getLogger("agrivision")

router = APIRouter(prefix="/market", tags=["Veille marché"])


@router.get("/intelligence")
async def market_intelligence(
    refresh: bool = Query(False, description="Forcer une actualisation (admin/agronome)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Feature-gating : module premium ──
    from app.services.plans import has_module

    plan = "enterprise"
    if current_user.cooperative_id:
        coop = db.query(Cooperative).filter(Cooperative.id == current_user.cooperative_id).first()
        if coop and coop.plan:
            plan = coop.plan
    if not has_module(plan, "veille"):
        raise HTTPException(
            status_code=403,
            detail="Module « Veille Marché » non inclus dans votre plan (premium requis).",
        )

    # Le rafraîchissement forcé est réservé aux rôles d'écriture (borne le coût IA).
    force = bool(refresh) and current_user.role in ("admin", "agronomist")
    data, usage = await get_market_intelligence(force=force)

    # Suivi du coût de revient : on enregistre les tokens réellement consommés.
    # Best-effort : un échec d'enregistrement ne casse jamais la réponse.
    if usage:
        try:
            from app.db.models import AiUsage
            from app.services.ai_cost import compute_cost_usd
            db.add(AiUsage(
                cooperative_id=current_user.cooperative_id,
                user_id=current_user.id,
                plantation_id=None,
                feature="market_intelligence",
                model=usage.get("model", ""),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cost_usd=compute_cost_usd(usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
            ))
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning("Enregistrement AiUsage (veille) échoué (ignoré) : %s", e)

    return data
