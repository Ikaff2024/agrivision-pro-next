"""Multi-fournisseur IA (Conseil agronomique) : coût par modèle + garde de config."""

import asyncio

from app import ai_advisor
from app.services.ai_cost import compute_cost_usd


def test_cost_is_model_aware():
    """Un LLM open source (DeepSeek/Qwen) coûte bien moins que Claude pour le même usage."""
    claude = compute_cost_usd(10_000, 2_000, "claude-sonnet-4-6")
    deepseek = compute_cost_usd(10_000, 2_000, "deepseek-chat")
    qwen = compute_cost_usd(10_000, 2_000, "qwen-plus")
    assert claude > deepseek
    assert claude > qwen
    # Modèle inconnu -> repli sur la grille par défaut (env / Claude Sonnet).
    assert compute_cost_usd(10_000, 2_000) == compute_cost_usd(10_000, 2_000, "modele-inconnu")


def test_openai_provider_requires_key(monkeypatch):
    """Avec AI_PROVIDER=deepseek mais sans clé, on renvoie une erreur de config (pas d'appel réseau)."""
    monkeypatch.setattr(ai_advisor, "AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("AI_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_OPENAI_MODEL", raising=False)

    result, usage = asyncio.run(ai_advisor.get_ai_advice(
        {"id": 1, "name": "P"}, None, [], {"has_boundary": False},
    ))
    assert usage is None
    assert "error" in result


def test_default_provider_is_anthropic():
    assert ai_advisor.AI_PROVIDER in ("anthropic", "claude", "")
