"""
app/ai_advisor.py
Module d'analyse agronomique IA via Claude API.
Appelé par l'endpoint POST /plantations/{id}/ai-advice
"""
import os
import logging
import httpx

logger = logging.getLogger("agrivision")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Modèle surchargeable par env (levier de coût). Défaut : Sonnet 4.6 (courant ;
# l'ancien claude-sonnet-4-20250514 part en retraite le 2026-06-15).
# Ex. AI_ADVISOR_MODEL=claude-haiku-4-5 → ~3x moins cher pour ce conseil structuré.
CLAUDE_MODEL      = os.getenv("AI_ADVISOR_MODEL", "claude-sonnet-4-6")
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"

# Fournisseur IA : "anthropic" (defaut) ou un LLM open source compatible OpenAI
# (DeepSeek, Qwen, etc.) pour reduire le cout. Le format de sortie est identique.
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
# Presets compatibles OpenAI : (base_url, modele par defaut, variable de cle).
# Surchargeables par AI_OPENAI_BASE_URL / AI_OPENAI_MODEL / AI_OPENAI_API_KEY.
_OPENAI_PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus", "DASHSCOPE_API_KEY"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
}


def build_agro_prompt(plantation: dict, latest_diag: dict, agro_records: list, boundary: dict) -> str:
    """Construit le prompt agronomique complet à partir des données AgriVision."""

    # Bloc plantation
    p_block = f"""
PLANTATION : {plantation.get('name', 'Inconnue')}
Propriétaire : {plantation.get('owner_name', '—')}
Localisation : {plantation.get('region', '—')}, {plantation.get('country', '—')}
Superficie déclarée : {plantation.get('hectares', '—')} ha
""".strip()

    # Bloc diagnostic
    if latest_diag:
        d_block = f"""
DERNIER DIAGNOSTIC AGRONOMIQUE
Score global : {latest_diag.get('global_score', '—')}/100
Niveau de risque : {latest_diag.get('global_risk_level', '—')}
Humidité : {latest_diag.get('humidity_pct', '—')}%
Pluviométrie mensuelle : {latest_diag.get('rainfall_mm_month', '—')} mm
Température moyenne : {latest_diag.get('avg_temp_c', '—')}°C
Âge de la plantation : {latest_diag.get('plantation_age_years', '—')} ans
Densité d'ombrage : {latest_diag.get('shade_tree_density_pct', '—')}%
""".strip()
    else:
        d_block = "DIAGNOSTIC : Aucun diagnostic réalisé à ce jour."

    # Bloc agroforesterie
    if agro_records:
        species_list = "\n".join(
            f"  - {r.get('species_name','?')} : {r.get('count_per_hectare','?')} arbres/ha"
            for r in agro_records
        )
        a_block = f"INVENTAIRE AGROFORESTIER\n{species_list}"
    else:
        a_block = "AGROFORESTERIE : Aucun inventaire disponible."

    # Bloc superficie mesurée
    if boundary and boundary.get("has_boundary"):
        b_block = f"SUPERFICIE MESURÉE (GPS/carte) : {boundary.get('area_hectares','—')} ha"
    else:
        b_block = "DÉLIMITATION : Parcelle non délimitée."

    return f"""Tu es un agronome expert spécialisé en cacaoculture en Afrique de l'Ouest, avec 20 ans d'expérience terrain en Côte d'Ivoire.

Voici les données AgriVision Pro pour une plantation :

{p_block}

{d_block}

{a_block}

{b_block}

Sur la base de ces données, fournis une analyse agronomique structurée en JSON avec exactement ce format :

{{
  "resume": "2-3 phrases résumant l'état général de la plantation",
  "points_forts": ["point 1", "point 2"],
  "risques_prioritaires": ["risque 1", "risque 2", "risque 3"],
  "actions": [
    {{"priorite": "urgent|important|conseil", "titre": "...", "detail": "...", "impact": "..."}},
    {{"priorite": "urgent|important|conseil", "titre": "...", "detail": "...", "impact": "..."}},
    {{"priorite": "urgent|important|conseil", "titre": "...", "detail": "...", "impact": "..."}}
  ],
  "perspective_eudr": "Évaluation courte de la conformité potentielle EUDR (déforestation zéro)",
  "score_potentiel": 85
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après. Sois précis, concret et adapté aux réalités ivoiriennes."""


def _parse_advice_json(raw_text: str) -> dict:
    """Extrait le JSON renvoyé par le modèle (tolère un bloc ```json … ```)."""
    import json
    t = (raw_text or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t.strip())


def _http_error_message(status: int, body_text: str) -> str:
    body = (body_text or "").lower()
    logger.warning("AI advice HTTP %s : %s", status, (body_text or "")[:300])
    if status == 401:
        return "Clé API IA invalide ou révoquée. Contactez l'administrateur."
    if status == 400 and any(k in body for k in ("credit", "billing", "insufficient", "quota")):
        return "Crédit IA insuffisant : rechargez le compte du fournisseur IA, puis réessayez."
    if status in (402, 403):
        return "Accès IA refusé (facturation ou permissions). Vérifiez le compte du fournisseur IA."
    if status == 429:
        return "Service IA momentanément saturé. Réessayez dans une minute."
    return f"Erreur API IA ({status}). Réessayez dans quelques instants."


async def get_ai_advice(plantation: dict, latest_diag: dict, agro_records: list, boundary: dict):
    """
    Génère l'analyse agronomique structurée via le fournisseur IA configuré.

    Retourne un tuple ``(result, usage)`` :
      - ``result`` : le dict d'analyse (ou ``{"error": ...}`` en cas d'echec) ;
      - ``usage``  : ``{"model", "input_tokens", "output_tokens"}`` (suivi de cout).

    Anthropic par défaut ; bascule possible vers un LLM open source compatible
    OpenAI (DeepSeek, Qwen…) via ``AI_PROVIDER`` — le format de sortie est identique.
    """
    prompt = build_agro_prompt(plantation, latest_diag, agro_records, boundary)
    if AI_PROVIDER in ("anthropic", "claude", ""):
        return await _advice_anthropic(prompt, plantation)
    return await _advice_openai_compatible(prompt, plantation)


async def _advice_anthropic(prompt: str, plantation: dict):
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY non configurée")
        return {"error": "Clé API IA non configurée. Contactez l'administrateur."}, None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      CLAUDE_MODEL,
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            usage_raw = data.get("usage") or {}
            usage = {
                "model": data.get("model", CLAUDE_MODEL),
                "input_tokens": int(usage_raw.get("input_tokens", 0) or 0),
                "output_tokens": int(usage_raw.get("output_tokens", 0) or 0),
            }
            result = _parse_advice_json(data["content"][0]["text"])
            logger.info("AI advice OK (anthropic) pour plantation %s", plantation.get('id'))
            return result, usage
    except httpx.TimeoutException:
        logger.warning("AI advice timeout (anthropic)")
        return {"error": "L'analyse IA a pris trop de temps. Réessayez dans quelques instants."}, None
    except httpx.HTTPStatusError as e:
        return {"error": _http_error_message(e.response.status_code, e.response.text)}, None
    except Exception as e:
        logger.warning("AI advice erreur (anthropic) : %s", e)
        return {"error": "Analyse IA temporairement indisponible."}, None


async def _advice_openai_compatible(prompt: str, plantation: dict):
    """Conseil via un endpoint compatible OpenAI (/chat/completions) : DeepSeek, Qwen…"""
    preset = _OPENAI_PRESETS.get(AI_PROVIDER)
    base_url = (os.getenv("AI_OPENAI_BASE_URL") or (preset[0] if preset else "")).rstrip("/")
    model = os.getenv("AI_OPENAI_MODEL") or (preset[1] if preset else "")
    api_key = os.getenv("AI_OPENAI_API_KEY") or (os.getenv(preset[2]) if preset else "") or ""
    if not base_url or not api_key or not model:
        logger.error("Fournisseur IA '%s' incomplet (base_url/clé/modèle manquant).", AI_PROVIDER)
        return {"error": "Fournisseur IA non configuré (clé/URL/modèle manquant). Contactez l'administrateur."}, None
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={
                    "model": model,
                    "max_tokens": 1500,
                    "temperature": 0.3,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            choice = (data.get("choices") or [{}])[0]
            raw_text = ((choice.get("message") or {}).get("content") or "")
            u = data.get("usage") or {}
            usage = {
                "model": data.get("model", model),
                "input_tokens": int(u.get("prompt_tokens", 0) or 0),
                "output_tokens": int(u.get("completion_tokens", 0) or 0),
            }
            result = _parse_advice_json(raw_text)
            logger.info("AI advice OK (%s / %s) pour plantation %s", AI_PROVIDER, model, plantation.get('id'))
            return result, usage
    except httpx.TimeoutException:
        logger.warning("AI advice timeout (%s)", AI_PROVIDER)
        return {"error": "L'analyse IA a pris trop de temps. Réessayez dans quelques instants."}, None
    except httpx.HTTPStatusError as e:
        return {"error": _http_error_message(e.response.status_code, e.response.text)}, None
    except Exception as e:
        logger.warning("AI advice erreur (%s) : %s", AI_PROVIDER, e)
        return {"error": "Analyse IA temporairement indisponible."}, None
