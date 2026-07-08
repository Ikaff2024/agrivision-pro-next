"""Signalement PUBLIC — sans compte (mécanisme de grievance CLMRS).

Un membre de la communauté remplit un formulaire depuis une URL/QR affichée dans
son village ; le jeton public de la coopérative (dans l'URL) garantit que le
signalement est rattaché à LA BONNE coopérative. Aucune authentification requise.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from datetime import datetime

from app.api.complaint_routes import _maybe_create_alert, _next_reference
from app.db.database import get_db
from app.db.models import Cooperative
from app.db.models_social import (
    Complaint,
    ComplaintSeverity,
    ComplaintStatus,
    ComplaintType,
    TrainingSession,
)

router = APIRouter(prefix="/public", tags=["Signalement public"])


def _coop_by_token(db: Session, token: str | None) -> Cooperative | None:
    t = (token or "").strip()
    if len(t) < 8:
        return None
    return db.query(Cooperative).filter(
        Cooperative.public_report_token == t,
        Cooperative.is_active == True,  # noqa: E712
    ).first()


@router.get("/report-info")
def public_report_info(c: str = Query(..., description="Jeton public de la coopérative"),
                       db: Session = Depends(get_db)):
    """Nom de la coopérative pour un jeton — pour afficher « Signalement · Coop X »."""
    coop = _coop_by_token(db, c)
    if not coop:
        raise HTTPException(status_code=404, detail="Lien de signalement invalide ou expiré.")
    return {"cooperative_name": coop.name}


class PublicComplaint(BaseModel):
    coop_token: str = Field(..., min_length=8, max_length=100)
    complaint_type: ComplaintType = ComplaintType.OTHER
    severity: ComplaintSeverity = ComplaintSeverity.MEDIUM
    description: str = Field(..., min_length=10, max_length=5000)
    reporter_name: str | None = Field(None, max_length=200)
    reporter_contact: str | None = Field(None, max_length=100)
    location_description: str | None = Field(None, max_length=2000)


@router.post("/complaints", status_code=201)
def public_create_complaint(payload: PublicComplaint, db: Session = Depends(get_db)):
    """Crée un signalement PUBLIC (sans compte), rattaché à la coop du jeton."""
    coop = _coop_by_token(db, payload.coop_token)
    if not coop:
        raise HTTPException(status_code=404, detail="Lien de signalement invalide ou expiré.")

    reference = _next_reference(db)
    complaint = Complaint(
        complaint_reference=reference,
        cooperative_id=coop.id,               # rattachement garanti à la bonne coop
        source="community",
        complaint_type=payload.complaint_type,
        severity=payload.severity,
        description=payload.description.strip(),
        reporter_name=(payload.reporter_name or "").strip() or None,
        reporter_contact=(payload.reporter_contact or "").strip() or None,
        location_description=(payload.location_description or "").strip() or None,
        status=ComplaintStatus.RECEIVED,
        is_confidential=True,
        confidentiality_level="confidential",
        created_by=None,
    )
    db.add(complaint)
    db.flush()
    try:
        _maybe_create_alert(db, complaint)
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    # Réponse minimale : ne jamais renvoyer le contenu à un client public.
    return {"reference": reference, "message": "Signalement reçu. Merci — il sera traité en confidentialité."}


# ── Avis de formation ANONYMES (chaque participant note sans voir les autres) ──

def _session_by_feedback_token(db: Session, token: str | None) -> TrainingSession | None:
    t = (token or "").strip()
    if len(t) < 8:
        return None
    return db.query(TrainingSession).filter(TrainingSession.feedback_token == t).first()


@router.get("/training-info")
def public_training_info(s: str = Query(..., description="Jeton d'avis de la session"),
                         db: Session = Depends(get_db)):
    """Titre de la session pour la page d'avis publique."""
    session = _session_by_feedback_token(db, s)
    if not session:
        raise HTTPException(status_code=404, detail="Lien d'avis invalide ou expiré.")
    return {"title": session.title, "scheduled_date": session.scheduled_date}


class PublicFeedback(BaseModel):
    feedback_token: str = Field(..., min_length=8, max_length=100)
    rating: int = Field(..., ge=0, le=5)
    comment: str | None = Field(None, max_length=1000)


@router.post("/training-feedback", status_code=201)
def public_training_feedback(payload: PublicFeedback, db: Session = Depends(get_db)):
    """Enregistre un avis ANONYME de participant (note 0-5 + commentaire) — aucune
    identité, aucun compte. Chaque avis est indépendant : pas d'influence entre pairs."""
    session = _session_by_feedback_token(db, payload.feedback_token)
    if not session:
        raise HTTPException(status_code=404, detail="Lien d'avis invalide ou expiré.")
    fb = list(session.participant_feedback or [])
    fb.append({
        "rating": int(payload.rating),
        "comment": (payload.comment or "").strip() or None,
        "at": datetime.utcnow().isoformat(),
    })
    session.participant_feedback = fb          # réassignation -> déclenche l'update JSON
    db.commit()
    return {"message": "Merci pour votre avis !", "count": len(fb)}
