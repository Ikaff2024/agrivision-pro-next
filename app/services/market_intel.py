"""
Veille Marché Cacao — données de marché, CÔTÉ SERVEUR.

Deux sources, découplées :
- PRIX : cours réel du cacao ICE New York (benchmark mondial USD) via une source
  publique gratuite — NE dépend PAS de la clé IA, donc fonctionne toujours.
  Le prix bord-champ CCC vient de la config (officiel). Londres = estimation IA.
- ACTUALITÉS + SYNTHÈSE : Claude avec recherche web (nécessite ANTHROPIC_API_KEY +
  web search activé sur le compte). Inclut explicitement les événements/conférences.

Principes : clé jamais exposée au navigateur, cache PARTAGÉ (coût borné), coût
tracé via AiUsage (par l'endpoint), dégradation gracieuse (aucun 500, aucun faux prix).
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

# Cours réel ICE New York (cacao, USD/tonne) — source publique gratuite.
NY_COCOA_URL = "https://query1.finance.yahoo.com/v8/finance/chart/CC=F?interval=1d&range=1d"

# Cache process partagé (données marché globales, pas par coopérative).
_CACHE: dict = {"ts": 0.0, "data": None}


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("MARKET_CACHE_TTL_SECONDS", "1800"))  # 30 min
    except ValueError:
        return 1800


_CITE_RE = re.compile(r"</?cite[^>]*>")


def _clean(text):
    """Retire les balises de citation <cite ...> injectées par la recherche web."""
    if not isinstance(text, str):
        return text
    return _CITE_RE.sub("", text).strip()


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


async def _fetch_ny_cocoa() -> Optional[dict]:
    """Cours RÉEL (temps différé) du cacao ICE New York via une source publique.

    Best-effort : renvoie None en cas d'échec (jamais d'exception). Indépendant
    de la clé IA → le prix de référence s'affiche même sans configuration IA.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(NY_COCOA_URL, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            results = (r.json().get("chart", {}) or {}).get("result") or []
        meta = (results[0] or {}).get("meta", {}) if results else {}
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if not price:
            return None
        change_pct = ((price - prev) / prev * 100.0) if prev else None
        cur = meta.get("currency", "USD")
        unit = "$" if cur == "USD" else cur
        return {
            "value": f"{price:,.0f} {unit}/t".replace(",", " "),
            "change": (f"{change_pct:+.1f}%" if change_pct is not None else None),
            "up": (change_pct is None or change_pct >= 0),
            "source": "ICE New York · temps différé",
            "indicative": False,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("Cours cacao NY indisponible : %s", e)
        return None


_SYSTEM_PROMPT = (
    "Tu es un analyste de la filière cacao ouest-africaine. Réponds UNIQUEMENT par un "
    "JSON valide, sans aucun texte ni backticks autour. Format STRICT :\n"
    '{"london":"XXXX £/t","london_change":"+X.X%","london_up":true,'
    '"news":[{"title":"...","source":"...","date":"il y a X jours ou date",'
    '"cat":"EUDR|Marché|Santé|Politique|Événement|Autre","summary":"1 phrase"}],'
    '"ai_summary":"2-3 phrases stratégiques pour des coopératives ivoiriennes."}\n'
    "Inclure 6 à 8 actualités récentes et VARIÉES : prix/marché, EUDR, maladies (CSSVD), "
    "politique de la filière (CCC), ET notamment les ÉVÉNEMENTS À VENIR pertinents pour "
    "un gérant de coopérative (conférences, salons, forums, ateliers, missions, foires "
    "agricoles) en Côte d'Ivoire et dans la filière cacao — avec dates et lieux si connus "
    '(catégorie "Événement").'
)

_USER_PROMPT = (
    "Donne le cours futures du cacao à Londres (LME/ICE) avec sa variation, 6 à 8 "
    "actualités récentes (marchés, EUDR, CSSVD, politique CCC) ET les événements/"
    "conférences/salons à venir dans la filière cacao en Côte d'Ivoire, plus une synthèse "
    "stratégique pour des coopératives ivoiriennes."
)


async def _call_claude_market() -> tuple[Optional[dict], Optional[dict]]:
    """Appelle Claude (web search) → (parsed_json, usage) ou (None, None)."""
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
    except Exception as e:  # noqa: BLE001
        logger.warning("Veille marché : appel Claude échoué : %s", e)
        return None, None


def _build(ny: Optional[dict], parsed: Optional[dict]) -> dict:
    parsed = parsed or {}

    # Londres : estimation IA (pas de flux officiel branché) → marqué indicatif.
    london = None
    if parsed.get("london"):
        london = {
            "value": parsed.get("london"), "change": parsed.get("london_change"),
            "up": parsed.get("london_up", True), "source": "estimation IA", "indicative": True,
        }
    # NY : prix réel si dispo, sinon estimation IA en repli.
    ny_block = ny
    if ny_block is None and parsed.get("ny"):
        ny_block = {
            "value": parsed.get("ny"), "change": parsed.get("ny_change"),
            "up": parsed.get("ny_up", True), "source": "estimation IA", "indicative": True,
        }

    raw_news = parsed.get("news") if isinstance(parsed.get("news"), list) else []
    news = [
        {**n, "title": _clean(n.get("title")), "summary": _clean(n.get("summary"))}
        for n in raw_news if isinstance(n, dict)
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live": bool(parsed),  # actualités + synthèse présentes
        "cached": False,
        "prices": {"ccc": _ccc_price(), "ny": ny_block, "london": london},
        "news": news,
        "ai_summary": _clean(parsed.get("ai_summary")),
        "note": None if parsed else (
            "Actualités et synthèse IA momentanément indisponibles "
            "(service IA non configuré ou injoignable). Les prix restent à jour."
        ),
    }


async def get_market_intelligence(force: bool = False) -> tuple[dict, Optional[dict]]:
    """Renvoie (data, usage). `usage` non-None UNIQUEMENT si un appel Claude facturé
    a eu lieu. Sert le cache partagé tant qu'il est frais."""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _ttl_seconds():
        cached = dict(_CACHE["data"])
        cached["cached"] = True
        return cached, None

    ny = await _fetch_ny_cocoa()                 # réel, sans clé
    parsed, usage = await _call_claude_market()  # actus + synthèse (clé requise)

    if ny is None and parsed is None:
        # Rien de neuf : servir le cache (même périmé) s'il existe.
        if _CACHE["data"] is not None:
            stale = dict(_CACHE["data"])
            stale["cached"] = True
            stale["stale"] = True
            return stale, None
        return _build(None, None), None  # CCC + message, non mis en cache

    data = _build(ny, parsed)
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data, usage
