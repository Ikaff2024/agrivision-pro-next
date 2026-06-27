"""Réglages plateforme (niveau propriétaire IKAFFANAN LTD).

Stockage clé→valeur en base (`PlatformSetting`) pour modifier au runtime des
paramètres globaux SANS redéploiement ni accès aux variables d'environnement.

Cas d'usage principal : choisir le **fournisseur IA** (Anthropic, DeepSeek, Qwen,
OpenAI, OpenRouter, open-weights, local) et le **modèle** du Conseil agronomique
depuis l'UI propriétaire.

⚠️ On ne stocke JAMAIS de secret ici : les clés API restent en variables
d'environnement serveur. Ce module ne gère que le *choix* du fournisseur/modèle.
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import PlatformSetting

AI_PROVIDER_KEY = "ai_provider"
AI_MODEL_KEY = "ai_model"

# Libellés lisibles pour l'UI (id technique -> nom affiché).
_PROVIDER_LABELS = {
    "anthropic": "Claude (Anthropic)",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Alibaba)",
    "openai": "OpenAI",
    "openrouter": "OpenRouter (multi-modèles)",
    "openweights": "Open-weights (hébergé)",
    "local": "Local (Ollama / vLLM)",
}


def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    return row.value if (row and row.value is not None) else default


def set_setting(db: Session, key: str, value: Optional[str]) -> None:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=key, value=value))
    db.commit()


def resolve_ai_config(db: Session) -> tuple[str, str]:
    """(provider, model) effectifs : override base si présent, sinon variables d'env.

    `model` vide → le fournisseur utilisera son modèle par défaut (preset / env).
    """
    from app.ai_advisor import AI_PROVIDER
    provider = (get_setting(db, AI_PROVIDER_KEY) or AI_PROVIDER or "anthropic").strip().lower()
    model = (get_setting(db, AI_MODEL_KEY) or "").strip()
    return provider, model


def available_providers() -> list[dict]:
    """Liste des fournisseurs IA disponibles + état de configuration (clé/URL).

    `ready` = le fournisseur peut être utilisé tel quel (clé + URL présentes).
    Sert à l'UI propriétaire pour signaler ce qui est prêt à l'emploi.
    """
    from app.ai_advisor import _OPENAI_PRESETS, ANTHROPIC_API_KEY, CLAUDE_MODEL

    out = [{
        "id": "anthropic",
        "label": _PROVIDER_LABELS["anthropic"],
        "default_model": CLAUDE_MODEL,
        "key_env": "ANTHROPIC_API_KEY",
        "ready": bool(ANTHROPIC_API_KEY),
        "needs_base_url": False,
    }]
    generic_base = os.getenv("AI_OPENAI_BASE_URL") or ""
    generic_key = os.getenv("AI_OPENAI_API_KEY") or ""
    for pid, (base, model, key_env) in _OPENAI_PRESETS.items():
        base_url = generic_base or base
        api_key = generic_key or (os.getenv(key_env) or "")
        out.append({
            "id": pid,
            "label": _PROVIDER_LABELS.get(pid, pid),
            "default_model": model,
            "key_env": key_env,
            "ready": bool(base_url and api_key),
            "needs_base_url": not base,  # openweights : base_url à fournir via env
        })
    return out


def valid_provider_ids() -> set[str]:
    return {"anthropic"} | {p["id"] for p in available_providers()}
