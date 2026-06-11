"""
Tracabilite physique du cacao (module #1) : entrepots, lots, mouvements, fusion
et passeport de tracabilite.

Principes :
- Tout est cloisonne par cooperative (multi-tenant).
- Un lot regroupe des recoltes (Harvest) ; son poids/nb de sacs derive des recoltes.
- Integration CacaoGuard : on REFUSE d'affecter a un lot une recolte dont le
  producteur a un blocage de tracabilite ACTIF (cas travail des enfants, etc.).
- Le passeport agrege producteurs, parcelles, certification, statut EUDR, blocages
  et journal des mouvements — exploitable pour un acheteur / auditeur.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Certification, Harvest, Lot, LotMovement, Plantation, Producer, User, Warehouse
from app.db.models_social import BlockStatus, TraceabilityBlock
from app.eudr.scoring import compute_eudr_score

router = APIRouter(tags=["Tracabilite des lots"])

_WRITE_ROLES = {"admin", "agronomist"}
_VALID_STATUS = {"open", "sealed", "shipped", "blocked", "merged"}


# ── Payloads ─────────────────────────────────────────────────────────────────

class WarehouseCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    location: Optional[str] = Field(None, max_length=255)
    capacity_kg: Optional[float] = Field(None, ge=0)


class LotCreate(BaseModel):
    season: Optional[str] = Field(None, max_length=50)
    certification_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    notes: Optional[str] = None
    harvest_ids: List[int] = Field(default_factory=list)


class HarvestAffect(BaseModel):
    harvest_ids: List[int] = Field(..., min_length=1)


class MovementCreate(BaseModel):
    movement_type: str = Field(..., max_length=40)
    quantity_kg: Optional[float] = Field(None, ge=0)
    to_warehouse_id: Optional[int] = None
    from_warehouse_id: Optional[int] = None
    reference: Optional[str] = Field(None, max_length=120)


class LotMerge(BaseModel):
    source_lot_ids: List[int] = Field(..., min_length=2)
    season: Optional[str] = Field(None, max_length=50)
    certification_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_write(user: User) -> None:
    if user.role not in _WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Action reservee a l'administrateur / agronome.")


def _coop_id(user: User):
    return user.cooperative_id


def _scoped_lot(lot_id: int, db: Session, user: User) -> Lot:
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot introuvable.")
    if _coop_id(user) is not None and lot.cooperative_id != _coop_id(user):
        raise HTTPException(status_code=403, detail="Lot d'une autre cooperative.")
    return lot


def _harvest_producer_id(db: Session, harvest: Harvest) -> Optional[int]:
    plantation = db.query(Plantation).filter(Plantation.id == harvest.plantation_id).first()
    return plantation.producer_id if plantation else None


def _blocked_producers(db: Session, producer_ids: set[int]) -> dict[int, TraceabilityBlock]:
    """Retourne {producer_id: block} pour les producteurs ayant un blocage ACTIF."""
    if not producer_ids:
        return {}
    blocks = db.query(TraceabilityBlock).filter(
        TraceabilityBlock.producer_id.in_(producer_ids),
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).all()
    return {b.producer_id: b for b in blocks}


def _load_scoped_harvests(db: Session, user: User, harvest_ids: list[int]) -> list[Harvest]:
    """Charge les recoltes demandees, en verifiant l'appartenance a la cooperative."""
    if not harvest_ids:
        return []
    harvests = db.query(Harvest).filter(Harvest.id.in_(harvest_ids)).all()
    found = {h.id for h in harvests}
    missing = set(harvest_ids) - found
    if missing:
        raise HTTPException(status_code=404, detail=f"Recolte(s) introuvable(s) : {sorted(missing)}.")
    if _coop_id(user) is not None:
        plant_ids = {h.plantation_id for h in harvests}
        plants = {
            p.id: p.cooperative_id
            for p in db.query(Plantation).filter(Plantation.id.in_(plant_ids)).all()
        }
        for h in harvests:
            if plants.get(h.plantation_id) != _coop_id(user):
                raise HTTPException(status_code=403, detail="Recolte d'une autre cooperative.")
    return harvests


def _guard_child_labor(db: Session, harvests: list[Harvest]) -> None:
    """Refuse l'affectation si un producteur concerne a un blocage CacaoGuard actif."""
    producer_ids = {pid for h in harvests if (pid := _harvest_producer_id(db, h)) is not None}
    blocked = _blocked_producers(db, producer_ids)
    if blocked:
        details = [
            {"producer_id": pid, "reason": b.block_reason.value, "block_id": b.id}
            for pid, b in blocked.items()
        ]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Affectation refusee : producteur(s) sous blocage de tracabilite CacaoGuard.",
                "blocked_producers": details,
            },
        )


def _recompute_totals(db: Session, lot: Lot) -> None:
    db.flush()  # garantit que les lot_id affectes sont visibles par la requete
    harvests = db.query(Harvest).filter(Harvest.lot_id == lot.id).all()
    lot.total_weight_kg = round(sum(float(h.quantity_kg or 0) for h in harvests), 2)
    lot.bag_count = int(sum(int(h.nbre_sacs or 0) for h in harvests))


def _generate_code(lot: Lot) -> str:
    year = datetime.utcnow().year
    return f"LOT-{year}-{lot.id:05d}"


def _movement(db: Session, lot: Lot, mtype: str, qty: float, user: User, **kw) -> LotMovement:
    mv = LotMovement(
        lot_id=lot.id,
        movement_type=mtype,
        quantity_kg=round(float(qty or 0), 2),
        from_warehouse_id=kw.get("from_warehouse_id"),
        to_warehouse_id=kw.get("to_warehouse_id"),
        reference=kw.get("reference"),
        movement_metadata=kw.get("metadata"),
        created_by_id=user.id if user else None,
    )
    db.add(mv)
    return mv


# ── Serializers ──────────────────────────────────────────────────────────────

def warehouse_to_dict(w: Warehouse) -> dict:
    return {
        "id": w.id, "name": w.name, "location": w.location,
        "capacity_kg": w.capacity_kg, "is_active": bool(w.is_active),
        "created_at": w.created_at,
    }


def movement_to_dict(m: LotMovement) -> dict:
    return {
        "id": m.id, "movement_type": m.movement_type, "quantity_kg": float(m.quantity_kg or 0),
        "from_warehouse_id": m.from_warehouse_id, "to_warehouse_id": m.to_warehouse_id,
        "reference": m.reference, "metadata": m.movement_metadata or {}, "created_at": m.created_at,
    }


def lot_to_dict(lot: Lot, include_movements: bool = False) -> dict:
    data = {
        "id": lot.id, "code": lot.code, "cooperative_id": lot.cooperative_id,
        "season": lot.season, "certification_id": lot.certification_id,
        "warehouse_id": lot.warehouse_id, "status": lot.status,
        "total_weight_kg": float(lot.total_weight_kg or 0), "bag_count": lot.bag_count or 0,
        "harvest_count": len(lot.harvests or []), "parent_lot_id": lot.parent_lot_id,
        "notes": lot.notes, "created_at": lot.created_at,
    }
    if include_movements:
        data["movements"] = [movement_to_dict(m) for m in lot.movements]
    return data


# ── Entrepots ────────────────────────────────────────────────────────────────

@router.get("/warehouses")
def list_warehouses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Warehouse)
    if _coop_id(current_user) is not None:
        q = q.filter(Warehouse.cooperative_id == _coop_id(current_user))
    return [warehouse_to_dict(w) for w in q.order_by(Warehouse.name).all()]


@router.post("/warehouses", status_code=201)
def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user)
    w = Warehouse(
        cooperative_id=_coop_id(current_user),
        name=data.name, location=data.location, capacity_kg=data.capacity_kg,
        created_by_id=current_user.id,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return warehouse_to_dict(w)


# ── Lots ─────────────────────────────────────────────────────────────────────

@router.get("/lots")
def list_lots(
    status: Optional[str] = None,
    season: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Lot)
    if _coop_id(current_user) is not None:
        q = q.filter(Lot.cooperative_id == _coop_id(current_user))
    if status:
        q = q.filter(Lot.status == status)
    if season:
        q = q.filter(Lot.season == season)
    return [lot_to_dict(lot) for lot in q.order_by(Lot.created_at.desc()).limit(limit).all()]


@router.post("/lots", status_code=201)
def create_lot(
    data: LotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user)
    harvests = _load_scoped_harvests(db, current_user, data.harvest_ids)
    _guard_child_labor(db, harvests)

    lot = Lot(
        cooperative_id=_coop_id(current_user),
        code="(pending)",
        season=data.season,
        certification_id=data.certification_id,
        warehouse_id=data.warehouse_id,
        status="open",
        notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(lot)
    db.flush()
    lot.code = _generate_code(lot)

    for h in harvests:
        h.lot_id = lot.id
    _recompute_totals(db, lot)
    _movement(db, lot, "creation", lot.total_weight_kg, current_user,
              to_warehouse_id=data.warehouse_id, metadata={"harvest_ids": data.harvest_ids})

    db.commit()
    db.refresh(lot)
    return lot_to_dict(lot, include_movements=True)


@router.get("/lots/{lot_id:int}")
def get_lot(lot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lot = _scoped_lot(lot_id, db, current_user)
    return lot_to_dict(lot, include_movements=True)


@router.post("/lots/{lot_id:int}/affect-harvests")
def affect_harvests(
    lot_id: int,
    data: HarvestAffect,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user)
    lot = _scoped_lot(lot_id, db, current_user)
    if lot.status not in {"open"}:
        raise HTTPException(status_code=409, detail="Seul un lot 'open' peut recevoir des recoltes.")
    harvests = _load_scoped_harvests(db, current_user, data.harvest_ids)
    _guard_child_labor(db, harvests)
    for h in harvests:
        if h.lot_id and h.lot_id != lot.id:
            raise HTTPException(status_code=409, detail=f"Recolte {h.id} deja affectee au lot {h.lot_id}.")
        h.lot_id = lot.id
    _recompute_totals(db, lot)
    _movement(db, lot, "adjustment", sum(float(h.quantity_kg or 0) for h in harvests), current_user,
              metadata={"affected_harvest_ids": data.harvest_ids})
    db.commit()
    db.refresh(lot)
    return lot_to_dict(lot, include_movements=True)


@router.post("/lots/{lot_id:int}/movements")
def add_movement(
    lot_id: int,
    data: MovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user)
    lot = _scoped_lot(lot_id, db, current_user)
    mtype = data.movement_type.strip().lower()
    allowed = {"warehouse_in", "transfer", "adjustment", "export_out", "seal"}
    if mtype not in allowed:
        raise HTTPException(status_code=400, detail=f"Type de mouvement invalide. Autorises : {sorted(allowed)}.")

    if mtype == "warehouse_in" and data.to_warehouse_id:
        lot.warehouse_id = data.to_warehouse_id
    if mtype == "seal":
        lot.status = "sealed"
    if mtype == "export_out":
        lot.status = "shipped"

    qty = data.quantity_kg if data.quantity_kg is not None else lot.total_weight_kg
    _movement(db, lot, mtype, qty, current_user,
              from_warehouse_id=data.from_warehouse_id, to_warehouse_id=data.to_warehouse_id,
              reference=data.reference)
    db.commit()
    db.refresh(lot)
    return lot_to_dict(lot, include_movements=True)


@router.post("/lots/merge", status_code=201)
def merge_lots(
    data: LotMerge,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user)
    sources = [_scoped_lot(sid, db, current_user) for sid in data.source_lot_ids]
    for s in sources:
        if s.status not in {"open", "sealed"}:
            raise HTTPException(status_code=409, detail=f"Lot {s.code} non fusionnable (statut {s.status}).")

    target = Lot(
        cooperative_id=_coop_id(current_user),
        code="(pending)",
        season=data.season or sources[0].season,
        certification_id=data.certification_id or sources[0].certification_id,
        warehouse_id=data.warehouse_id or sources[0].warehouse_id,
        status="open",
        notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(target)
    db.flush()
    target.code = _generate_code(target)

    for s in sources:
        for h in db.query(Harvest).filter(Harvest.lot_id == s.id).all():
            h.lot_id = target.id
        _movement(db, s, "split_out", s.total_weight_kg, current_user,
                  reference=target.code, metadata={"merged_into": target.id})
        s.status = "merged"
        s.parent_lot_id = target.id
        s.total_weight_kg = 0
        s.bag_count = 0

    _recompute_totals(db, target)
    _movement(db, target, "merge_in", target.total_weight_kg, current_user,
              metadata={"source_lot_ids": data.source_lot_ids})
    db.commit()
    db.refresh(target)
    return lot_to_dict(target, include_movements=True)


def build_lot_passport(db: Session, lot: Lot) -> dict:
    """Construit le passeport de tracabilite d'un lot (composition, EUDR, mouvements)."""
    harvests = db.query(Harvest).filter(Harvest.lot_id == lot.id).all()

    # Composition par producteur + statut EUDR + blocage par parcelle.
    plant_ids = {h.plantation_id for h in harvests}
    plantations = {p.id: p for p in db.query(Plantation).filter(Plantation.id.in_(plant_ids)).all()} if plant_ids else {}
    producer_ids = {p.producer_id for p in plantations.values() if p.producer_id}
    producers = {p.id: p for p in db.query(Producer).filter(Producer.id.in_(producer_ids)).all()} if producer_ids else {}
    blocked = _blocked_producers(db, producer_ids)

    composition = []
    eudr_compliant = 0
    eudr_total = 0
    for h in harvests:
        plantation = plantations.get(h.plantation_id)
        producer = producers.get(plantation.producer_id) if plantation and plantation.producer_id else None
        eudr_status = None
        if plantation:
            eudr_total += 1
            score = compute_eudr_score(plantation, db)
            eudr_status = score.status
            if score.status == "conforme":
                eudr_compliant += 1
        composition.append({
            "harvest_id": h.id,
            "plantation_id": h.plantation_id,
            "plantation_name": plantation.name if plantation else None,
            "producer_id": plantation.producer_id if plantation else None,
            "producer_name": producer.nom_complet if producer else None,
            "quantity_kg": float(h.quantity_kg or 0),
            "eudr_status": eudr_status,
            "producer_blocked": (plantation.producer_id in blocked) if plantation else False,
        })

    certification = db.query(Certification).filter(Certification.id == lot.certification_id).first() if lot.certification_id else None
    warehouse = db.query(Warehouse).filter(Warehouse.id == lot.warehouse_id).first() if lot.warehouse_id else None

    return {
        "lot": lot_to_dict(lot),
        "code": lot.code,
        "generated_at": datetime.utcnow().isoformat(),
        "certification": {"id": certification.id, "code": certification.code, "name": certification.nom_complet} if certification else None,
        "warehouse": warehouse_to_dict(warehouse) if warehouse else None,
        "composition": composition,
        "summary": {
            "harvests": len(harvests),
            "producers": len(producer_ids),
            "plantations": len(plant_ids),
            "total_weight_kg": float(lot.total_weight_kg or 0),
            "bag_count": lot.bag_count or 0,
            "eudr_compliant_plantations": eudr_compliant,
            "eudr_total_plantations": eudr_total,
            "eudr_compliance_rate_pct": round(eudr_compliant / eudr_total * 100, 1) if eudr_total else 0.0,
            "blocked_producers": len(blocked),
        },
        "movements": [movement_to_dict(m) for m in lot.movements],
    }


@router.get("/lots/{lot_id:int}/passport")
def lot_passport(lot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Passeport de tracabilite : composition, conformite et historique du lot (JSON)."""
    lot = _scoped_lot(lot_id, db, current_user)
    return build_lot_passport(db, lot)


@router.get("/lots/{lot_id:int}/passport.pdf")
def lot_passport_pdf(lot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Passeport de tracabilite au format PDF (charte AgriVision)."""
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    from app.services.lot_reports import (
        build_lot_passport_context, generate_lot_passport_pdf, lot_passport_filename,
    )
    lot = _scoped_lot(lot_id, db, current_user)
    passport = build_lot_passport(db, lot)
    context = build_lot_passport_context(passport)
    from app.services.reports import coop_brand
    context.update(coop_brand(db, lot.cooperative_id))
    pdf_bytes = generate_lot_passport_pdf(context)
    filename = lot_passport_filename(lot)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf",
                             headers={"Content-Disposition": disposition})


@router.get("/lots/{lot_id:int}/eudr-pack.zip")
def lot_eudr_pack(lot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Pack de diligence raisonnee EUDR du lot (livrable acheteur / importateur).

    ZIP : un DDS PDF par parcelle + parcelles.geojson + recapitulatif.csv.
    Reserve admin/agronome (document officiel de conformite).
    """
    if current_user.role not in _WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Export DDS reserve a l'administrateur / agronome.")
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    from app.services.eudr_pack import build_eudr_pack

    lot = _scoped_lot(lot_id, db, current_user)
    result = build_eudr_pack(db, lot)
    if result is None:
        raise HTTPException(status_code=400, detail="Lot sans parcelle : affectez des recoltes avant l'export.")
    data, filename = result
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(iter([data]), media_type="application/zip",
                             headers={"Content-Disposition": disposition})
