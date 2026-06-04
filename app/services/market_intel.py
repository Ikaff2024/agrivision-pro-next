"""
Veille Marché Cacao — données de marché via Claude (recherche web), CÔTÉ SERVEUR.

Principes (corrigent la version client-side prototype) :
- l'appel Claude se fait sur le SERVEUR : la clé n'est jamais exposée au navigateur ;
- cache PARTAGÉ en mémoire (les données marché sont globales, pas par coopérative) →
  coût borné à ~1 appel/heure pour toute la plateforme ;
- coût tracé via AiUsage (par l'endpoint) ;
- dégradation GRACIEUSE si ANTHROPIC_API_KEY absente (pas de 500, pas de faux prix) ;
- le prix bord-champ CCC vient de la CONFIG (valeur officielle fiable), pas du LLM ;
  les cours Londres/NY sont marqués « indicatifs ».
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("agrivision")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

# Cache process partagé (suffit pour 1 worker ; sinon 1 appel par worker/heure).
_CACHE: dict = {"ts": 0.0, "data": None}


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("MARKET_CACHE_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600


def _ccc_price() -> dict:
    """Prix bord-champ officiel CCC (config) — valeur fiable, pas devinée par le LLM."""
    try:
        val = float(os.getenv("CCC_FARMGATE_PRICE_FCFA", "2800"))
    except ValueError:
        val = 2800.0
    return {
        "fcfa_kg": val,
        "note": os.getenv("CCC_FARMGATE_NOTE", "Campagne 2025-2026 — prix bord-champ officiel CCC"),
    }


_SYSTEM_PROMPT = (
    "Tu es un analyste du marché mondial du cacao. Réponds UNIQUEMENT par un JSON "
    "valide, sans aucun texte ni backticks autour. Format STRICT :\n"
    '{"london":"XXXX $/t","london_change":"+X.X%","london_up":true,'
    '"ny":"XXXX $/t","ny_change":"-X.X%","ny_up":false,'
    '"news":[{"title":"...","source":"...","date":"il y a X jours",'
    '"cat":"EUDR|Marché|Santé|Politique|Autre","summary":"1 phrase"}],'
    '"ai_summary":"2-3 phrases stratégiques pour des coopératives ivoiriennes."}\n'
    "Inclure 6 à 8 actualités récentes et variées (prix, EUDR, maladies CSSVD, "
    "politique de la filière CCC, exportateurs)."
)

_USER_PROMPT = (
    "Donne les cours futures du cacao à Londres (LME) et New York (ICE) actuels avec "
    "leur variation, 6 à 8 actualités récentes (EUDR, marchés, CSSVD, politique CCC), "
    "et une synthèse stratégique pour des coopératives ivoiriennes."
)


async def _call_claude_market() -> tuple[Optional[dict], Optional[dict]]:
    """Appelle Claude (web search) et renvoie (parsed_json, usage) ou (None, None)."""
    if not ANTHROPIC_API_KEY:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 1800,
                    "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    "system": _SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": _USER_PROMPT}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            logger.warning("Veille marché : pas de JSON dans la réponse Claude.")
            return None, None
        parsed = json.loads(match.group(0))
        usage_raw = data.get("usage") or {}
        usage = {
            "model": data.get("model", CLAUDE_MODEL),
            "input_tokens": int(usage_raw.get("input_tokens", 0) or 0),
            "output_tokens": int(usage_raw.get("output_tokens", 0) or 0),
        }
        return parsed, usage
    except Exception as e:  # noqa: BLE001 — best-effort, jamais de 500
        logger.warning("Veille marché : appel Claude échoué : %s", e)
        return None, None


def _fallback(reason: str) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live": False,
        "cached": False,
        "prices": {"ccc": _ccc_price(), "london": None, "ny": None, "indicative": True},
        "news": [],
        "ai_summary": None,
        "note": reason,
    }


def _build(parsed: dict) -> dict:
    news = parsed.get("news")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live": True,
        "cached": False,
        "prices": {
            "ccc": _ccc_price(),
            "london": {"value": parsed.get("london"), "change": parsed.get("london_change"),
                       "up": parsed.get("london_up", True)},
            "ny": {"value": parsed.get("ny"), "change": parsed.get("ny_change"),
                   "up": parsed.get("ny_up", True)},
            "indicative": True,  # cours mondiaux indicatifs (pas un flux officiel)
        },
        "news": news if isinstance(news, list) else [],
        "ai_summary": parsed.get("ai_summary"),
        "note": None,
    }


async def get_market_intelligence(force: bool = False) -> tuple[dict, Optional[dict]]:
    """Renvoie (data, usage). `usage` non-None UNIQUEMENT si un appel Claude a eu lieu
    (pour le suivi de coût). Sert le cache partagé tant qu'il est frais."""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _ttl_seconds():
        cached = dict(_CACHE["data"])
        cached["cached"] = True
        return cached, None

    parsed, usage = await _call_claude_market()
    if parsed is None:
        # Pas de données fraîches : servir le cache périmé s'il existe, sinon fallback.
        if _CACHE["data"] is not None:
            stale = dict(_CACHE["data"])
            stale["cached"] = True
            stale["stale"] = True
            return stale, None
        return _fallback(
            "Données de marché momentanément indisponibles "
            "(service IA non configuré ou injoignable)."
        ), None

    data = _build(parsed)
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data, usage
