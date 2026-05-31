"""
Plans d'abonnement (feature-gating) : exposition des features de l'utilisateur
et gestion du plan d'une cooperative.

- GET /me/features : plan + categories + modules autorises (pilote le menu front).
- GET /me : profil minimal de l'utilisateur connecte (+ plan).
- PATCH /cooperatives/{id}/plan : change le plan (admin uniquement).

Garde-fou reutilisable `require_module(...)` fourni pour proteger des routes
cote API quand le decoupage commercial sera fige (non applique massivement pour
rester non-cassant tant que tout le monde est en 'enterprise').
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Cooperative, User
from app.services.plans import (
    PLAN_CATEGORIES,
    has_module,
    normalize_plan,
    plan_overview,
)

router = APIRouter(tags=["Plans & profil"])


def _coop_plan(db: Session, cooperative_id: int | None) -> str:
    if cooperative_id is None:
        return "enterprise"
    coop = db.query(Cooperative).filter(Cooperative.id == cooperative_id).first()
    return normalize_plan(coop.plan if coop else None)


@router.get("/me")
def get_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = _coop_plan(db, current_user.cooperative_id)
    return {
        "email": current_user.email,
        "role": current_user.role,
        "cooperative_id": current_user.cooperative_id,
        "plan": plan,
    }


@router.get("/me/features")
def get_my_features(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Plan effectif + modules autorises (consomme par le menu frontend)."""
    plan = _coop_plan(db, current_user.cooperative_id)
    return plan_overview(plan)


class PlanUpdate(BaseModel):
    plan: str


@router.patch("/cooperatives/{cooperative_id:int}/plan")
def set_cooperative_plan(
    cooperative_id: int,
    data: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change le plan d'une cooperative (admin uniquement, sa propre coop)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Reserve a l'administrateur.")
    if data.plan not in PLAN_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Plan invalide : {sorted(PLAN_CATEGORIES)}.")
    # Un admin de coop ne gere que sa propre cooperative.
    if current_user.cooperative_id is not None and cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Cooperative non autorisee.")
    coop = db.query(Cooperative).filter(Cooperative.id == cooperative_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Cooperative introuvable.")
    coop.plan = data.plan
    db.commit()
    return {"cooperative_id": coop.id, "plan": coop.plan}


def require_module(module_id: str):
    """
    Dependance FastAPI reutilisable pour proteger une route selon le plan.
    A appliquer quand le decoupage commercial sera fige. Aujourd'hui inoffensif
    car le plan par defaut 'enterprise' inclut tout.
    """
    def _dep(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        plan = _coop_plan(db, current_user.cooperative_id)
        if not has_module(plan, module_id):
            raise HTTPException(
                status_code=403,
                detail=f"Module '{module_id}' non inclus dans votre plan ({plan}).",
            )
        return current_user
    return _dep
