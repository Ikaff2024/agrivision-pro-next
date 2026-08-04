"""Endpoints veille — moteur IA agnostique (open-source). cf. docs/PLAN_MOTEUR_IA_AGNOSTIQUE.md

- POST /veille/ingest  (admin)  : récupère les sources (RSS/Atom) → items. Pas de LLM.
- GET  /veille/items            : items récents (lecture, tout rôle authentifié).
- POST /veille/digest  (admin)  : synthèse OPEN-SOURCE des items récents → digest stocké.
- GET  /veille/digest           : dernier digest (lecture).

Veille **globale** (partagée, pas de scope coopérative, comme le cache marché). La
génération (LLM) est réservée admin (coût). N'altère pas la veille marché existante.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, VeilleItem, VeilleDigest
from app.auth.auth_service import get_current_user
from app.services import veille_engine

router = APIRouter(prefix="/veille", tags=["veille"])


def _item_dict(it: VeilleItem) -> dict:
    return {
        "id": it.id,
        "source_key": it.source_key,
        "source_name": it.source_name,
        "title": it.title,
        "url": it.url,
        "summary": it.summary,
        "topics": it.topics or [],
        "published_at": it.published_at.isoformat() if it.published_at else None,
        "fetched_at": it.fetched_at.isoformat() if it.fetched_at else None,
    }


def _digest_dict(dg: VeilleDigest) -> dict:
    return {
        "id": dg.id,
        "topic": dg.topic,
        "model": dg.model,
        "item_count": dg.item_count,
        "generated_at": dg.generated_at.isoformat() if dg.generated_at else None,
        "payload": dg.payload,
    }


@router.post("/ingest")
def veille_ingest(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Récupère les sources de veille (RSS/Atom) et stocke les nouveaux items. ADMIN."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Ingestion veille réservée à l'administrateur.")
    return veille_engine.ingest(db)


@router.get("/items")
def veille_items(
    topic: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=200),
    max_age_days: Optional[int] = Query(
        None, ge=1, le=1825,
        description="Ne garder que les items publiés (à défaut récupérés) dans les N derniers jours.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Filtre d'âge : on récupère large puis on borne, pour rester au niveau `limit`.
    items = veille_engine.retrieve(db, topics=[topic] if topic else None, limit=200 if max_age_days else limit)
    if max_age_days and max_age_days > 0:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        def _item_dt(it):
            dt = it.published_at or it.fetched_at
            if dt is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        items = [it for it in items if (_item_dt(it) or cutoff) >= cutoff][:limit]
    return {"count": len(items), "items": [_item_dict(it) for it in items]}


@router.post("/digest")
def veille_make_digest(
    topic: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Génère une synthèse OPEN-SOURCE des items récents et la stocke. ADMIN.
    Renvoie 502 (clair) si le modèle open n'est pas configuré (pas de repli Claude)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Synthèse veille réservée à l'administrateur.")
    items = veille_engine.retrieve(db, topics=[topic] if topic else None)
    try:
        # db transmis → la synthèse utilise le fournisseur choisi par le propriétaire
        # (sélecteur IA), sinon les variables d'env. Moteur agnostique de Claude.
        result = veille_engine.synthesize(items, db=db)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(e).__name__}.")
        raise
    dg = VeilleDigest(topic=topic, payload=result, model=result.get("model"), item_count=len(items))
    db.add(dg)
    db.commit()
    db.refresh(dg)
    return _digest_dict(dg)


@router.get("/digest")
def veille_latest_digest(
    topic: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(VeilleDigest)
    if topic:
        q = q.filter(VeilleDigest.topic == topic)
    dg = q.order_by(VeilleDigest.generated_at.desc()).first()
    return {"digest": _digest_dict(dg) if dg else None}
