from datetime import datetime
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FarmForceAssessment, Producer
from app.importers.farmforce_excel import parse_farmforce_excel

router = APIRouter(prefix="/farmforce", tags=["FarmForce"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class FarmForcePayload(BaseModel):
    producer_id: int
    campagne_id: Optional[int] = None
    campaign_label: str = Field(default="2025-2026", min_length=4)
    localite: Optional[str] = None
    pr_code: Optional[str] = None
    household_members: list[dict] = Field(default_factory=list)
    parcels: list[dict] = Field(default_factory=list)
    revenue_items: list[dict] = Field(default_factory=list)
    cost_items: list[dict] = Field(default_factory=list)
    family_labor_items: list[dict] = Field(default_factory=list)
    hired_labor_items: list[dict] = Field(default_factory=list)
    food_security_items: list[dict] = Field(default_factory=list)
    notes: Optional[str] = None


class FarmForceResponse(FarmForcePayload):
    id: int
    producer_name: str
    total_revenue_cfa: float
    total_cost_cfa: float
    profit_cfa: float
    family_labor_days: float
    hired_labor_days: float
    return_per_family_day_cfa: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _number(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _item_total(item: dict, total_key: str = "total_cfa") -> float:
    explicit = _number(item.get(total_key))
    if explicit:
        return explicit
    quantity = _number(item.get("quantity") or item.get("quantite"))
    price = _number(item.get("unit_price_cfa") or item.get("prix_unitaire"))
    return quantity * price


def _labor_days(item: dict) -> float:
    if item.get("total_days") not in (None, ""):
        return _number(item.get("total_days"))
    direct_keys = ("producer_days", "spouse_days", "other_family_days", "children_days")
    direct = sum(_number(item.get(key)) for key in direct_keys)
    if direct:
        return direct
    workers = _number(item.get("workers"))
    days = _number(item.get("days_per_worker") or item.get("days"))
    return workers * days


def _calculate(data: FarmForcePayload) -> dict:
    total_revenue = sum(_item_total(item, "revenue_cfa") for item in data.revenue_items)
    total_revenue += sum(_item_total(item, "market_value_cfa") for item in data.food_security_items)
    input_costs = sum(_item_total(item, "cost_cfa") for item in data.cost_items)
    family_days = sum(_labor_days(item) for item in data.family_labor_items)
    hired_days = sum(_labor_days(item) for item in data.hired_labor_items)
    hired_costs = sum(
        _item_total(item, "labor_cost_cfa")
        or (_labor_days(item) * _number(item.get("daily_wage_cfa")))
        for item in data.hired_labor_items
    )
    total_cost = input_costs + hired_costs
    profit = total_revenue - total_cost
    return {
        "total_revenue_cfa": round(total_revenue, 2),
        "total_cost_cfa": round(total_cost, 2),
        "profit_cfa": round(profit, 2),
        "family_labor_days": round(family_days, 2),
        "hired_labor_days": round(hired_days, 2),
        "return_per_family_day_cfa": round(profit / family_days, 2) if family_days else None,
    }


def _serialize(assessment: FarmForceAssessment) -> dict:
    return {
        "id": assessment.id,
        "producer_id": assessment.producer_id,
        "producer_name": assessment.producer.nom_complet if assessment.producer else "Producteur inconnu",
        "campagne_id": assessment.campagne_id,
        "campaign_label": assessment.campaign_label,
        "localite": assessment.localite,
        "pr_code": assessment.pr_code,
        "household_members": assessment.household_members or [],
        "parcels": assessment.parcels or [],
        "revenue_items": assessment.revenue_items or [],
        "cost_items": assessment.cost_items or [],
        "family_labor_items": assessment.family_labor_items or [],
        "hired_labor_items": assessment.hired_labor_items or [],
        "food_security_items": assessment.food_security_items or [],
        "notes": assessment.notes,
        "total_revenue_cfa": assessment.total_revenue_cfa,
        "total_cost_cfa": assessment.total_cost_cfa,
        "profit_cfa": assessment.profit_cfa,
        "family_labor_days": assessment.family_labor_days,
        "hired_labor_days": assessment.hired_labor_days,
        "return_per_family_day_cfa": assessment.return_per_family_day_cfa,
        "created_at": assessment.created_at,
        "updated_at": assessment.updated_at,
    }


def _create_assessment_from_payload(data: FarmForcePayload, db: Session) -> FarmForceAssessment:
    producer = db.query(Producer).filter(Producer.id == data.producer_id, Producer.is_active == True).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur non trouve.")
    totals = _calculate(data)
    assessment = FarmForceAssessment(
        producer_id=data.producer_id,
        campagne_id=data.campagne_id,
        campaign_label=data.campaign_label,
        localite=data.localite or producer.localite,
        pr_code=data.pr_code or producer.code_yeyasso,
        household_members=data.household_members,
        parcels=data.parcels,
        revenue_items=data.revenue_items,
        cost_items=data.cost_items,
        family_labor_items=data.family_labor_items,
        hired_labor_items=data.hired_labor_items,
        food_security_items=data.food_security_items,
        notes=data.notes,
        **totals,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/summary")
def farmforce_summary(db: Session = Depends(get_db)):
    count = db.query(func.count(FarmForceAssessment.id)).scalar() or 0
    totals = db.query(
        func.coalesce(func.sum(FarmForceAssessment.total_revenue_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.total_cost_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.profit_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.family_labor_days), 0),
    ).one()
    avg_return = db.query(func.avg(FarmForceAssessment.return_per_family_day_cfa)).scalar()
    return {
        "assessments": count,
        "total_revenue_cfa": float(totals[0] or 0),
        "total_cost_cfa": float(totals[1] or 0),
        "profit_cfa": float(totals[2] or 0),
        "family_labor_days": float(totals[3] or 0),
        "average_return_per_family_day_cfa": round(float(avg_return), 2) if avg_return is not None else None,
    }


@router.get("/assessments", response_model=list[FarmForceResponse])
def list_assessments(
    producer_id: Optional[int] = None,
    campaign_label: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(FarmForceAssessment)
    if producer_id:
        query = query.filter(FarmForceAssessment.producer_id == producer_id)
    if campaign_label:
        query = query.filter(FarmForceAssessment.campaign_label == campaign_label)
    rows = query.order_by(FarmForceAssessment.created_at.desc()).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/assessments/{assessment_id}", response_model=FarmForceResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(FarmForceAssessment).filter(FarmForceAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Evaluation FarmForce introuvable.")
    return _serialize(assessment)


@router.post("/assessments", response_model=FarmForceResponse)
def create_assessment(data: FarmForcePayload, db: Session = Depends(get_db)):
    assessment = _create_assessment_from_payload(data, db)
    return _serialize(assessment)


@router.post("/import/excel")
async def import_farmforce_excel(
    file: UploadFile = File(...),
    producer_id: Optional[int] = Query(None),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Importe l'outil Excel Fairtrade FarmForce.

    - dry_run=true : parse et renvoie les donnees detectees.
    - dry_run=false : cree une evaluation FarmForce. Le producteur est trouve
      par producer_id si fourni, sinon par code interne dans l'onglet profil.
    """
    filename = file.filename or "farmforce.xlsx"
    if not filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="Format non supporte. Fournissez un fichier Excel.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier FarmForce trop volumineux.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        parsed = parse_farmforce_excel(tmp_path, filename=filename)
        if parsed.errors:
            return {"status": "error", "errors": parsed.errors}

        payload = parsed.as_payload()
        if producer_id:
            payload["producer_id"] = producer_id
        elif parsed.producer_code:
            producer = db.query(Producer).filter(Producer.code_yeyasso == parsed.producer_code).first()
            if producer:
                payload["producer_id"] = producer.id

        preview = {
            "producer_code": parsed.producer_code,
            "producer_name": parsed.producer_name,
            "campaign_label": parsed.campaign_label,
            "counts": {
                "household_members": len(parsed.household_members),
                "parcels": len(parsed.parcels),
                "revenue_items": len(parsed.revenue_items),
                "cost_items": len(parsed.cost_items),
                "family_labor_items": len(parsed.family_labor_items),
                "hired_labor_items": len(parsed.hired_labor_items),
                "household_expenses": len(parsed.household_expenses),
                "consent_records": len(parsed.consent_records),
            },
            "summary": parsed.summary,
            "warnings": parsed.warnings,
            "payload": payload,
        }

        if dry_run:
            return {"status": "preview", **preview}
        if not payload.get("producer_id"):
            raise HTTPException(
                status_code=400,
                detail="Producteur introuvable. Fournissez producer_id ou renseignez le code interne dans l'Excel.",
            )
        assessment = _create_assessment_from_payload(FarmForcePayload(**payload), db)
        return {"status": "success", "assessment": _serialize(assessment), "preview": preview}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
