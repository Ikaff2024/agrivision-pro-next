"""Assistant « mes données » — Q&A en langage naturel ANCRÉ sur un instantané.

Sécurité : le LLM ne génère JAMAIS de requête SQL. On construit côté serveur un
instantané COMPACT et CLOISONNÉ par coopérative (réutilise les agrégats existants :
KPI direction, couverture certification + listes ciblées), puis le fournisseur
sélectionné (OpenRouter…) répond UNIQUEMENT à partir de cet instantané.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, Producer, User

router = APIRouter(tags=["Assistant IA"])

# Aligné sur le tableau de bord direction (qui alimente l'instantané).
_ALLOWED = {"admin", "agronomist"}
_CAP = 60  # bornage des listes d'entités dans l'instantané


class AssistantQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


def _build_snapshot(db: Session, current_user: User) -> dict:
    """Instantané compact et cloisonné des données de la coopérative."""
    from app.api.dashboard_routes import direction_dashboard
    from app.api.certification_routes import certification_coverage

    kpis = direction_dashboard(db, current_user)          # périmètre, EUDR, social, revenu vital, volumes
    coverage = certification_coverage(db, current_user)   # couverture par standard

    coop_id = current_user.cooperative_id
    pq = db.query(Plantation)
    if coop_id is not None:
        pq = pq.filter(Plantation.cooperative_id == coop_id)

    non_conf = [
        {"parcelle": p.name, "region": p.region}
        for p in pq.filter(Plantation.eudr_status == "non_conforme").limit(_CAP).all()
    ]
    a_verifier = [
        {"parcelle": p.name, "region": p.region}
        for p in pq.filter(Plantation.eudr_status == "a_verifier").limit(_CAP).all()
    ]

    # Producteurs sous blocage social actif (CacaoGuard).
    blocked = []
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
        bq = (
            db.query(Producer.nom_complet, TraceabilityBlock.block_reason)
            .join(TraceabilityBlock, TraceabilityBlock.producer_id == Producer.id)
            .filter(TraceabilityBlock.status == BlockStatus.ACTIVE)
        )
        if coop_id is not None:
            bq = bq.filter(Producer.cooperative_id == coop_id)
        blocked = [
            {"producteur": nom, "motif": getattr(r, "value", str(r)) if r else None}
            for nom, r in bq.limit(_CAP).all()
        ]
    except ImportError:
        pass

    return {
        "perimetre": kpis.get("perimeter"),
        "eudr": {
            **(kpis.get("eudr") or {}),
            "parcelles_non_conformes": non_conf,
            "parcelles_a_verifier": a_verifier,
            "note_listes": f"listes plafonnées à {_CAP} éléments" if len(non_conf) == _CAP else None,
        },
        "protection_enfant": {
            **(kpis.get("child_protection") or {}),
            "producteurs_sous_blocage": blocked,
        },
        "revenu_vital": kpis.get("living_income"),
        "volumes": kpis.get("volume"),
        "certification": coverage.get("certifications"),
        "alertes_ouvertes": (kpis.get("alerts") or {}).get("open"),
    }


@router.post("/assistant/ask")
def assistant_ask(
    data: AssistantQuestion,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Répond à une question en langage naturel à partir des données de la coopérative."""
    if current_user.role not in _ALLOWED:
        raise HTTPException(status_code=403, detail="Assistant réservé à la direction (admin/agronome).")

    snapshot = _build_snapshot(db, current_user)
    prompt = (
        "Tu es l'assistant data d'une coopérative de cacao en Côte d'Ivoire. "
        "Réponds à la QUESTION en français, de façon concise et chiffrée, en t'appuyant "
        "EXCLUSIVEMENT sur les DONNÉES JSON ci-dessous (déjà cloisonnées à cette coopérative). "
        "Si l'information n'y figure pas, dis-le clairement et n'invente aucun chiffre. "
        "Quand une liste est plafonnée, précise-le.\n\n"
        f"QUESTION : {data.question.strip()}\n\n"
        f"DONNÉES :\n{json.dumps(snapshot, ensure_ascii=False, default=str)}"
    )
    try:
        from app.services import llm_client
        out = llm_client.chat(db, prompt, max_tokens=600, temperature=0.2)
    except llm_client.LLMNotConfigured as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        import httpx as _httpx
        if isinstance(ex, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(ex).__name__}.")
        raise

    try:
        from app.db.models import AiUsage
        from app.services.ai_cost import compute_cost_usd
        it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
        db.add(AiUsage(
            cooperative_id=current_user.cooperative_id, user_id=current_user.id,
            plantation_id=None, feature="assistant",
            model=out.get("model", ""), input_tokens=it_, output_tokens=ot_,
            cost_usd=compute_cost_usd(it_, ot_, out.get("model")),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return {"answer": (out.get("text") or "").strip(), "model": out.get("model")}
