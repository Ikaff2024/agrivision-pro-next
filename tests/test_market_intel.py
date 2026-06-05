"""Tests — Veille Marché (GET /market/intelligence).

Le cours réel (Yahoo) ET l'appel Claude sont mockés → aucun accès réseau.
"""
import pytest

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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Évite tout appel réseau : pas de cours réel par défaut, cache réinitialisé."""
    async def _none():
        return None
    monkeypatch.setattr(mi, "_fetch_ny_cocoa", _none)
    mi._CACHE["data"] = None
    mi._CACHE["ts"] = 0.0
    mi._LAST_GOOD["data"] = None
    yield
    mi._CACHE["data"] = None
    mi._CACHE["ts"] = 0.0
    mi._LAST_GOOD["data"] = None


def _patch_claude_ok(monkeypatch):
    async def _fake():
        parsed = {
            "london": "3 400 £/t", "london_change": "-2.1%", "london_up": False,
            "ny": "3 950 $/t", "ny_change": "-1.8%", "ny_up": False,
            "news": [
                {"title": "EUDR : les coops s'organisent", "source": "Mongabay",
                 "date": "il y a 2 jours", "cat": "EUDR", "summary": "Préparation à la traçabilité."},
                {"title": "Forum cacao à Abidjan en juin", "source": "CCC",
                 "date": "à venir", "cat": "Événement", "summary": "Conférence filière."},
            ],
            "ai_summary": '<cite index="12-1,42-2">Marché en baisse</cite>, pression EUDR : numériser vite.',
        }
        usage = {"model": "claude-sonnet-4-20250514", "input_tokens": 1200, "output_tokens": 600}
        return parsed, usage
    monkeypatch.setattr(mi, "_call_claude_market", _fake)


# ── Prix réel NY, indépendant de la clé IA ────────────────────────────────────

def test_real_ny_price_without_ai(client, monkeypatch):
    async def _ny():
        return {"value": "3 929 $/t", "change": "+0.9%", "up": True,
                "source": "ICE New York · temps différé", "indicative": False}
    monkeypatch.setattr(mi, "_fetch_ny_cocoa", _ny)
    h, _ = _admin(client, "veille.realny@test.ci")
    body = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert body["prices"]["ny"]["value"] == "3 929 $/t"
    assert body["prices"]["ny"]["indicative"] is False     # cours réel, pas une estimation
    assert body["prices"]["ccc"]["fcfa_kg"] > 0
    assert body["live"] is False                           # actus indisponibles sans clé IA
    assert body["note"]


# ── Fallback total (ni cours réel, ni clé IA) ─────────────────────────────────

def test_full_fallback(client):
    h, _ = _admin(client, "veille.fallback@test.ci")
    body = client.get("/market/intelligence", headers=h).json()
    assert body["live"] is False
    assert body["prices"]["ccc"]["fcfa_kg"] > 0     # prix officiel CCC toujours présent
    assert body["prices"]["ny"] is None
    assert body["news"] == []
    assert body["note"]


# ── Données IA (Claude mocké) + suivi de coût + événements ────────────────────

def test_live_records_cost_and_events(client, monkeypatch):
    _patch_claude_ok(monkeypatch)
    h, coop_id = _admin(client, "veille.live@test.ci")
    body = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert body["live"] is True
    assert len(body["news"]) == 2
    assert any(n["cat"] == "Événement" for n in body["news"])   # capte les événements (Q2)
    assert body["prices"]["london"]["value"] == "3 400 £/t"
    assert body["prices"]["london"]["indicative"] is True
    assert body["ai_summary"]
    assert "<cite" not in body["ai_summary"]   # balises de citation web nettoyées
    assert body["ai_summary"].startswith("Marché en baisse")

    db = TestingSessionLocal()
    try:
        rows = db.query(AiUsage).filter(
            AiUsage.feature == "market_intelligence", AiUsage.cooperative_id == coop_id).all()
        assert len(rows) == 1
        assert rows[0].input_tokens == 1200 and rows[0].cost_usd > 0
    finally:
        db.close()


def test_failure_keeps_last_good_news(client, monkeypatch):
    """Un échec Claude (ou un redéploiement) ne doit PAS effacer de bonnes actus."""
    _patch_claude_ok(monkeypatch)
    h, _ = _admin(client, "veille.resil@test.ci")
    ok = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert len(ok["news"]) == 2                      # bonne charge mise en cache

    # Claude tombe en panne ; même un refresh forcé conserve les actualités.
    async def _fail():
        return None, None
    monkeypatch.setattr(mi, "_call_claude_market", _fail)
    degraded = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert len(degraded["news"]) == 2               # actus conservées (dernière bonne charge)
    assert degraded.get("stale") is True
    assert "datées" in (degraded.get("note") or "")


def test_shared_cache(client, monkeypatch):
    _patch_claude_ok(monkeypatch)
    h, coop_id = _admin(client, "veille.cache@test.ci")
    client.get("/market/intelligence?refresh=true", headers=h)   # 1 appel facturé
    r2 = client.get("/market/intelligence", headers=h)           # sert le cache
    assert r2.json()["cached"] is True
    db = TestingSessionLocal()
    try:
        n = db.query(AiUsage).filter(
            AiUsage.feature == "market_intelligence", AiUsage.cooperative_id == coop_id).count()
        assert n == 1
    finally:
        db.close()


# ── Gating premium + auth ─────────────────────────────────────────────────────

def test_coop_price_from_purchases(client):
    """La veille expose le prix d'achat RÉEL de la coopérative (données Achats)."""
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


def test_db_cache_survives_redeploy(client, monkeypatch):
    """Les actualités persistées en DB survivent à un redéploiement (cache mémoire vidé)."""
    _patch_claude_ok(monkeypatch)
    h, _ = _admin(client, "veille.dbcache@test.ci")
    ok = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert len(ok["news"]) == 2  # bonne charge → persistée en DB

    # Simule un redéploiement : cache mémoire vidé + service IA en panne.
    mi._CACHE["data"] = None
    mi._CACHE["ts"] = 0.0
    mi._LAST_GOOD["data"] = None

    async def _fail():
        return None, None
    monkeypatch.setattr(mi, "_call_claude_market", _fail)

    after = client.get("/market/intelligence?refresh=true", headers=h).json()
    assert len(after["news"]) == 2          # actus resservies depuis la DB
    assert after.get("stale") is True


def test_available_on_all_plans(client):
    """Veille Marché est incluse dans TOUS les plans, y compris starter (décision produit)."""
    h, coop_id = _admin(client, "veille.allplans@test.ci", coop="Coop Veille All")
    assert client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "starter"}, headers=h).status_code == 200
    assert client.get("/market/intelligence", headers=h).status_code == 200


def test_requires_auth(client):
    assert client.get("/market/intelligence").status_code == 401
