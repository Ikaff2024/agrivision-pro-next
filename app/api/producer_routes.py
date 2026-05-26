from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Producer

router = APIRouter(tags=["Producteurs"])


class ProducerResponse(BaseModel):
    id: int
    nom_complet: str
    code_yeyasso: Optional[str] = None
    telephone: Optional[str] = None
    localite: Optional[str] = None
    section: Optional[str] = None
    cooperative_id: Optional[int] = None

    class Config:
        from_attributes = True


@router.get("/producers", response_model=List[ProducerResponse])
def list_producers(
    limit: int = Query(500, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    search: Optional[str] = None,
    localite: Optional[str] = None,
    section: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Producer).filter(Producer.is_active == True)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            (Producer.nom_complet.ilike(like))
            | (Producer.code_yeyasso.ilike(like))
            | (Producer.telephone.ilike(like))
        )
    if localite:
        query = query.filter(Producer.localite == localite)
    if section:
        query = query.filter(Producer.section == section)

    return query.order_by(Producer.nom_complet.asc()).offset(skip).limit(limit).all()
