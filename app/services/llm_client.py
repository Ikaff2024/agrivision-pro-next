"""Client LLM partagé (synchrone) — alimenté par le sélecteur de fournisseur.

UN SEUL point d'accès LLM pour toute la plateforme : il résout le fournisseur et
le modèle via le choix runtime du propriétaire (`PlatformSetting`) puis, à défaut,
via les variables d'environnement (`AI_PROVIDER` + presets `_OPENAI_PRESETS`).

Conséquence : configurer/choisir un fournisseur **une seule fois** alimente à la
fois le Conseil agronomique ET le moteur de veille. Le moteur de veille est ainsi
**agnostique de Claude** (il tourne sur n'importe quel fournisseur compatible
OpenAI : DeepSeek, Qwen, OpenRouter, open-weights, local…) tout en restant
**alimenté par les mêmes fournisseurs** que le reste de la plateforme.

Synchrone (httpx) car appelé depuis des routes/synthèses synchrones (veille).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from sqlalchemy.orm import Session


class LLMNotConfigured(RuntimeError):
    """Le fournisseur résolu n'a pas de clé/URL/modèle exploitable."""


def resolve(db: Optional[Session]) -> tuple[str, str]:
    """(provider, model) effectifs : choix propriétaire (base) puis env."""
    from app.ai_advisor import AI_PROVIDER
    if db is not None:
        from app.services.platform_settings import resolve_ai_config
        return resolve_ai_config(db)
    return (AI_PROVIDER or "anthropic").strip().lower(), (os.getenv("AI_OPENAI_MODEL") or "").strip()


def chat(db: Optional[Session], prompt: str, *, max_tokens: int = 1200,
         temperature: float = 0.2) -> dict:
    """Complétion via le fournisseur sélectionné. Renvoie {"text", "model"}.

    Lève ``LLMNotConfigured`` si le fournisseur n'est pas exploitable (clé/URL
    manquante) — pas de repli silencieux d'un fournisseur vers un autre.
    """
    provider, model = resolve(db)
    if provider in ("anthropic", "claude", ""):
        return _anthropic_chat(prompt, model, max_tokens)
    return _openai_compatible_chat(provider, model, prompt, max_tokens, temperature)


def _anthropic_chat(prompt: str, model: str, max_tokens: int) -> dict:
    from app.ai_advisor import ANTHROPIC_API_KEY, CLAUDE_API_URL, CLAUDE_MODEL
    if not ANTHROPIC_API_KEY:
        raise LLMNotConfigured("Fournisseur Anthropic non configuré (ANTHROPIC_API_KEY manquante).")
    used_model = (model or "").strip() or CLAUDE_MODEL
    r = httpx.post(
        CLAUDE_API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": used_model, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()
    text = ((data.get("content") or [{}])[0].get("text") or "")
    return {"text": text, "model": data.get("model", used_model)}


def _openai_compatible_chat(provider: str, model: str, prompt: str,
                            max_tokens: int, temperature: float) -> dict:
    from app.ai_advisor import _OPENAI_PRESETS
    preset = _OPENAI_PRESETS.get(provider)
    base_url = (os.getenv("AI_OPENAI_BASE_URL") or (preset[0] if preset else "")).rstrip("/")
    used_model = (model or "").strip() or os.getenv("AI_OPENAI_MODEL") or (preset[1] if preset else "")
    api_key = os.getenv("AI_OPENAI_API_KEY") or (os.getenv(preset[2]) if preset else "") or ""
    if not (base_url and used_model and api_key):
        raise LLMNotConfigured(
            f"Fournisseur IA '{provider}' non configuré (base_url/clé/modèle manquant). "
            f"Définissez la clé du fournisseur (et AI_OPENAI_BASE_URL pour open-weights) côté serveur."
        )
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL") or "https://agrivision.pro"
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME") or "AgriVision Pro"
    r = httpx.post(
        base_url + "/chat/completions",
        headers=headers,
        json={"model": used_model, "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature, "max_tokens": max_tokens, "stream": False},
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return {"text": text, "model": data.get("model", used_model)}
