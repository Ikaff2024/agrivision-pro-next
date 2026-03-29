from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import User, Cooperative
from app.auth.auth_service import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

VALID_ROLES = {"admin", "agronomist", "technician"}


class RegisterUserRequest(BaseModel):
    email: str
    password: str
    role: str
    cooperative_name: str
    country: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(req: RegisterUserRequest, db: Session = Depends(get_db)):
    """
    Enregistre un nouvel utilisateur selon les règles métier coopérative :

    - Coopérative inexistante → créée automatiquement, utilisateur devient Admin
      (quel que soit le rôle demandé : il est le fondateur).
    - Coopérative existante → rôle accepté SAUF Admin, qui ne peut être attribué
      qu'en self-service. Un Admin existant doit promouvoir manuellement.
    """
    # Validation du rôle
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle invalide. Valeurs acceptées : {', '.join(VALID_ROLES)}",
        )

    # Email déjà utilisé ?
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email déjà enregistré.")

    # Mot de passe minimum
    if len(req.password) < 6:
        raise HTTPException(
            status_code=400, detail="Mot de passe trop court (minimum 6 caractères)."
        )

    coop = db.query(Cooperative).filter(
        Cooperative.name == req.cooperative_name
    ).first()

    if not coop:
        # ── Nouvelle coopérative : l'inscrit en est le fondateur → Admin forcé ──
        coop = Cooperative(name=req.cooperative_name, country=req.country)
        db.add(coop)
        db.commit()
        db.refresh(coop)
        assigned_role = "admin"  # fondateur, toujours admin
    else:
        # ── Coopérative existante : Admin interdit en self-service ──
        if req.role == "admin":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Le rôle Admin ne peut pas être auto-attribué sur une coopérative existante. "
                    "Contactez l'administrateur de votre coopérative."
                ),
            )
        assigned_role = req.role

    new_user = User(
        email=req.email,
        password_hash=get_password_hash(req.password),
        role=assigned_role,
        cooperative_id=coop.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Compte créé avec succès.",
        "user_id": new_user.id,
        "role": assigned_role,
        "cooperative": coop.name,
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Authentifie l'utilisateur et retourne un access token + refresh token.
    """
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants incorrects.")

    token_data = {
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    }
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "role": user.role,
    }


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """
    Échange un refresh token valide contre un nouvel access token.
    """
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token invalide.")

    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.")

    token_data = {
        "sub": user.email,
        "role": user.role,
        "coop_id": user.cooperative_id,
    }
    return {
        "access_token": create_access_token(token_data),
        "token_type": "bearer",
    }
