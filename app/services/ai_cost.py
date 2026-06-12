"""
Tarification et calcul du cout de revient des appels a l'API Claude
(module Conseil agronomique IA).

Le cout de revient depend du nombre de tokens consommes (entree + sortie),
renvoyes par l'API Anthropic a chaque appel. La grille tarifaire est
parametrable par variables d'environnement (config serveur), avec pour
valeurs par defaut les tarifs publics de Claude Sonnet 4 :
  - entree  : 3 USD / million de tokens
  - sortie  : 15 USD / million de tokens

Le taux de conversion USD -> FCFA est lui aussi parametrable (contexte
ivoirien). Toutes ces valeurs sont lues a l'import : il suffit de definir
les variables d'environnement au demarrage du serveur.
"""
from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    """Lit une variable d'environnement en float, avec repli sur la valeur par defaut."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


# Grille tarifaire (USD par million de tokens) — defaut : Claude Sonnet 4.
COST_PER_1M_INPUT_TOKENS_USD = _env_float("AI_COST_INPUT_PER_1M_USD", 3.0)
COST_PER_1M_OUTPUT_TOKENS_USD = _env_float("AI_COST_OUTPUT_PER_1M_USD", 15.0)

# Taux de conversion pour affichage local (1 USD = X FCFA).
USD_TO_FCFA_RATE = _env_float("USD_TO_FCFA_RATE", 600.0)

# Prix indicatifs (USD / 1M tokens) par famille de modele : permet un cout de
# revient realiste quand on bascule sur un LLM open source (DeepSeek/Qwen),
# bien moins cher que Claude. Repli sur la grille env (Claude) si modele inconnu.
_MODEL_PRICES = {
    "claude-haiku": (1.0, 5.0),
    "claude-opus": (5.0, 25.0),
    "claude-sonnet": (3.0, 15.0),
    "claude": (3.0, 15.0),
    "deepseek": (0.27, 1.10),
    "qwen": (0.40, 1.20),
    "gpt-4o-mini": (0.15, 0.60),
}


def _price_for(model: str | None) -> tuple[float, float]:
    m = (model or "").lower()
    for key, price in _MODEL_PRICES.items():
        if key in m:
            return price
    return (COST_PER_1M_INPUT_TOKENS_USD, COST_PER_1M_OUTPUT_TOKENS_USD)


def compute_cost_usd(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    """Cout en USD d'un appel, a partir des tokens consommes et du modele utilise."""
    it = max(0, int(input_tokens or 0))
    ot = max(0, int(output_tokens or 0))
    price_in, price_out = _price_for(model)
    cost = (it / 1_000_000.0) * price_in + (ot / 1_000_000.0) * price_out
    return round(cost, 6)


def usd_to_fcfa(amount_usd: float) -> float:
    """Convertit un montant USD en FCFA selon le taux courant."""
    return round((amount_usd or 0.0) * USD_TO_FCFA_RATE, 2)


def pricing_info() -> dict:
    """Grille tarifaire courante — pour affichage transparent dans l'UI propriétaire."""
    return {
        "input_per_1m_usd": COST_PER_1M_INPUT_TOKENS_USD,
        "output_per_1m_usd": COST_PER_1M_OUTPUT_TOKENS_USD,
        "usd_to_fcfa_rate": USD_TO_FCFA_RATE,
    }
