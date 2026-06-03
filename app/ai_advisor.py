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
CLAUDE_MODEL      = "claude-sonnet-4-20250514"
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"


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


async def get_ai_advice(plantation: dict, latest_diag: dict, agro_records: list, boundary: dict):
    """
    Appelle Claude API et retourne l'analyse agronomique structurée.

    Retourne un tuple ``(result, usage)`` :
      - ``result`` : le dict d'analyse (ou ``{"error": ...}`` en cas d'echec) ;
      - ``usage``  : ``{"model", "input_tokens", "output_tokens"}`` lorsque l'appel
        a effectivement consomme des tokens (pour le suivi de cout), sinon ``None``.
    """
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY non configurée")
        return {"error": "Clé API IA non configurée. Contactez l'administrateur."}, None

    prompt = build_agro_prompt(plantation, latest_diag, agro_records, boundary)

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
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Usage reel renvoye par l'API (pour le suivi du cout de revient).
            usage_raw = data.get("usage") or {}
            usage = {
                "model": data.get("model", CLAUDE_MODEL),
                "input_tokens": int(usage_raw.get("input_tokens", 0) or 0),
                "output_tokens": int(usage_raw.get("output_tokens", 0) or 0),
            }

            raw_text = data["content"][0]["text"].strip()

            # Parser le JSON retourné par Claude
            import json
            # Nettoyer les éventuels backticks
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            result = json.loads(raw_text.strip())
            logger.info("AI advice OK pour plantation %s", plantation.get('id'))
            return result, usage

    except httpx.TimeoutException:
        logger.warning("AI advice timeout")
        return {"error": "L'analyse IA a pris trop de temps. Réessayez dans quelques instants."}, None
    except httpx.HTTPStatusError as e:
        logger.warning("AI advice HTTP error %s", e.response.status_code)
        return {"error": f"Erreur API IA ({e.response.status_code}). Réessayez dans quelques instants."}, None
    except Exception as e:
        logger.warning("AI advice erreur : %s", e)
        return {"error": "Analyse IA temporairement indisponible."}, None
