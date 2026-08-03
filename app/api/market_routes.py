"""
Veille Marché Cacao (module premium).

GET /market/intelligence : prix (CCC officiel + cours réel ICE New York),
actualités filtrables et synthèse IA.

Architecture (agnostique de Claude) :
- PRIX : cours réel ICE New York + prix bord-champ officiel CCC (aucune IA).
- ACTUALITÉS : tirées du moteur de veille open-source (RSS Google News cacao
  monde + Côte d'Ivoire), donc une seule source de news pour toute la page.
- SYNTHÈSE : générée par le FOURNISSEUR sélectionné (sélecteur propriétaire,
  ex. OpenRouter) via le client LLM partagé — plus de dépendance à Claude.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Cooperative, User
from app.services.market_intel import get_market_prices

logger = logging.getLogger("agrivision")

router = APIRouter(prefix="/market", tags=["Veille marché"])


def _coop_recent_price(db: Session, coop_id, days: int = 60):
    """Prix d'achat moyen RÉEL de la coopérative sur la période (données Achats).

    Donnée propre à la coop, jamais trompeuse (contrairement à un plancher
    générique). Renvoie None si aucun achat récent valorisé.
    """
    if not coop_id:
        return None
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.db.models import PurchaseRecord
    since = datetime.utcnow() - timedelta(days=days)
    avg_price, n = db.query(
        func.avg(PurchaseRecord.price_per_kg_fcfa), func.count(PurchaseRecord.id)
    ).filter(
        PurchaseRecord.cooperative_id == coop_id,
        PurchaseRecord.price_per_kg_fcfa.isnot(None),
        PurchaseRecord.purchase_date >= since,
    ).one()
    if not n or not avg_price:
        return None
    return {"avg_fcfa_kg": round(float(avg_price)), "purchases": int(n), "period_days": days}


def _save_market_cache(db: Session, data: dict) -> None:
    """Persiste la dernière bonne charge de veille (survit aux redéploiements)."""
    import json
    from datetime import datetime, timezone
    from app.db.models import MarketCache
    try:
        row = db.query(MarketCache).order_by(MarketCache.id.desc()).first()
        payload = json.dumps(data, ensure_ascii=False)
        if row:
            row.payload = payload
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(MarketCache(payload=payload))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("MarketCache: sauvegarde échouée (ignorée) : %s", e)


def _load_market_cache(db: Session) -> Optional[dict]:
    import json
    from app.db.models import MarketCache
    try:
        row = db.query(MarketCache).order_by(MarketCache.id.desc()).first()
        return json.loads(row.payload) if row else None
    except Exception:  # noqa: BLE001
        return None


# ── Actualités issues du moteur de veille open-source (RSS cacao monde + CI) ──
# Bloc MARCHÉ = prix/marché uniquement (topic "marche"). La veille EUDR/réglementaire
# vit dans la page Veille (moteur open-source) → pas de doublon entre les deux blocs.
_MARKET_TOPICS = ["marche"]


def _market_cat(topics) -> str:
    """Catégorie d'affichage (chips marché) à partir des topics de veille."""
    ts = {(t or "").lower() for t in (topics or [])}
    if "eudr" in ts:
        return "EUDR"
    if ts & {"marche", "cacao", "monde", "cote_ivoire", "certification", "durabilite"}:
        return "Marché"
    return "Autre"


def _item_date(it):
    """Date de référence d'un item pour l'ancienneté : publication sinon récupération."""
    from datetime import timezone as _tz
    dt = getattr(it, "published_at", None) or getattr(it, "fetched_at", None)
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    return dt


def _news_from_veille(db: Session, limit: int = 12, max_age_days: Optional[int] = None) -> list:
    """Mappe les items de veille récents (marché/cacao) au format des actualités marché.

    `max_age_days` (facultatif) borne l'ancienneté sur la date de PUBLICATION
    (à défaut, date de récupération) : ne conserve que les infos plus récentes.
    """
    from datetime import timedelta
    from app.services import veille_engine
    # On récupère large puis on filtre par âge, pour rester au niveau de `limit`.
    items = veille_engine.retrieve(db, topics=_MARKET_TOPICS, limit=200 if max_age_days else limit)
    if max_age_days and max_age_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        items = [it for it in items if (_item_date(it) or cutoff) >= cutoff]
    items = items[: max(1, limit)]
    out = []
    for it in items:
        d = ""
        if getattr(it, "published_at", None):
            try:
                d = it.published_at.date().isoformat()
            except Exception:  # noqa: BLE001
                d = ""
        out.append({
            "title": it.title,
            "source": it.source_name or it.source_key or "",
            "date": d,
            "cat": _market_cat(it.topics),
            "summary": it.summary or "",
            "url": it.url,
        })
    return out


def _market_prompt(news: list) -> str:
    lines = [
        f"- [{n['source']}] {n['title']}" + (f" ({n['date']})" if n['date'] else "")
        for n in news[:10]
    ]
    return (
        "Tu es analyste de la filière cacao pour une coopérative ivoirienne. À partir "
        "UNIQUEMENT des actualités ci-dessous, rédige 2 à 3 phrases stratégiques "
        "(prix/marché, EUDR, opportunités et risques pour la coopérative). "
        "N'invente rien qui n'y figure pas.\n\nACTUALITÉS :\n" + "\n".join(lines)
    )


def _load_summary_cache(db: Session) -> dict:
    return _load_market_cache(db) or {}


def _save_summary_cache(db: Session, summary: str, model: Optional[str]) -> None:
    _save_market_cache(db, {
        "ai_summary": summary, "ai_model": model,
        "ai_generated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/intelligence")
async def market_intelligence(
    refresh: bool = Query(False, description="Forcer une actualisation (admin/agronome)"),
    max_age_days: Optional[int] = Query(
        None, ge=1, le=1825,
        description="Ne garder que les actualités publiées dans les N derniers jours (facultatif).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Feature-gating : module premium ──
    from app.services.plans import has_module

    plan = "enterprise"
    if current_user.cooperative_id:
        coop = db.query(Cooperative).filter(Cooperative.id == current_user.cooperative_id).first()
        if coop and coop.plan:
            plan = coop.plan
    if not has_module(plan, "veille"):
        raise HTTPException(
            status_code=403,
            detail="Module « Veille Marché » non inclus dans votre plan (premium requis).",
        )

    # Le rafraîchissement forcé est réservé aux rôles d'écriture (borne le coût IA).
    force = bool(refresh) and current_user.role in ("admin", "agronomist")

    # 1) Prix (réel, sans IA) + 2) actualités (moteur de veille open-source).
    prices = await get_market_prices()
    news = _news_from_veille(db, max_age_days=max_age_days)

    # 3) Synthèse par le FOURNISSEUR sélectionné (cache pour borner le coût :
    #    régénérée seulement sur refresh forcé ou si aucune synthèse en cache).
    cache = _load_summary_cache(db)
    ai_summary = cache.get("ai_summary") or ""
    ai_model = cache.get("ai_model")
    diag = {
        "ok": None, "key_present": False, "key_prefix": "", "status": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reason": "Aucune synthèse générée.",
    }
    from app.services.platform_settings import resolve_ai_config, available_providers
    provider, model = resolve_ai_config(db)
    ready = next((p["ready"] for p in available_providers() if p["id"] == provider), False)
    diag["key_present"], diag["key_prefix"] = ready, provider

    if news and (force or not ai_summary):
        if not ready:
            diag["ok"] = False
            diag["reason"] = f"Fournisseur IA « {provider} » non configuré (clé serveur manquante)."
        else:
            try:
                from app.services import llm_client
                out = llm_client.chat(db, _market_prompt(news), max_tokens=400, temperature=0.3)
                ai_summary = (out.get("text") or "").strip() or ai_summary
                ai_model = out.get("model") or model
                _save_summary_cache(db, ai_summary, ai_model)
                diag["ok"], diag["reason"] = True, "OK — synthèse générée par le fournisseur sélectionné."
                # Suivi du coût de revient (tokens réellement consommés).
                try:
                    from app.db.models import AiUsage
                    from app.services.ai_cost import compute_cost_usd
                    it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
                    db.add(AiUsage(
                        cooperative_id=current_user.cooperative_id, user_id=current_user.id,
                        plantation_id=None, feature="market_intelligence",
                        model=ai_model or "", input_tokens=it_, output_tokens=ot_,
                        cost_usd=compute_cost_usd(it_, ot_, ai_model),
                    ))
                    db.commit()
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    logger.warning("AiUsage (marché) échoué (ignoré) : %s", e)
            except Exception as e:  # noqa: BLE001
                diag["ok"] = False
                diag["reason"] = f"Synthèse IA indisponible : {type(e).__name__}."
                logger.warning("Synthèse marché (%s) échouée : %s", provider, e)
    elif not news:
        diag["reason"] = "Aucune actualité ingérée — cliquez « Rafraîchir les sources »."

    note = None
    if not news:
        note = ("Aucune actualité pour le moment. "
                "Admin : cliquez « Rafraîchir les sources » dans la veille réglementaire ci-dessous.")
    elif not ai_summary and not ready:
        note = "Synthèse IA indisponible (fournisseur non configuré). Prix et actualités à jour."

    data = {
        "generated_at": prices.get("generated_at"),
        "live": bool(news),
        "cached": False,
        "prices": prices.get("prices", {}),
        "news": news,
        "ai_summary": ai_summary or None,
        "note": note,
        "max_age_days": max_age_days,
        "coop_price": _coop_recent_price(db, current_user.cooperative_id),
    }
    if current_user.role == "admin":
        data["diag"] = diag
    return data
