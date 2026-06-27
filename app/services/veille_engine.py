"""Moteur de veille agnostique (open-source) — pipeline RAG léger.

Indépendant de Claude : récupère des sources publiques (RSS/Atom) sur l'EUDR, le
cacao et la durabilité, les normalise / déduplique, puis laisse un modèle
**open-source** (via un endpoint OpenAI-compatible — VPS Ollama ou API hébergée)
en faire la **synthèse**. La synthèse ne s'appuie QUE sur les sources fournies
(anti-hallucination).

v1 : récupération par **récence + mots-clés** (les embeddings / pgvector sont en
Phase 2). N'altère PAS la veille marché existante (`market_intel`) — c'est additif.
cf. docs/PLAN_MOTEUR_IA_AGNOSTIQUE.md
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import VeilleItem, VeilleDigest

logger = logging.getLogger("agrivision.veille")

VEILLE_ENABLED = os.getenv("VEILLE_ENABLED", "").strip().lower() in ("1", "true", "yes")

def _gnews_url(query: str, hl: str = "fr", gl: str = "CI") -> str:
    """URL de recherche Google News RSS (gratuit, sans clé, stable) pour une
    requête mot-clé, localisée par langue (`hl`) et pays (`gl`). Permet de
    couvrir « toutes les news cacao » dans le monde ET en Côte d'Ivoire."""
    from urllib.parse import quote_plus
    lang = hl.split("-")[0]
    return (
        "https://news.google.com/rss/search?q=" + quote_plus(query)
        + f"&hl={hl}&gl={gl}&ceid={gl}:{lang}"
    )


# Registre de sources curées (cacao / EUDR / durabilité), RSS/Atom publics.
# ⚠️ Pipeline fail-soft par source : une source morte est ignorée + journalisée,
# sans casser l'ingestion. Élargissable sans toucher au code.
#
# Couverture cacao mondiale + Côte d'Ivoire assurée par des recherches Google
# News RSS (mot-clé + langue + pays) : c'est la façon la plus robuste de capter
# « toutes les news cacao » sans dépendre d'un RSS officiel (le Conseil du
# Café-Cacao n'en a pas de stable). Les institutionnels (UE/ICCO/certifs) restent
# pour la veille réglementaire.
VEILLE_SOURCES = [
    # ── Actualités CACAO — Côte d'Ivoire (FR) ────────────────────────────────
    {"key": "gnews_ci_cacao", "name": "Actualités cacao — Côte d'Ivoire",
     "url": _gnews_url("cacao Côte d'Ivoire", hl="fr", gl="CI"),
     "topics": ["cacao", "cote_ivoire", "marche"]},
    {"key": "gnews_ci_filiere", "name": "Filière cacao CI — prix & campagne",
     "url": _gnews_url("cacao (prix OR campagne OR Conseil Café Cacao OR producteurs)", hl="fr", gl="CI"),
     "topics": ["cacao", "cote_ivoire", "marche"]},
    # ── Actualités CACAO — Monde ─────────────────────────────────────────────
    {"key": "gnews_world_cocoa", "name": "Cocoa news — World",
     "url": _gnews_url("cocoa (market OR price OR production OR harvest)", hl="en-US", gl="US"),
     "topics": ["cacao", "monde", "marche"]},
    {"key": "gnews_world_cocoa_fr", "name": "Actualités cacao — Monde (FR)",
     "url": _gnews_url("cacao (marché mondial OR cours OR production)", hl="fr", gl="FR"),
     "topics": ["cacao", "monde", "marche"]},
    # ── Cacao & conformité (EUDR / déforestation / durabilité) ───────────────
    {"key": "gnews_cocoa_eudr", "name": "Cacao & EUDR / déforestation",
     "url": _gnews_url("cocoa (EUDR OR deforestation OR sustainability)", hl="en-US", gl="US"),
     "topics": ["cacao", "eudr", "monde"]},
    {"key": "gnews_cacao_eudr_fr", "name": "Cacao & EUDR (FR)",
     "url": _gnews_url("cacao (EUDR OR déforestation OR durabilité)", hl="fr", gl="FR"),
     "topics": ["cacao", "eudr", "reglementation"]},
    # ── Sources institutionnelles (veille réglementaire) ─────────────────────
    {"key": "eu_news", "name": "Commission européenne — presse",
     "url": "https://ec.europa.eu/commission/presscorner/api/rss?language=fr",
     "topics": ["eudr", "ue", "reglementation"]},
    {"key": "icco", "name": "ICCO — Organisation internationale du cacao",
     "url": "https://www.icco.org/feed/", "topics": ["cacao", "marche", "monde"]},
    {"key": "rainforest", "name": "Rainforest Alliance",
     "url": "https://www.rainforest-alliance.org/feed/", "topics": ["certification", "durabilite"]},
    {"key": "fairtrade", "name": "Fairtrade International",
     "url": "https://www.fairtrade.net/feed", "topics": ["certification", "durabilite"]},
]


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", "replace"))
    return h.hexdigest()


def normalize_entry(source: dict, entry) -> Optional[dict]:
    """Transforme une entrée brute (feedparser ou dict) en item normalisé.

    Renvoie None si inexploitable (pas de titre). Fonction PURE (testable).
    """
    get = entry.get if hasattr(entry, "get") else (lambda k, d=None: d)
    title = (get("title") or "").strip()
    if not title:
        return None
    url = (get("link") or "").strip()
    summary = (get("summary") or get("description") or "").strip()
    published_at = None
    pp = get("published_parsed") or get("updated_parsed")
    if pp:
        try:
            published_at = datetime(*pp[:6], tzinfo=timezone.utc)
        except Exception:
            published_at = None
    return {
        "source_key": source["key"],
        "source_name": source.get("name"),
        "title": title[:1000],
        "url": url or None,
        "summary": (summary[:4000] or None),
        "topics": source.get("topics") or [],
        "lang": get("language") or None,
        "published_at": published_at,
        # dédup : clé stable = source + (url sinon titre)
        "content_hash": _hash(source["key"], url or title),
    }


def _fetch_feed(url: str) -> list:
    """Récupère + parse un flux RSS/Atom. Isolé : `feedparser` importé
    paresseusement + accès réseau → NON couvert par les tests unitaires (qui
    injectent un `fetcher`). On teste la normalisation / dédup / synthèse."""
    import feedparser  # dépendance déclarée dans requirements.txt
    parsed = feedparser.parse(url)
    return list(parsed.entries or [])


def ingest(db: Session, sources: Optional[list] = None, fetcher=None) -> dict:
    """Récupère toutes les sources, normalise, déduplique (par hash) et upserte.

    `fetcher(url) -> entries` est injectable (tests). **Fail-soft par source** :
    une source en échec est ignorée + journalisée, sans interrompre les autres.
    """
    sources = sources if sources is not None else VEILLE_SOURCES
    fetch = fetcher or _fetch_feed
    created, skipped, errors = 0, 0, 0
    for source in sources:
        try:
            entries = fetch(source["url"])
        except Exception as e:  # source morte / réseau / parse → on continue
            errors += 1
            logger.warning("Veille : échec source %s : %s", source.get("key"), e)
            continue
        for entry in entries or []:
            item = normalize_entry(source, entry)
            if not item:
                continue
            exists = db.query(VeilleItem).filter(
                VeilleItem.content_hash == item["content_hash"]
            ).first()
            if exists:
                skipped += 1
                continue
            db.add(VeilleItem(**item))
            created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors, "sources": len(sources)}


def retrieve(db: Session, topics: Optional[list] = None, limit: int = 40) -> list:
    """Items les plus récents (par `fetched_at`), filtrés par topics si fournis.

    v1 du RAG : récence + mots-clés (pas d'embeddings). Portable SQLite/Postgres
    (pas de `NULLS LAST`). Le filtre topics se fait en Python (JSON portable).
    """
    items = (
        db.query(VeilleItem)
        .order_by(VeilleItem.fetched_at.desc())
        .limit(500)
        .all()
    )
    if topics:
        wanted = {t.lower() for t in topics}
        items = [
            it for it in items
            if wanted & {(t or "").lower() for t in (it.topics or [])}
        ]
    return items[: max(1, limit)]


def synthesize(items: list, llm=None, db=None) -> dict:
    """Construit un prompt à partir des items et appelle le LLM (fournisseur choisi
    par le propriétaire) pour une synthèse structurée en français.

    `llm(prompt) -> {"text","model"}` injectable (tests). Si absent, on résout le
    fournisseur via le sélecteur propriétaire (`db`) + variables d'env — le moteur
    de veille est ainsi **alimenté par les mêmes fournisseurs** que la plateforme,
    sans dépendre de Claude. Renvoie {summary, model, items}. Anti-hallucination :
    « uniquement à partir des sources »."""
    if not items:
        return {"summary": "Aucun élément de veille récent.", "model": None, "items": []}
    lines = []
    for it in items:
        d = ""
        if getattr(it, "published_at", None):
            try:
                d = " (" + it.published_at.date().isoformat() + ")"
            except Exception:
                d = ""
        lines.append(
            f"- [{it.source_name or it.source_key}] {it.title}{d} {it.url or ''}\n"
            f"  {(it.summary or '')[:500]}"
        )
    corpus = "\n".join(lines)
    prompt = (
        "Tu es analyste de veille pour une coopérative de cacao en Côte d'Ivoire. "
        "À partir UNIQUEMENT des sources ci-dessous, rédige une synthèse en français :\n"
        "1) 3 à 6 points clés ;\n"
        "2) impacts concrets pour la coopérative (EUDR, marché, certification) ;\n"
        "3) cite les sources utilisées (nom + lien).\n"
        "N'invente rien qui ne figure pas dans les sources.\n\n"
        f"SOURCES :\n{corpus}"
    )
    call = llm or (lambda p: _default_llm(p, db=db))
    out = call(prompt) or {}
    return {
        "summary": out.get("text", ""),
        "model": out.get("model"),
        "items": [
            {"title": it.title, "url": it.url, "source": it.source_name or it.source_key}
            for it in items
        ],
    }


def _default_llm(prompt: str, db=None) -> dict:
    """Synthèse via le client LLM partagé : fournisseur résolu par le sélecteur
    propriétaire (`db`) puis variables d'env (presets DeepSeek/Qwen/OpenAI/
    OpenRouter/open-weights/local). Le moteur de veille est donc **alimenté par
    les mêmes fournisseurs** que la plateforme et reste indépendant de Claude.
    Lève (RuntimeError) si le fournisseur n'est pas configuré."""
    from app.services import llm_client
    return llm_client.chat(db, prompt, max_tokens=1200, temperature=0.2)
