"""
assignment_routes.py
======================
Endpoints d'attribution des plantations aux techniciens (Sprint #1).

Toutes les operations d'ecriture sont reservees au role admin.
Le cloisonnement par role sur la LECTURE des plantations est gere
separement (phase 1.4).
"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    User, Plantation, Producer,
    PlantationAssignment, TechnicianSubstitution,
)
from app.auth.auth_service import get_current_user

router = APIRouter(prefix="/assignments", tags=["assignments"])
sub_router = APIRouter(prefix="/substitutions", tags=["substitutions"])


# ===========================================================================
# Schemas
# ===========================================================================

class AssignmentCreate(BaseModel):
    plantation_id: int
    technician_id: int


class BulkAssignmentCreate(BaseModel):
    plantation_ids: List[int]
    technician_id: int


class SectionAssignmentCreate(BaseModel):
    section: str
    technician_id: int


class FromRegistryRequest(BaseModel):
    technician_id: int
    formateur_nom: str


class SubstitutionCreate(BaseModel):
    absent_technician_id: int
    substitute_technician_id: int
    date_debut: datetime
    date_fin: datetime
    motif: Optional[str] = None


# ===========================================================================
# Helpers
# ===========================================================================

def _require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")


def _check_technician(db: Session, technician_id: int, coop_id: int) -> User:
    """Verifie que le technicien existe, est bien technicien, et de la coop."""
    tech = db.query(User).filter(User.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technicien introuvable.")
    if tech.cooperative_id != coop_id:
        raise HTTPException(status_code=403,
                            detail="Ce technicien n'appartient pas a votre cooperative.")
    if tech.role != "technician":
        raise HTTPException(status_code=400,
                            detail="L'utilisateur cible n'a pas le role technicien.")
    return tech


def _assign_one(db: Session, plantation_id: int, technician_id: int,
                admin_id: int, coop_id: int) -> str:
    """
    Attribue une plantation a un technicien (UPSERT).
    Retourne 'created' ou 'updated'. Ne commit pas.
    """
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == coop_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404,
                            detail=f"Plantation {plantation_id} introuvable.")

    existing = db.query(PlantationAssignment).filter(
        PlantationAssignment.plantation_id == plantation_id,
        PlantationAssignment.is_active == True,
    ).first()

    if existing:
        existing.technician_id = technician_id
        existing.assigned_by_id = admin_id
        existing.assigned_at = datetime.utcnow()
        return "updated"
    else:
        db.add(PlantationAssignment(
            plantation_id=plantation_id,
            technician_id=technician_id,
            assigned_by_id=admin_id,
            is_active=True,
        ))
        return "created"


# ===========================================================================
# Endpoints attribution
# ===========================================================================

@router.get("/technician/{technician_id}")
def get_technician_assignments(
    technician_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les plantations attribuees a un technicien."""
    _require_admin(current_user)
    _check_technician(db, technician_id, current_user.cooperative_id)

    assignments = db.query(PlantationAssignment).filter(
        PlantationAssignment.technician_id == technician_id,
        PlantationAssignment.is_active == True,
    ).all()

    plantation_ids = [a.plantation_id for a in assignments]
    plantations = db.query(Plantation).filter(
        Plantation.id.in_(plantation_ids or [-1])
    ).all() if plantation_ids else []

    return {
        "technician_id": technician_id,
        "count": len(plantations),
        "plantations": plantations,
    }


@router.post("")
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attribue une plantation a un technicien."""
    _require_admin(current_user)
    _check_technician(db, payload.technician_id, current_user.cooperative_id)

    result = _assign_one(db, payload.plantation_id, payload.technician_id,
                         current_user.id, current_user.cooperative_id)
    db.commit()
    return {"status": result, "plantation_id": payload.plantation_id,
            "technician_id": payload.technician_id}


@router.post("/bulk")
def create_bulk_assignments(
    payload: BulkAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attribue plusieurs plantations a un technicien en une fois."""
    _require_admin(current_user)
    _check_technician(db, payload.technician_id, current_user.cooperative_id)

    created, updated, errors = 0, 0, []
    for pid in payload.plantation_ids:
        try:
            r = _assign_one(db, pid, payload.technician_id,
                            current_user.id, current_user.cooperative_id)
            if r == "created":
                created += 1
            else:
                updated += 1
        except HTTPException as e:
            errors.append(f"Plantation {pid} : {e.detail}")

    db.commit()
    return {"created": created, "updated": updated,
            "errors": errors, "total": created + updated}


@router.post("/by-section")
def assign_by_section(
    payload: SectionAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Attribue toutes les plantations d'une section a un technicien.
    La section est portee par le producteur.
    """
    _require_admin(current_user)
    _check_technician(db, payload.technician_id, current_user.cooperative_id)

    # Producteurs de la section
    producer_ids = [
        p.id for p in db.query(Producer).filter(
            Producer.cooperative_id == current_user.cooperative_id,
            Producer.section == payload.section,
        ).all()
    ]
    if not producer_ids:
        raise HTTPException(status_code=404,
                            detail=f"Aucun producteur dans la section '{payload.section}'.")

    # Plantations de ces producteurs
    plantations = db.query(Plantation).filter(
        Plantation.producer_id.in_(producer_ids),
        Plantation.cooperative_id == current_user.cooperative_id,
    ).all()

    created, updated = 0, 0
    for plant in plantations:
        r = _assign_one(db, plant.id, payload.technician_id,
                        current_user.id, current_user.cooperative_id)
        if r == "created":
            created += 1
        else:
            updated += 1

    db.commit()
    return {"section": payload.section, "created": created,
            "updated": updated, "total": created + updated}


@router.post("/from-registry")
def assign_from_registry(
    payload: FromRegistryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pre-remplit les attributions depuis le registre : attribue au technicien
    toutes les plantations dont le producteur a formateur_interne_nom egal
    au nom fourni. Gain de temps majeur a la mise en place.

    La comparaison est insensible a la casse et aux espaces superflus.
    """
    _require_admin(current_user)
    _check_technician(db, payload.technician_id, current_user.cooperative_id)

    target = " ".join(payload.formateur_nom.strip().lower().split())

    # Producteurs dont le formateur correspond
    matching_producer_ids = []
    for p in db.query(Producer).filter(
        Producer.cooperative_id == current_user.cooperative_id,
        Producer.formateur_interne_nom.isnot(None),
    ).all():
        name = " ".join(str(p.formateur_interne_nom).strip().lower().split())
        if name == target:
            matching_producer_ids.append(p.id)

    if not matching_producer_ids:
        return {"status": "no_match", "formateur_nom": payload.formateur_nom,
                "created": 0, "updated": 0, "total": 0,
                "message": "Aucun producteur trouve pour ce formateur."}

    plantations = db.query(Plantation).filter(
        Plantation.producer_id.in_(matching_producer_ids),
        Plantation.cooperative_id == current_user.cooperative_id,
    ).all()

    created, updated = 0, 0
    for plant in plantations:
        r = _assign_one(db, plant.id, payload.technician_id,
                        current_user.id, current_user.cooperative_id)
        if r == "created":
            created += 1
        else:
            updated += 1

    db.commit()
    return {"status": "success", "formateur_nom": payload.formateur_nom,
            "created": created, "updated": updated, "total": created + updated}


@router.delete("/{plantation_id}")
def remove_assignment(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire l'attribution active d'une plantation (desactivation, pas suppression)."""
    _require_admin(current_user)

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    assignment = db.query(PlantationAssignment).filter(
        PlantationAssignment.plantation_id == plantation_id,
        PlantationAssignment.is_active == True,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404,
                            detail="Cette plantation n'a pas d'attribution active.")

    assignment.is_active = False
    db.commit()
    return {"status": "removed", "plantation_id": plantation_id}


# ===========================================================================
# Endpoints remplacement
# ===========================================================================

@sub_router.get("")
def list_substitutions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les remplacements de la cooperative, avec leur statut."""
    _require_admin(current_user)

    subs = db.query(TechnicianSubstitution).filter(
        TechnicianSubstitution.cooperative_id == current_user.cooperative_id,
    ).order_by(TechnicianSubstitution.date_debut.desc()).all()

    now = datetime.utcnow()
    result = []
    for s in subs:
        is_current = bool(s.is_active and s.date_debut <= now <= s.date_fin)
        result.append({
            "id": s.id,
            "absent_technician_id": s.absent_technician_id,
            "substitute_technician_id": s.substitute_technician_id,
            "date_debut": s.date_debut,
            "date_fin": s.date_fin,
            "motif": s.motif,
            "is_active": s.is_active,
            "is_current": is_current,
        })
    return result


@sub_router.post("")
def create_substitution(
    payload: SubstitutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cree un remplacement temporaire."""
    _require_admin(current_user)

    if payload.absent_technician_id == payload.substitute_technician_id:
        raise HTTPException(status_code=400,
                            detail="Le remplacant doit etre different du technicien absent.")
    if payload.date_fin <= payload.date_debut:
        raise HTTPException(status_code=400,
                            detail="La date de fin doit etre posterieure a la date de debut.")

    _check_technician(db, payload.absent_technician_id, current_user.cooperative_id)
    _check_technician(db, payload.substitute_technician_id, current_user.cooperative_id)

    sub = TechnicianSubstitution(
        cooperative_id=current_user.cooperative_id,
        absent_technician_id=payload.absent_technician_id,
        substitute_technician_id=payload.substitute_technician_id,
        date_debut=payload.date_debut,
        date_fin=payload.date_fin,
        motif=payload.motif,
        created_by_id=current_user.id,
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"status": "created", "id": sub.id}


@sub_router.delete("/{substitution_id}")
def cancel_substitution(
    substitution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Annule un remplacement (desactivation)."""
    _require_admin(current_user)

    sub = db.query(TechnicianSubstitution).filter(
        TechnicianSubstitution.id == substitution_id,
        TechnicianSubstitution.cooperative_id == current_user.cooperative_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Remplacement introuvable.")

    sub.is_active = False
    db.commit()
    return {"status": "cancelled", "id": substitution_id}
