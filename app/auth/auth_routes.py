import logging

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
    create_password_reset_token,
    decode_token,
    get_current_user,
    _password_fingerprint,
)
from app.services.email_service import (
    app_base_url,
    send_password_reset_email,
    smtp_is_configured,
)
from app.services.environment import current_environment, is_development

logger = logging.getLogger("agrivision.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])

VALID_ROLES = {"admin", "agronomist", "technician", "gestionnaire"}


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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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
        # ── Coopérative existante : inscription publique interdite ──
        raise HTTPException(
            status_code=403,
            detail=(
                "L'inscription sur une coopérative existante se fait via son administrateur. "
                "Demandez-lui de créer votre compte depuis le panneau d'administration."
            ),
        )

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


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change le mot de passe de l'utilisateur connecte (ancien + nouveau)."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe trop court (minimum 6 caracteres).")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit etre different de l'ancien.")
    current_user.password_hash = get_password_hash(req.new_password)
    db.commit()
    return {"status": "ok", "message": "Mot de passe modifie avec succes."}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Demande de reinitialisation de mot de passe (self-service).

    Renvoie TOUJOURS le meme message generique (anti-enumeration d'emails).
    Si l'email correspond a un compte actif, un lien de reinitialisation
    (valable 1 h, usage unique) est envoye par email.

    Le lien n'est JAMAIS renvoye dans la reponse HTTP, sauf si le serveur
    declare explicitement `ENVIRONMENT=development` ou `test` — filet de secours
    pour recuperer un admin unique verrouille sur un poste de developpement.
    En production (valeur par defaut, y compris variable absente), l'absence ou
    la panne de SMTP ne change rien : le lien part par email ou nulle part, et
    reste consultable dans les journaux serveur.
    """
    generic = {
        "status": "ok",
        "message": "Si un compte est associe a cet email, un lien de reinitialisation a ete envoye.",
    }
    email = (req.email or "").strip().lower()
    if not email:
        return generic

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        return generic

    token = create_password_reset_token(user.email, user.password_hash)
    reset_link = f"{app_base_url()}/reset_password.html?token={token}"
    sent = send_password_reset_email(user.email, reset_link)

    # Filet de securite pour l'admin unique en lockout, RESERVE aux postes de
    # developpement declares. La condition porte sur l'environnement, jamais sur
    # l'etat de SMTP : une variable SMTP_HOST perdue en production ne doit pas
    # transformer cet endpoint en distributeur de prises de controle de compte.
    if not sent and is_development():
        logger.warning(
            "ENVIRONMENT=%s : lien de reinitialisation renvoye dans la reponse HTTP "
            "(filet de secours de developpement). Interdit en production.",
            current_environment(),
        )
        return {**generic, "reset_link": reset_link, "smtp_configured": smtp_is_configured()}
    return generic


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Definit un nouveau mot de passe a partir d'un token de reinitialisation."""
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe trop court (minimum 6 caracteres).")

    payload = decode_token(req.token)
    if payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Lien de reinitialisation invalide.")

    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Lien de reinitialisation invalide.")

    # Usage unique : l'empreinte doit correspondre au mot de passe actuel.
    if payload.get("fp") != _password_fingerprint(user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Ce lien a deja ete utilise ou n'est plus valide. Refaites une demande.",
        )

    user.password_hash = get_password_hash(req.new_password)
    db.commit()
    return {"status": "ok", "message": "Mot de passe reinitialise avec succes. Vous pouvez vous connecter."}


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
