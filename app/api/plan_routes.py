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

import base64
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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


# ── Profil de la coopérative (nom, pays, responsables) ────────────────────────
class CoopManager(BaseModel):
    name: str
    role: str | None = None
    phone: str | None = None


class CoopProfileUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    managers: list[CoopManager] | None = None
    enforce_social_export_block: bool | None = None
    living_income_benchmark_cfa: float | None = None


def _managers_list(coop: Cooperative) -> list:
    return coop.managers if isinstance(coop.managers, list) else []


@router.get("/cooperatives/{cooperative_id:int}/profile")
def get_cooperative_profile(
    cooperative_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Profil de la coopérative (nom, pays, responsables). Lecture : tout membre de la coop."""
    if current_user.cooperative_id is not None and cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Cooperative non autorisee.")
    coop = _get_coop_or_404(db, cooperative_id)
    return {
        "cooperative_id": coop.id,
        "name": coop.name,
        "country": coop.country,
        "managers": _managers_list(coop),
        "enforce_social_export_block": bool(coop.enforce_social_export_block),
        "living_income_benchmark_cfa": coop.living_income_benchmark_cfa,
        "public_report_token": coop.public_report_token,
    }


@router.patch("/cooperatives/{cooperative_id:int}/profile")
def update_cooperative_profile(
    cooperative_id: int,
    data: CoopProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Modifie le nom / pays / responsables de la coopérative. Admin, sa propre coop.

    Le nom peut évoluer dans le temps ; il se répercute partout (en-têtes PDF, etc.).
    """
    _assert_coop_admin(current_user, cooperative_id)
    coop = _get_coop_or_404(db, cooperative_id)
    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Le nom de la coopérative ne peut pas être vide.")
        coop.name = new_name
    if data.country is not None:
        coop.country = data.country.strip() or None
    if data.managers is not None:
        # Normalise : on garde les responsables ayant au moins un nom.
        coop.managers = [
            {"name": m.name.strip(),
             "role": (m.role or "").strip() or None,
             "phone": (m.phone or "").strip() or None}
            for m in data.managers if (m.name or "").strip()
        ]
    if data.enforce_social_export_block is not None:
        coop.enforce_social_export_block = bool(data.enforce_social_export_block)
    if data.living_income_benchmark_cfa is not None:
        b = float(data.living_income_benchmark_cfa)
        if b < 0:
            raise HTTPException(status_code=400, detail="Le seuil de revenu vital ne peut pas être négatif.")
        # 0 (ou vide) => on revient au défaut serveur (NULL en base).
        coop.living_income_benchmark_cfa = b if b > 0 else None
    db.commit()
    db.refresh(coop)
    return {
        "cooperative_id": coop.id,
        "name": coop.name,
        "country": coop.country,
        "managers": _managers_list(coop),
        "enforce_social_export_block": bool(coop.enforce_social_export_block),
        "living_income_benchmark_cfa": coop.living_income_benchmark_cfa,
        "public_report_token": coop.public_report_token,
    }


@router.post("/cooperatives/{cooperative_id:int}/public-report-token")
def generate_public_report_token(
    cooperative_id: int,
    regenerate: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Génère (ou régénère) le jeton public de signalement de la coopérative.

    Le jeton alimente l'URL/QR affichée dans les villages : un signalement fait
    depuis cette URL est rattaché à CETTE coopérative. Régénérer invalide l'ancien.
    """
    _assert_coop_admin(current_user, cooperative_id)
    coop = _get_coop_or_404(db, cooperative_id)
    if not coop.public_report_token or regenerate:
        coop.public_report_token = secrets.token_urlsafe(12)
        db.commit()
        db.refresh(coop)
    return {"cooperative_id": coop.id, "public_report_token": coop.public_report_token}


# ── Logo de la coopérative (affiché sur les PDF) ──────────────────────────────
_ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_MAX_LOGO_BYTES = 512 * 1024  # 512 Ko (stocké en base, intégré aux PDF)


def _assert_coop_admin(current_user: User, cooperative_id: int) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Reserve a l'administrateur.")
    if current_user.cooperative_id is not None and cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=403, detail="Cooperative non autorisee.")


def _get_coop_or_404(db: Session, cooperative_id: int) -> Cooperative:
    coop = db.query(Cooperative).filter(Cooperative.id == cooperative_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Cooperative introuvable.")
    return coop


@router.get("/cooperatives/{cooperative_id:int}/logo")
def get_cooperative_logo(
    cooperative_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Logo courant de la coopérative (data-URI ou None). Admin, sa propre coop."""
    _assert_coop_admin(current_user, cooperative_id)
    coop = _get_coop_or_404(db, cooperative_id)
    return {
        "cooperative_id": coop.id,
        "logo": coop.logo_data,
        "size": coop.logo_size or "md",
        "plaque": bool(coop.logo_plaque),
    }


class LogoSettings(BaseModel):
    size: str | None = None      # sm | md | lg
    plaque: bool | None = None


@router.patch("/cooperatives/{cooperative_id:int}/logo-settings")
def set_cooperative_logo_settings(
    cooperative_id: int,
    data: LogoSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajuste l'affichage du logo sur les PDF (taille + pastille). Admin, sa coop."""
    _assert_coop_admin(current_user, cooperative_id)
    coop = _get_coop_or_404(db, cooperative_id)
    if data.size is not None:
        if data.size not in ("sm", "md", "lg"):
            raise HTTPException(status_code=400, detail="Taille invalide (sm | md | lg).")
        coop.logo_size = data.size
    if data.plaque is not None:
        coop.logo_plaque = bool(data.plaque)
    db.commit()
    return {"cooperative_id": coop.id, "size": coop.logo_size, "plaque": bool(coop.logo_plaque)}


@router.post("/cooperatives/{cooperative_id:int}/logo")
async def set_cooperative_logo(
    cooperative_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Téléverse le logo (PNG/JPEG/WebP, ≤512 Ko) ; stocké en data-URI base64."""
    _assert_coop_admin(current_user, cooperative_id)
    ctype = (file.content_type or "").lower()
    if ctype not in _ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail="Format non supporté (PNG, JPEG ou WebP).")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    if len(raw) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Logo trop volumineux (max 512 Ko).")
    coop = _get_coop_or_404(db, cooperative_id)
    norm_type = "image/jpeg" if ctype == "image/jpg" else ctype
    coop.logo_data = f"data:{norm_type};base64,{base64.b64encode(raw).decode('ascii')}"
    db.commit()
    return {"cooperative_id": coop.id, "size_bytes": len(raw), "ok": True}


@router.delete("/cooperatives/{cooperative_id:int}/logo")
def delete_cooperative_logo(
    cooperative_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire le logo de la coopérative (retour au « A » AgriVision par défaut)."""
    _assert_coop_admin(current_user, cooperative_id)
    coop = _get_coop_or_404(db, cooperative_id)
    coop.logo_data = None
    db.commit()
    return {"cooperative_id": coop.id, "ok": True}


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
