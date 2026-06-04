"""Tests — Veille Marché (GET /market/intelligence). L'appel Claude est mocké."""
import app.services.market_intel as mi
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


def _reset_cache():
    mi._CACHE["data"] = None
    mi._CACHE["ts"] = 0.0


def _fake_claude_ok():
    async def _fake():
        parsed = {
            "london": "3 400 $/t", "london_change": "-2.1%", "london_up": False,
            "ny": "3 350 $/t", "ny_change": "-1.8%", "ny_up": False,
            "news": [
                {"title": "EUDR : les coops s'organisent", "source": "Mongabay",
                 "date": "il y a 2 jours", "cat": "EUDR", "summary": "Préparation à la traçabilité."},
                {"title": "CSSVD en hausse", "source": "Ecofin", "date": "il y a 5 jours",
                 "cat": "Santé", "summary": "41% des exploitations touchées."},
            ],
            "ai_summary": "Marché en baisse, pression EUDR, CSSVD en hausse : numériser vite.",
        }
        usage = {"model": "claude-sonnet-4-20250514", "input_tokens": 1200, "output_tokens": 600}
        return parsed, usage
    return _fake


# ── Fallback gracieux (pas de clé IA → pas de 500, pas de faux prix) ──────────

def test_market_fallback_without_key(client):
    _reset_cache()
    h, _ = _admin(client, "veille.fallback@test.ci")
    r = client.get("/market/intelligence", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is False
    assert body["prices"]["ccc"]["fcfa_kg"] > 0      # prix CCC officiel (config) toujours présent
    assert body["news"] == []
    assert body["note"]                               # message d'indisponibilité


# ── Données live (Claude mocké) + suivi de coût ───────────────────────────────

def test_market_live_records_cost(client, monkeypatch):
    _reset_cache()
    monkeypatch.setattr(mi, "_call_claude_market", _fake_claude_ok())
    h, coop_id = _admin(client, "veille.live@test.ci")

    r = client.get("/market/intelligence?refresh=true", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is True
    assert len(body["news"]) == 2
    assert body["prices"]["london"]["value"] == "3 400 $/t"
    assert body["prices"]["indicative"] is True
    assert body["ai_summary"]

    # Le coût a été tracé dans AiUsage (feature dédiée).
    db = TestingSessionLocal()
    try:
        rows = db.query(AiUsage).filter(
            AiUsage.feature == "market_intelligence",
            AiUsage.cooperative_id == coop_id,
        ).all()
        assert len(rows) == 1
        assert rows[0].input_tokens == 1200 and rows[0].output_tokens == 600
        assert rows[0].cost_usd > 0
    finally:
        db.close()
    _reset_cache()


def test_market_uses_shared_cache(client, monkeypatch):
    """Le 2e appel (non forcé) sert le cache → aucun nouvel appel/coût."""
    _reset_cache()
    monkeypatch.setattr(mi, "_call_claude_market", _fake_claude_ok())
    h, coop_id = _admin(client, "veille.cache@test.ci")

    client.get("/market/intelligence?refresh=true", headers=h)  # remplit le cache (1 appel)
    r2 = client.get("/market/intelligence", headers=h)          # doit servir le cache
    assert r2.json()["cached"] is True

    db = TestingSessionLocal()
    try:
        n = db.query(AiUsage).filter(
            AiUsage.feature == "market_intelligence", AiUsage.cooperative_id == coop_id,
        ).count()
        assert n == 1   # un seul appel facturé malgré 2 requêtes
    finally:
        db.close()
    _reset_cache()


# ── Feature-gating premium ────────────────────────────────────────────────────

def test_market_gated_by_plan(client):
    _reset_cache()
    h, coop_id = _admin(client, "veille.gate@test.ci", coop="Coop Veille Gate")
    # Downgrade en 'starter' (pas de premium) → 403
    assert client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "starter"}, headers=h).status_code == 200
    r = client.get("/market/intelligence", headers=h)
    assert r.status_code == 403


def test_market_requires_auth(client):
    assert client.get("/market/intelligence").status_code == 401
