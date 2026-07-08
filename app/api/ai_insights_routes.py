"""Interprétation IA par module (Aya) + suggestions de formation.

Réutilise l'instantané COMPACT et CLOISONNÉ de l'assistant (`_build_snapshot`) et
le fournisseur LLM sélectionné (`llm_client.chat`). Deux garde-fous coût :
- réservé à la direction (admin/agronome/gestionnaire) ;
- **cache mémoire TTL + signature des données** : tant que les chiffres n'ont pas
  changé (et dans la fenêtre TTL), on ne rappelle pas le LLM (coût de revient maîtrisé).
"""
from __future__ import annotations

import hashlib
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/ai", tags=["Aya - insights IA"])

_INSIGHT_ROLES = {"admin", "agronomist", "gestionnaire"}
_CACHE_TTL_SECONDS = 6 * 3600  # 6 h : les KPI d'une coop bougent lentement
_cache: dict[str, dict] = {}   # clé -> {"ts", "sig", "payload"}

# Modules interprétables (libellé lisible pour le prompt).
_MODULES = {
    "direction": "tableau de bord Direction (vue 360° : EUDR, protection enfant, revenu vital, volumes, certification, alertes)",
    "eudr": "conformité EUDR (parcelles conformes / à vérifier / non conformes, polygones, déforestation)",
    "cacaoguard": "protection de l'enfant & conformité sociale (enfants à risque, blocages, alertes, suspicions SSRTE)",
    "agroforestry": "agroforesterie (ombrage, diversité, stock carbone estimé, conformité)",
    "farmforce": "revenu vital (ménages évalués, revenu vital atteint, revenu net moyen)",
    "volumes": "volumes & traçabilité (volume total, certifié, non tracé dont retenu pour cas social)",
}


class InterpretRequest(BaseModel):
    module: str = Field(..., min_length=2, max_length=40)


def _require(user: User):
    if user.role not in _INSIGHT_ROLES:
        raise HTTPException(status_code=403, detail="Interprétation IA réservée à la direction (admin/agronome/gestionnaire).")


def _module_extra(db: Session, user: User, module: str) -> dict:
    """Données SPÉCIFIQUES au module demandé, absentes de l'instantané générique.

    Sans ceci, Aya interprétait l'agroforesterie à partir d'un instantané qui ne
    contenait aucune donnée agroforestière -> elle répondait « pas de données »
    alors que la page en est pleine. On injecte donc le vrai bilan du module.
    """
    try:
        if module == "agroforestry":
            from app.api.routes import get_agroforestry_summary
            return {"agroforesterie": get_agroforestry_summary(db, user)}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _snapshot_json(db: Session, user: User, module: str | None = None) -> str:
    from app.api.assistant_routes import _build_snapshot
    payload: dict = {"coop": _build_snapshot(db, user)}
    if module:
        extra = _module_extra(db, user, module)
        if extra:
            payload["module_detail"] = extra
    return json.dumps(payload, ensure_ascii=False, default=str)


def _cache_get(key: str, sig: str):
    hit = _cache.get(key)
    if hit and hit["sig"] == sig and (time.time() - hit["ts"]) < _CACHE_TTL_SECONDS:
        return hit["payload"]
    return None


def _cache_put(key: str, sig: str, payload: dict):
    _cache[key] = {"ts": time.time(), "sig": sig, "payload": payload}


def _run_llm(db: Session, user: User, prompt: str, feature: str, max_tokens: int) -> dict:
    from app.services import llm_client
    try:
        out = llm_client.chat(db, prompt, max_tokens=max_tokens, temperature=0.2)
    except llm_client.LLMNotConfigured as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        import httpx as _httpx
        if isinstance(ex, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(ex).__name__}.")
        raise
    # Suivi de coût (comme l'assistant).
    try:
        from app.db.models import AiUsage
        from app.services.ai_cost import compute_cost_usd
        it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
        db.add(AiUsage(
            cooperative_id=user.cooperative_id, user_id=user.id, plantation_id=None,
            feature=feature, model=out.get("model", ""), input_tokens=it_, output_tokens=ot_,
            cost_usd=compute_cost_usd(it_, ot_, out.get("model")),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return {"text": (out.get("text") or "").strip(), "model": out.get("model")}


@router.post("/interpret")
def interpret_module(
    data: InterpretRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lecture en langage clair des chiffres d'un module + 3 actions prioritaires."""
    _require(current_user)
    module = data.module.strip().lower()
    if module not in _MODULES:
        raise HTTPException(status_code=400, detail=f"Module inconnu. Valeurs : {sorted(_MODULES)}.")

    snap = _snapshot_json(db, current_user, module)
    sig = hashlib.sha256((module + "|" + snap).encode("utf-8")).hexdigest()
    key = f"interpret:{current_user.cooperative_id}:{module}"
    cached = _cache_get(key, sig)
    if cached:
        return {**cached, "cached": True}

    prompt = (
        "Tu es Aya, l'assistante IA d'AgriVision Pro (cacao, Côte d'Ivoire). "
        f"Interprète pour un décideur de coopérative le module : {_MODULES[module]}.\n"
        "L'INSTANTANÉ contient les données générales de la coopérative sous « coop » ET, "
        "quand elles existent, les données PROPRES au module sous « module_detail » : "
        "concentre-toi en priorité sur « module_detail » pour ce module.\n"
        "À partir UNIQUEMENT de l'INSTANTANÉ (déjà cloisonné à cette coopérative), rends :\n"
        "1) « En bref » : 2-3 phrases de lecture claire des chiffres (pas de jargon) ;\n"
        "2) « Points d'attention » : 2-3 puces sur ce qui cloche ou est à surveiller ;\n"
        "3) « 3 actions prioritaires » : 3 puces concrètes et réalisables.\n"
        "N'invente AUCUN chiffre absent de l'instantané ; si une donnée manque, dis-le. "
        "Réponds en français, en Markdown concis.\n\n"
        f"INSTANTANÉ :\n{snap}"
    )
    result = _run_llm(db, current_user, prompt, feature=f"interpret:{module}", max_tokens=650)
    _cache_put(key, sig, result)
    return {**result, "cached": False}


@router.get("/training-suggestions")
def training_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aya propose des programmes de formation priorisés selon les risques de la coop."""
    _require(current_user)
    snap = _snapshot_json(db, current_user)
    sig = hashlib.sha256(("training|" + snap).encode("utf-8")).hexdigest()
    key = f"training:{current_user.cooperative_id}"
    cached = _cache_get(key, sig)
    if cached:
        return {**cached, "cached": True}

    prompt = (
        "Tu es Aya, l'assistante IA d'AgriVision Pro (cacao, Côte d'Ivoire). "
        "À partir UNIQUEMENT de l'INSTANTANÉ (cloisonné à cette coopérative), propose un "
        "PLAN DE FORMATION priorisé pour les producteurs et agents, adapté aux RISQUES réels "
        "de la coopérative (protection de l'enfant, agroforesterie, bonnes pratiques EUDR, "
        "revenu vital, qualité/récolte).\n"
        "Rends 3 à 5 MODULES DE FORMATION. Pour chacun : un titre, la raison (le chiffre/risque "
        "qui le justifie), le public cible, et la priorité (Haute/Moyenne). "
        "N'invente aucun chiffre absent de l'instantané. Réponds en français, en Markdown concis "
        "(un module = un titre en gras + 3 puces).\n\n"
        f"INSTANTANÉ :\n{snap}"
    )
    result = _run_llm(db, current_user, prompt, feature="training_suggestions", max_tokens=800)
    _cache_put(key, sig, result)
    return {**result, "cached": False}
