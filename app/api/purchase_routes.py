"""
Achats producteurs (module #2) : bons d'achat / pesees bord champ.

Un achat enregistre une pesee + un bon d'achat aupres d'un producteur. Si une
plantation est precisee, une Harvest est generee automatiquement (alimente les
volumes et la tracabilite des lots). Le suivi de paiement est COMPTABLE
(statut paye / en attente) — aucun mouvement d'argent n'est execute ici.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Harvest, Plantation, Producer, PurchaseRecord, User
from app.db.models_social import BlockStatus, TraceabilityBlock

router = APIRouter(prefix="/purchases", tags=["Achats producteurs"])

_FIELD_ROLES = {"admin", "agronomist", "technician", "gestionnaire"}  # achat = activite terrain ou guichet
_ADMIN_ROLES = {"admin", "agronomist", "gestionnaire"}
_VALID_QUALITIES = {"Bonne", "Moyenne", "Defauts"}


class PurchaseCreate(BaseModel):
    producer_id: int
    plantation_id: Optional[int] = None
    harvest_id: Optional[int] = None   # lier l'achat a une RECOLTE EXISTANTE (anti-doublon) au lieu d'en creer une
    receipt_number: Optional[str] = Field(None, max_length=120)
    purchase_date: Optional[datetime] = None
    season: Optional[str] = Field(None, max_length=50)
    certification_id: Optional[int] = None
    quality: Optional[str] = None
    gross_weight_kg: Optional[float] = Field(None, ge=0)
    tare_kg: float = Field(0, ge=0)
    net_weight_kg: Optional[float] = Field(None, ge=0)
    bag_count: int = Field(0, ge=0)
    price_per_kg_fcfa: Optional[float] = Field(None, ge=0)
    buyer_name: Optional[str] = Field(None, max_length=200)
    payment_status: str = Field("pending")
    payment_method: Optional[str] = Field(None, max_length=40)
    notes: Optional[str] = None
    create_harvest: bool = True


class PaymentUpdate(BaseModel):
    payment_method: Optional[str] = Field(None, max_length=40)
    payment_date: Optional[datetime] = None


def _coop_id(user: User):
    return user.cooperative_id


def _require(user: User, roles: set[str]) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Action non autorisee pour ce role.")


def _scoped(pid: int, db: Session, user: User) -> PurchaseRecord:
    rec = db.query(PurchaseRecord).filter(PurchaseRecord.id == pid).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Achat introuvable.")
    if _coop_id(user) is not None and rec.cooperative_id != _coop_id(user):
        raise HTTPException(status_code=403, detail="Achat d'une autre cooperative.")
    return rec


def _producer_blocked(db: Session, producer_id: int) -> bool:
    return db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id == producer_id,
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).first() is not None


def purchase_to_dict(r: PurchaseRecord, producer_name: Optional[str] = None, blocked: bool = False) -> dict:
    return {
        "id": r.id,
        "producer_id": r.producer_id,
        "producer_name": producer_name,
        "plantation_id": r.plantation_id,
        "harvest_id": r.harvest_id,
        "receipt_number": r.receipt_number,
        "purchase_date": r.purchase_date,
        "season": r.season,
        "certification_id": r.certification_id,
        "quality": r.quality,
        "gross_weight_kg": r.gross_weight_kg,
        "tare_kg": float(r.tare_kg or 0),
        "net_weight_kg": float(r.net_weight_kg or 0),
        "bag_count": r.bag_count or 0,
        "price_per_kg_fcfa": r.price_per_kg_fcfa,
        "total_amount_fcfa": float(r.total_amount_fcfa or 0),
        "payment_status": r.payment_status,
        "payment_date": r.payment_date,
        "payment_method": r.payment_method,
        "buyer_name": r.buyer_name,
        "producer_blocked": blocked,
        "notes": r.notes,
        "created_at": r.created_at,
    }


@router.get("")
def list_purchases(
    producer_id: Optional[int] = None,
    season: Optional[str] = None,
    payment_status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(PurchaseRecord)
    if _coop_id(current_user) is not None:
        q = q.filter(PurchaseRecord.cooperative_id == _coop_id(current_user))
    if producer_id:
        q = q.filter(PurchaseRecord.producer_id == producer_id)
    if season:
        q = q.filter(PurchaseRecord.season == season)
    if payment_status:
        q = q.filter(PurchaseRecord.payment_status == payment_status)
    rows = q.order_by(PurchaseRecord.purchase_date.desc()).limit(limit).all()
    pnames = {
        p.id: p.nom_complet
        for p in db.query(Producer).filter(Producer.id.in_({r.producer_id for r in rows})).all()
    } if rows else {}
    return [purchase_to_dict(r, pnames.get(r.producer_id)) for r in rows]


@router.get("/summary")
def purchases_summary(
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(PurchaseRecord)
    if _coop_id(current_user) is not None:
        q = q.filter(PurchaseRecord.cooperative_id == _coop_id(current_user))
    if season:
        q = q.filter(PurchaseRecord.season == season)
    rows = q.all()
    total_kg = sum(float(r.net_weight_kg or 0) for r in rows)
    total_amount = sum(float(r.total_amount_fcfa or 0) for r in rows)
    paid = [r for r in rows if r.payment_status == "paid"]
    pending = [r for r in rows if r.payment_status == "pending"]
    return {
        "purchases": len(rows),
        "total_net_kg": round(total_kg, 1),
        "total_amount_fcfa": round(total_amount, 0),
        "paid_count": len(paid),
        "paid_amount_fcfa": round(sum(float(r.total_amount_fcfa or 0) for r in paid), 0),
        "pending_count": len(pending),
        "pending_amount_fcfa": round(sum(float(r.total_amount_fcfa or 0) for r in pending), 0),
    }


@router.get("/duplicate-check")
def purchase_duplicate_check(
    plantation_id: int,
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anti-doublon : récoltes EXISTANTES pour une parcelle (+ campagne).

    Le formulaire d'achat l'appelle quand une parcelle est choisie : s'il existe
    déjà une récolte pour cette parcelle/campagne, saisir un achat qui régénère une
    récolte ferait un DOUBLON de volume → on propose plutôt de LIER (`harvest_id`).
    """
    coop = _coop_id(current_user)
    pl = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not pl or (coop is not None and pl.cooperative_id != coop):
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    q = db.query(Harvest).filter(Harvest.plantation_id == plantation_id)
    if season:
        q = q.filter(Harvest.season == season)
    harvests = q.order_by(Harvest.harvest_date.desc()).all()
    return {
        "plantation_id": plantation_id,
        "season": season,
        "has_duplicate_risk": len(harvests) > 0,
        "existing_harvests": [
            {
                "id": h.id,
                "quantity_kg": float(h.quantity_kg or 0),
                "season": h.season,
                "harvest_date": h.harvest_date,
                "numero_recu_achat": h.numero_recu_achat,
                "price_per_kg_fcfa": h.price_per_kg_fcfa,
            }
            for h in harvests
        ],
    }


@router.get("/producer-balances")
def producer_balances(
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Solde de paiement par producteur : montant total acheté, payé et DÛ (en
    attente), trié par solde dû décroissant. Lecture seule, scope coopérative."""
    coop = _coop_id(current_user)
    q = db.query(PurchaseRecord)
    if coop is not None:
        q = q.filter(PurchaseRecord.cooperative_id == coop)
    if season:
        q = q.filter(PurchaseRecord.season == season)
    rows = q.all()

    agg: dict[int, dict] = {}
    for r in rows:
        a = agg.setdefault(r.producer_id, {
            "producer_id": r.producer_id, "purchases": 0, "net_kg": 0.0,
            "total_amount_fcfa": 0.0, "paid_amount_fcfa": 0.0,
            "pending_amount_fcfa": 0.0, "pending_count": 0, "last_purchase_date": None,
        })
        amt = float(r.total_amount_fcfa or 0)
        a["purchases"] += 1
        a["net_kg"] += float(r.net_weight_kg or 0)
        a["total_amount_fcfa"] += amt
        if r.payment_status == "paid":
            a["paid_amount_fcfa"] += amt
        elif r.payment_status == "pending":
            a["pending_amount_fcfa"] += amt
            a["pending_count"] += 1
        if r.purchase_date and (a["last_purchase_date"] is None or r.purchase_date > a["last_purchase_date"]):
            a["last_purchase_date"] = r.purchase_date

    pnames = {
        p.id: p.nom_complet
        for p in db.query(Producer).filter(Producer.id.in_(agg.keys())).all()
    } if agg else {}

    producers = []
    for pid, a in agg.items():
        a["producer_name"] = pnames.get(pid)
        for k in ("net_kg", "total_amount_fcfa", "paid_amount_fcfa", "pending_amount_fcfa"):
            a[k] = round(a[k], 1 if k == "net_kg" else 0)
        producers.append(a)
    producers.sort(key=lambda x: x["pending_amount_fcfa"], reverse=True)

    with_outstanding = [p for p in producers if p["pending_amount_fcfa"] > 0]
    return {
        "producers": producers,
        "totals": {
            "producers_with_outstanding": len(with_outstanding),
            "outstanding_amount_fcfa": round(sum(p["pending_amount_fcfa"] for p in with_outstanding), 0),
            "outstanding_count": sum(p["pending_count"] for p in with_outstanding),
        },
    }


@router.post("/producer/{producer_id:int}/settle")
def settle_producer(
    producer_id: int,
    data: PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Règle (marque payés) TOUS les achats en attente d'un producteur — suivi
    comptable, aucun virement exécuté. Réservé admin/agronome."""
    _require(current_user, _ADMIN_ROLES)
    coop = _coop_id(current_user)
    producer = db.query(Producer).filter(Producer.id == producer_id).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    if coop is not None and producer.cooperative_id != coop:
        raise HTTPException(status_code=403, detail="Producteur d'une autre cooperative.")

    q = db.query(PurchaseRecord).filter(
        PurchaseRecord.producer_id == producer_id,
        PurchaseRecord.payment_status == "pending",
    )
    if coop is not None:
        q = q.filter(PurchaseRecord.cooperative_id == coop)
    pendings = q.all()

    when = data.payment_date or datetime.utcnow()
    total = 0.0
    for r in pendings:
        r.payment_status = "paid"
        r.payment_date = when
        if data.payment_method:
            r.payment_method = data.payment_method
        total += float(r.total_amount_fcfa or 0)
    db.commit()
    return {
        "producer_id": producer_id,
        "producer_name": producer.nom_complet,
        "settled_count": len(pendings),
        "settled_amount_fcfa": round(total, 0),
    }


@router.post("", status_code=201)
def create_purchase(
    data: PurchaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require(current_user, _FIELD_ROLES)

    producer = db.query(Producer).filter(Producer.id == data.producer_id).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur introuvable.")
    if _coop_id(current_user) is not None and producer.cooperative_id != _coop_id(current_user):
        raise HTTPException(status_code=403, detail="Producteur d'une autre cooperative.")

    plantation = None
    if data.plantation_id is not None:
        plantation = db.query(Plantation).filter(Plantation.id == data.plantation_id).first()
        if not plantation:
            raise HTTPException(status_code=404, detail="Plantation introuvable.")
        if _coop_id(current_user) is not None and plantation.cooperative_id != _coop_id(current_user):
            raise HTTPException(status_code=403, detail="Plantation d'une autre cooperative.")

    # Anti-doublon : lier l'achat a une recolte EXISTANTE (ne pas en recreer une).
    linked_harvest = None
    if data.harvest_id is not None:
        linked_harvest = db.query(Harvest).filter(Harvest.id == data.harvest_id).first()
        if not linked_harvest:
            raise HTTPException(status_code=404, detail="Recolte a lier introuvable.")
        hpl = db.query(Plantation).filter(Plantation.id == linked_harvest.plantation_id).first()
        if _coop_id(current_user) is not None and (not hpl or hpl.cooperative_id != _coop_id(current_user)):
            raise HTTPException(status_code=403, detail="Recolte d'une autre cooperative.")
        if plantation is None:
            plantation = hpl

    if data.quality and data.quality not in _VALID_QUALITIES:
        raise HTTPException(status_code=400, detail=f"Qualite invalide : {sorted(_VALID_QUALITIES)}.")
    if data.payment_status not in {"pending", "paid", "cancelled"}:
        raise HTTPException(status_code=400, detail="Statut de paiement invalide.")

    # Poids net : fourni, ou calcule brut - tare.
    net = data.net_weight_kg
    if net is None and data.gross_weight_kg is not None:
        net = max(0.0, data.gross_weight_kg - (data.tare_kg or 0))
    if not net or net <= 0:
        raise HTTPException(status_code=400, detail="Poids net (ou brut) requis et superieur a 0.")

    total = round(net * data.price_per_kg_fcfa, 2) if data.price_per_kg_fcfa else 0.0
    purchase_date = data.purchase_date or datetime.utcnow()

    rec = PurchaseRecord(
        cooperative_id=_coop_id(current_user),
        producer_id=producer.id,
        plantation_id=plantation.id if plantation else None,
        receipt_number=data.receipt_number,
        purchase_date=purchase_date,
        season=data.season,
        certification_id=data.certification_id,
        quality=data.quality,
        gross_weight_kg=data.gross_weight_kg,
        tare_kg=data.tare_kg or 0,
        net_weight_kg=round(net, 2),
        bag_count=data.bag_count or 0,
        price_per_kg_fcfa=data.price_per_kg_fcfa,
        total_amount_fcfa=total,
        payment_status=data.payment_status,
        payment_date=datetime.utcnow() if data.payment_status == "paid" else None,
        payment_method=data.payment_method,
        buyer_name=data.buyer_name,
        notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(rec)
    db.flush()
    if linked_harvest is not None:
        rec.harvest_id = linked_harvest.id   # lie a la recolte existante → zero doublon de volume

    # Genere une recolte tracable si une plantation est rattachee ET aucun lien existant.
    if plantation and data.create_harvest and linked_harvest is None:
        harvest = Harvest(
            plantation_id=plantation.id,
            harvest_date=purchase_date,
            quantity_kg=round(net, 2),
            quality=data.quality or "Moyenne",
            price_per_kg_fcfa=data.price_per_kg_fcfa,
            season=data.season,
            nbre_sacs=data.bag_count or 0,
            numero_recu_achat=data.receipt_number,
            certification_id=data.certification_id,
            notes=f"Genere depuis l'achat #{rec.id}",
            created_by_user_id=current_user.id,
        )
        db.add(harvest)
        db.flush()
        rec.harvest_id = harvest.id

    db.commit()
    db.refresh(rec)
    return purchase_to_dict(rec, producer.nom_complet, _producer_blocked(db, producer.id))


@router.get("/{purchase_id:int}")
def get_purchase(purchase_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rec = _scoped(purchase_id, db, current_user)
    producer = db.query(Producer).filter(Producer.id == rec.producer_id).first()
    return purchase_to_dict(rec, producer.nom_complet if producer else None, _producer_blocked(db, rec.producer_id))


@router.post("/{purchase_id:int}/mark-paid")
def mark_paid(
    purchase_id: int,
    data: PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marque un achat comme paye (suivi comptable ; n'execute aucun virement)."""
    _require(current_user, _ADMIN_ROLES)
    rec = _scoped(purchase_id, db, current_user)
    if rec.payment_status == "cancelled":
        raise HTTPException(status_code=409, detail="Achat annule : paiement impossible.")
    rec.payment_status = "paid"
    rec.payment_date = data.payment_date or datetime.utcnow()
    if data.payment_method:
        rec.payment_method = data.payment_method
    db.commit()
    db.refresh(rec)
    producer = db.query(Producer).filter(Producer.id == rec.producer_id).first()
    return purchase_to_dict(rec, producer.nom_complet if producer else None)
