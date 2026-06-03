"""Tests — suivi du cout de revient IA (API Claude) par cooperative."""
from datetime import datetime

from app.db.models import AiUsage, Cooperative
from app.services.ai_cost import compute_cost_usd, usd_to_fcfa, pricing_info
from tests.conftest import TestingSessionLocal


OWNER_KEY = "test-owner-key"


def _owner_h(key=OWNER_KEY):
    return {"X-Owner-Key": key}


def _admin(client, email, coop):
    """Cree une coop (fondateur=admin) et retourne (headers, cooperative_id)."""
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    coop_id = client.get("/me", headers=headers).json()["cooperative_id"]
    return headers, coop_id


def _seed_usage(cooperative_id, input_tokens, output_tokens):
    """Insere une ligne AiUsage avec le cout calcule, datee de maintenant."""
    db = TestingSessionLocal()
    try:
        u = AiUsage(
            cooperative_id=cooperative_id,
            feature="ai_advice",
            model="claude-sonnet-4-test",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=compute_cost_usd(input_tokens, output_tokens),
            created_at=datetime.utcnow(),
        )
        db.add(u)
        db.commit()
    finally:
        db.close()


# ─── Tests unitaires : calcul de cout ─────────────────────────────────────────

def test_compute_cost_default_pricing():
    # Tarifs par defaut Sonnet 4 : 3 USD/M input, 15 USD/M output
    assert compute_cost_usd(1_000_000, 0) == 3.0
    assert compute_cost_usd(0, 1_000_000) == 15.0
    assert compute_cost_usd(700, 1000) == round(700 / 1e6 * 3 + 1000 / 1e6 * 15, 6)


def test_compute_cost_handles_none_and_negative():
    assert compute_cost_usd(None, None) == 0.0
    assert compute_cost_usd(-100, -50) == 0.0


def test_usd_to_fcfa_default_rate():
    # Taux par defaut : 1 USD = 600 FCFA
    assert usd_to_fcfa(1.0) == 600.0
    assert usd_to_fcfa(0.0171) == round(0.0171 * 600, 2)


def test_pricing_info_shape():
    info = pricing_info()
    assert info["input_per_1m_usd"] == 3.0
    assert info["output_per_1m_usd"] == 15.0
    assert info["usd_to_fcfa_rate"] == 600.0


# ─── Tests endpoints owner ────────────────────────────────────────────────────

def test_owner_ai_cost_requires_key(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    assert client.get("/owner/ai-cost", headers=_owner_h("mauvaise")).status_code == 401


def test_owner_ai_cost_aggregates_by_cooperative(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    _, coop_a = _admin(client, "ai.a@test.ci", "Coop AI A")
    _, coop_b = _admin(client, "ai.b@test.ci", "Coop AI B")

    # Coop A : 2 appels ; Coop B : 1 appel
    _seed_usage(coop_a, 1000, 500)
    _seed_usage(coop_a, 2000, 1000)
    _seed_usage(coop_b, 700, 1000)

    r = client.get("/owner/ai-cost?from=2020-01-01&to=2030-12-31", headers=_owner_h())
    assert r.status_code == 200, r.text
    data = r.json()

    # Totaux
    assert data["totals"]["calls"] == 3
    assert data["totals"]["input_tokens"] == 1000 + 2000 + 700
    assert data["totals"]["output_tokens"] == 500 + 1000 + 1000
    expected_total = round(
        compute_cost_usd(1000, 500) + compute_cost_usd(2000, 1000) + compute_cost_usd(700, 1000), 4
    )
    assert data["totals"]["cost_usd"] == expected_total
    assert data["totals"]["cost_fcfa"] == usd_to_fcfa(expected_total)

    # Ventilation : coop A en premier (cout le plus eleve)
    by = {row["cooperative_id"]: row for row in data["by_cooperative"]}
    assert by[coop_a]["calls"] == 2
    assert by[coop_b]["calls"] == 1
    assert data["by_cooperative"][0]["cooperative_id"] == coop_a
    # Grille tarifaire exposee
    assert data["pricing"]["input_per_1m_usd"] == 3.0


def test_owner_cooperative_ai_cost_scoped(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    _, coop_a = _admin(client, "ai.scope.a@test.ci", "Coop Scope A")
    _, coop_b = _admin(client, "ai.scope.b@test.ci", "Coop Scope B")
    _seed_usage(coop_a, 1000, 500)
    _seed_usage(coop_b, 9999, 9999)

    r = client.get(f"/owner/cooperatives/{coop_a}/ai-cost?from=2020-01-01&to=2030-12-31", headers=_owner_h())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cooperative_id"] == coop_a
    assert data["totals"]["calls"] == 1
    assert data["totals"]["input_tokens"] == 1000
    assert data["totals"]["cost_usd"] == compute_cost_usd(1000, 500)


def test_owner_cooperative_ai_cost_unknown_coop_404(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    r = client.get("/owner/cooperatives/999999/ai-cost", headers=_owner_h())
    assert r.status_code == 404


# ─── Test integration : l'appel IA enregistre bien l'usage ────────────────────

def test_ai_advice_records_usage(client, monkeypatch):
    """L'endpoint /ai-advice doit persister une ligne AiUsage avec le cout calcule."""
    headers, coop_id = _admin(client, "ai.rec@test.ci", "Coop AI Rec")

    # Plantation de la coop
    p = client.post("/plantations", json={
        "name": "P IA", "owner_name": "O", "country": "CI", "hectares": 2.0,
    }, headers=headers).json()
    plantation_id = p["id"]

    # Mock de l'appel Claude : retourne (result, usage) sans reseau
    async def fake_get_ai_advice(*args, **kwargs):
        return (
            {"resume": "Etat correct", "score_potentiel": 80},
            {"model": "claude-sonnet-4-test", "input_tokens": 1000, "output_tokens": 500},
        )
    monkeypatch.setattr("app.api.routes.get_ai_advice", fake_get_ai_advice)

    r = client.post(f"/plantations/{plantation_id}/ai-advice", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["score_potentiel"] == 80

    # Verification en base
    db = TestingSessionLocal()
    try:
        rows = db.query(AiUsage).filter(AiUsage.cooperative_id == coop_id).all()
        assert len(rows) == 1
        assert rows[0].input_tokens == 1000
        assert rows[0].output_tokens == 500
        assert rows[0].cost_usd == compute_cost_usd(1000, 500)
        assert rows[0].plantation_id == plantation_id
    finally:
        db.close()
