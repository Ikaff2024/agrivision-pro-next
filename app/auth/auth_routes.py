from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from collections import defaultdict

from app.db.database import get_db
from app.db.models import User, Cooperative
from app.auth.auth_service import (
    get_password_hash, verify_password,
    create_access_token, create_refresh_token, decode_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

ALLOWED_ROLES = {"admin", "agronomist", "technician"}

# ── Rate limiting léger en mémoire (5 tentatives / 60 s par IP) ───────────────
_login_attempts: dict = defaultdict(list)
MAX_ATTEMPTS  = 5
WINDOW_SECS   = 60


def _check_rate_limit(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    attempts = [t for t in _login_attempts[ip] if now - t < WINDOW_SECS]
    _login_attempts[ip] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Trop de tentatives. Réessayez dans {WINDOW_SECS} secondes.",
        )
    _login_attempts[ip].append(now)


# ── Schémas ───────────────────────────────────────────────────────────────────

class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: str
    cooperative_name: str
    country: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(req: RegisterUserRequest, db: Session = Depends(get_db)):
    if req.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle invalide. Valeurs autorisées : {', '.join(ALLOWED_ROLES)}",
        )
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email déjà enregistré.")

    coop = db.query(Cooperative).filter(Cooperative.name == req.cooperative_name).first()
    if not coop:
        coop = Cooperative(name=req.cooperative_name, country=req.country)
        db.add(coop)
        db.commit()
        db.refresh(coop)

    new_user = User(
        email=req.email,
        password_hash=get_password_hash(req.password),
        role=req.role,
        cooperative_id=coop.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Compte créé avec succès.", "user_id": new_user.id}


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Rate limiting par IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides.")

    token_data = {"sub": user.email, "role": user.role, "coop_id": user.cooperative_id}
    return {
        "access_token":  create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type":    "bearer",
        "expires_in":    120 * 60,  # secondes
    }


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """Échange un refresh token valide contre un nouvel access token."""
    payload = decode_token(req.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token de rafraîchissement invalide.")

    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.")

    token_data = {"sub": user.email, "role": user.role, "coop_id": user.cooperative_id}
    return {
        "access_token": create_access_token(token_data),
        "token_type":   "bearer",
        "expires_in":   120 * 60,
    }


@router.get("/me")
def get_me(db: Session = Depends(get_db),
           current_user: User = Depends(__import__('app.auth.auth_service', fromlist=['get_current_user']).get_current_user)):
    return {
        "id":             current_user.id,
        "email":          current_user.email,
        "role":           current_user.role,
        "cooperative_id": current_user.cooperative_id,
    }
