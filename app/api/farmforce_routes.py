from datetime import datetime
import os
import tempfile
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.auth_service import decode_token, get_current_user
from app.db.database import get_db
from app.db.models import FarmForceAssessment, Producer, User
from app.importers.farmforce_excel import parse_farmforce_excel
from app.services.farmforce_reports import (
    build_farmforce_context,
    farmforce_filename,
    generate_farmforce_pdf,
)

router = APIRouter(prefix="/farmforce", tags=["FarmForce"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_optional_bearer = HTTPBearer(auto_error=False)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        return None
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    return user if (user and user.is_active) else None


def _coop_producer_subq(db: Session, cooperative_id: int | None):
    """Sous-requete des producteurs d'une coop (None => global)."""
    if cooperative_id is None:
        return None
    return db.query(Producer.id).filter(Producer.cooperative_id == cooperative_id).subquery()

# Verdict revenu vital : helper partage (defini dans le service pour eviter
# un import circulaire routes <-> reports).
from app.services.farmforce_reports import living_income_assessment as _living_income  # noqa: E402


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
    household_expense_items: list[dict] = Field(default_factory=list)
    notes: Optional[str] = None


class FarmForceResponse(FarmForcePayload):
    id: int
    producer_name: str
    total_revenue_cfa: float
    total_cost_cfa: float
    profit_cfa: float
    total_household_expenses_cfa: float = 0
    net_income_cfa: float = 0
    living_income_benchmark_cfa: Optional[float] = None
    living_income_gap_cfa: Optional[float] = None
    living_income_pct: Optional[float] = None
    living_income_status: Optional[str] = None
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
    household_expenses = sum(
        _number(item.get("amount_cfa") or item.get("cost_cfa") or item.get("montant_cfa"))
        for item in data.household_expense_items
    )
    net_income = profit - household_expenses
    return {
        "total_revenue_cfa": round(total_revenue, 2),
        "total_cost_cfa": round(total_cost, 2),
        "profit_cfa": round(profit, 2),
        "total_household_expenses_cfa": round(household_expenses, 2),
        "net_income_cfa": round(net_income, 2),
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
        "household_expense_items": assessment.household_expense_items or [],
        "notes": assessment.notes,
        "total_revenue_cfa": assessment.total_revenue_cfa,
        "total_cost_cfa": assessment.total_cost_cfa,
        "profit_cfa": assessment.profit_cfa,
        "total_household_expenses_cfa": assessment.total_household_expenses_cfa or 0,
        "net_income_cfa": assessment.net_income_cfa or 0,
        **_living_income(assessment.net_income_cfa or 0),
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
        household_expense_items=data.household_expense_items,
        notes=data.notes,
        **totals,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/summary")
def farmforce_summary(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _coop_producer_subq(db, coop_id)
    ff_filter = [FarmForceAssessment.producer_id.in_(prod_subq)] if prod_subq is not None else []
    count = db.query(func.count(FarmForceAssessment.id)).filter(*ff_filter).scalar() or 0
    totals = db.query(
        func.coalesce(func.sum(FarmForceAssessment.total_revenue_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.total_cost_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.profit_cfa), 0),
        func.coalesce(func.sum(FarmForceAssessment.family_labor_days), 0),
    ).filter(*ff_filter).one()
    avg_return = db.query(func.avg(FarmForceAssessment.return_per_family_day_cfa)).filter(*ff_filter).scalar()
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
    current_user: User | None = Depends(get_optional_current_user),
):
    query = db.query(FarmForceAssessment)
    if producer_id:
        query = query.filter(FarmForceAssessment.producer_id == producer_id)
    if campaign_label:
        query = query.filter(FarmForceAssessment.campaign_label == campaign_label)
    coop_id = current_user.cooperative_id if current_user else None
    prod_subq = _coop_producer_subq(db, coop_id)
    if prod_subq is not None:
        query = query.filter(FarmForceAssessment.producer_id.in_(prod_subq))
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


@router.put("/assessments/{assessment_id}", response_model=FarmForceResponse)
def update_assessment(assessment_id: int, data: FarmForcePayload, db: Session = Depends(get_db)):
    """Met a jour un livret FarmForce existant (reprise / correction de saisie).

    Toutes les sections et totaux sont recalcules a partir du payload fourni.
    """
    assessment = db.query(FarmForceAssessment).filter(FarmForceAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Evaluation FarmForce introuvable.")
    producer = db.query(Producer).filter(Producer.id == data.producer_id, Producer.is_active == True).first()
    if not producer:
        raise HTTPException(status_code=404, detail="Producteur non trouve.")

    totals = _calculate(data)
    assessment.producer_id = data.producer_id
    assessment.campagne_id = data.campagne_id
    assessment.campaign_label = data.campaign_label
    assessment.localite = data.localite or producer.localite
    assessment.pr_code = data.pr_code or producer.code_yeyasso
    assessment.household_members = data.household_members
    assessment.parcels = data.parcels
    assessment.revenue_items = data.revenue_items
    assessment.cost_items = data.cost_items
    assessment.family_labor_items = data.family_labor_items
    assessment.hired_labor_items = data.hired_labor_items
    assessment.food_security_items = data.food_security_items
    assessment.household_expense_items = data.household_expense_items
    assessment.notes = data.notes
    for key, value in totals.items():
        setattr(assessment, key, value)

    db.commit()
    db.refresh(assessment)
    return _serialize(assessment)


@router.get("/assessments/{assessment_id}/livret.pdf")
def download_farmforce_livret(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telecharge le Livret de suivi (DD farm records) rempli au format PDF."""
    assessment = db.query(FarmForceAssessment).filter(FarmForceAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Evaluation FarmForce introuvable.")
    producer = db.query(Producer).filter(Producer.id == assessment.producer_id).first()
    if not producer or producer.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=404, detail="Evaluation FarmForce introuvable.")
    context = build_farmforce_context(assessment)
    pdf_bytes = generate_farmforce_pdf(context)
    filename = farmforce_filename(assessment)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


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
