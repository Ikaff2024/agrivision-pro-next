"""Tests — Veille Marché (GET /market/intelligence).

Architecture agnostique de Claude :
- prix réel ICE New York (mocké) + CCC officiel ;
- actualités issues du moteur de veille open-source (items RSS ingérés) ;
- synthèse via le fournisseur sélectionné (client LLM partagé, mocké).
Aucun accès réseau dans les tests.
"""
import pytest

import app.services.market_intel as mi
import app.services.llm_client as llmc
import app.ai_advisor as ai_advisor
from app.services import veille_engine, platform_settings
from app.db.models import AiUsage
from tests.conftest import TestingSessionLocal


def _admin(client, email, coop="Coop Veille"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    coop_id = client.get("/me", headers=h).json()["cooperative_id"]
    return h, coop_id


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Pas de cours réel par défaut + AUCUN fournisseur prêt (zéro appel LLM réel)."""
    async def _none():
        return None
    monkeypatch.setattr(mi, "_fetch_ny_cocoa", _none)
    monkeypatch.setattr(ai_advisor, "AI_PROVIDER", "openweights")  # défaut : non prêt (base_url requis)
    for v in ("AI_OPENAI_BASE_URL", "AI_OPENAI_API_KEY", "OPENWEIGHTS_API_KEY",
              "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY",
              "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    yield


def _seed_news(topics=("cacao", "marche")):
    """Ingère 2 items de veille (via fetcher injecté) pour alimenter le marché."""
    db = TestingSessionLocal()
    try:
        veille_engine.ingest(db, sources=[
            {"key": "t_market", "name": "Test Marché", "url": "u", "topics": list(topics)},
        ], fetcher=lambda url: [
            {"title": "Cours du cacao en hausse à Abidjan", "link": "http://n/1", "summary": "Marché porteur."},
            {"title": "EUDR : les coops s'organisent", "link": "http://n/2", "summary": "Traçabilité."},
        ])
    finally:
        db.close()


def _select_openrouter(monkeypatch, ready=True):
    """Sélectionne OpenRouter ; `ready` contrôle la présence de la clé serveur."""
    db = TestingSessionLocal()
    try:
        platform_settings.set_setting(db, platform_settings.AI_PROVIDER_KEY, "openrouter")
        platform_settings.set_setting(db, platform_settings.AI_MODEL_KEY, "")
    finally:
        db.close()
    if ready:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")


def _patch_llm_ok(monkeypatch):
    calls = {"n": 0}
    def _chat(db, prompt, **kw):
        calls["n"] += 1
        return {"text": "Synthèse marché FR", "model": "meta-llama/llama-3.3-70b-instruct",
                "input_tokens": 300, "output_tokens": 120}
    monkeypatch.setattr(llmc, "chat", _chat)
    return calls


# ── Prix ──────────────────────────────────────────────────────────────────────
def test_real_ny_price_without_ai(client, monkeypatch):
    async def _ny():
        return {"value": "3 929 $/t", "change": "+0.9%", "up": True,
                "source": "ICE New York · temps différé", "indicative": False}
    monkeypatch.setattr(mi, "_fetch_ny_cocoa", _ny)
    h, _ = _admin(client, "veille.realny@test.ci")
    body = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert body["prices"]["ny"]["value"] == "3 929 $/t"
    assert body["prices"]["ny"]["indicative"] is False
    assert body["prices"]["ccc"]["fcfa_kg"] > 0
    assert body["live"] is False           # aucune actu ingérée
    assert body["note"]


def test_full_fallback(client):
    h, _ = _admin(client, "veille.fallback@test.ci")
    body = client.get("/market/intelligence", headers=h).json()
    assert body["live"] is False
    assert body["prices"]["ccc"]["fcfa_kg"] > 0
    assert body["prices"]["ny"] is None
    assert body["news"] == []
    assert body["note"]


# ── Actualités (veille open-source) + synthèse (fournisseur) + coût ───────────
def test_news_from_veille_and_summary_cost(client, monkeypatch):
    _seed_news()
    _select_openrouter(monkeypatch, ready=True)
    _patch_llm_ok(monkeypatch)
    h, coop_id = _admin(client, "veille.live@test.ci")
    body = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert body["live"] is True
    assert len(body["news"]) == 2
    assert body["ai_summary"] == "Synthèse marché FR"

    db = TestingSessionLocal()
    try:
        rows = db.query(AiUsage).filter(
            AiUsage.feature == "market_intelligence", AiUsage.cooperative_id == coop_id).all()
        assert len(rows) == 1
        assert rows[0].input_tokens == 300 and rows[0].cost_usd > 0
    finally:
        db.close()


def test_summary_is_cached_not_regenerated(client, monkeypatch):
    _seed_news()
    _select_openrouter(monkeypatch, ready=True)
    calls = _patch_llm_ok(monkeypatch)
    h, _ = _admin(client, "veille.cache@test.ci")
    client.get("/market/intelligence?refresh=true", headers=h)   # génère (1 appel)
    r2 = client.get("/market/intelligence", headers=h).json()    # sert le cache
    assert r2["ai_summary"] == "Synthèse marché FR"
    assert calls["n"] == 1                                        # pas de régénération


# ── Prix d'achat coopérative ─────────────────────────────────────────────────
def test_coop_price_from_purchases(client):
    h, _ = _admin(client, "veille.coop@test.ci")
    client.post("/plantations", json={
        "name": "P", "owner_name": "O", "country": "CI", "region": "Y", "hectares": 2.0,
    }, headers=h)
    pid = client.get("/producers?limit=50", headers=h).json()[0]["id"]
    client.post("/purchases", json={
        "producer_id": pid, "net_weight_kg": 100, "price_per_kg_fcfa": 1500, "payment_status": "pending",
    }, headers=h)
    body = client.get("/market/intelligence", headers=h).json()
    assert body["coop_price"]["avg_fcfa_kg"] == 1500
    assert body["coop_price"]["purchases"] == 1


def test_coop_price_none_without_purchases(client):
    h, _ = _admin(client, "veille.nocoop@test.ci")
    assert client.get("/market/intelligence", headers=h).json()["coop_price"] is None


# ── Gating premium + auth ────────────────────────────────────────────────────
def test_available_on_all_plans(client):
    h, coop_id = _admin(client, "veille.allplans@test.ci", coop="Coop Veille All")
    assert client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "starter"}, headers=h).status_code == 200
    assert client.get("/market/intelligence", headers=h).status_code == 200


def test_requires_auth(client):
    assert client.get("/market/intelligence").status_code == 401


# ── Diagnostic IA (admin uniquement) ─────────────────────────────────────────
def test_diag_admin_provider_not_configured(client, monkeypatch):
    """L'admin voit clairement que le fournisseur n'est pas configuré."""
    _seed_news()
    _select_openrouter(monkeypatch, ready=False)   # provider choisi mais SANS clé
    h, _ = _admin(client, "veille.diag@test.ci")
    body = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert "diag" in body
    diag = body["diag"]
    assert diag["ok"] is False
    assert diag["key_present"] is False
    assert "non configuré" in diag["reason"].lower()


def test_diag_hidden_for_non_admin(client):
    from app.db.models import User
    h, _ = _admin(client, "veille.agro@test.ci", coop="Coop Agro Diag")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.email == "veille.agro@test.ci").update({"role": "agronomist"})
        db.commit()
    finally:
        db.close()
    body = client.get("/market/intelligence", headers=h).json()
    assert "diag" not in body
