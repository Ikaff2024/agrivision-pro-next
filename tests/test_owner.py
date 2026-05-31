"""Tests — dashboard proprietaire (IKAFFANAN) : stats enrichies + plan."""
import os


KEY = "test-owner-key"


def _setup_key(monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", KEY)


def _h(key=KEY):
    return {"X-Owner-Key": key}


def test_owner_stats_requires_key(client, monkeypatch):
    _setup_key(monkeypatch)
    assert client.get("/owner/stats", headers=_h("mauvaise")).status_code == 401


def test_owner_stats_enriched_kpis(client, monkeypatch):
    _setup_key(monkeypatch)
    # cree une coop via inscription
    client.post("/auth/register", json={
        "email": "owner.kpi@test.ci", "password": "pass1234", "role": "admin",
        "cooperative_name": "Coop Owner KPI", "country": "CI",
    })
    r = client.get("/owner/stats", headers=_h())
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    # Nouveaux KPIs presents
    for key in ("total_producers", "total_children", "high_risk_children",
                "active_traceability_blocks", "total_lots",
                "total_purchase_volume_kg", "total_purchase_amount_fcfa"):
        assert key in s, f"KPI manquant : {key}"
    assert "plan_distribution" in r.json()
    # chaque coop expose son plan
    assert all("plan" in c for c in r.json()["cooperatives"])


def test_owner_set_plan(client, monkeypatch):
    _setup_key(monkeypatch)
    client.post("/auth/register", json={
        "email": "owner.plan@test.ci", "password": "pass1234", "role": "admin",
        "cooperative_name": "Coop Owner Plan", "country": "CI",
    })
    coops = client.get("/owner/stats", headers=_h()).json()["cooperatives"]
    coop = [c for c in coops if c["name"] == "Coop Owner Plan"][0]
    assert coop["plan"] == "enterprise"  # defaut

    r = client.put(f"/owner/cooperatives/{coop['id']}/plan", json={"plan": "pro"}, headers=_h())
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "pro"

    # invalide
    r2 = client.put(f"/owner/cooperatives/{coop['id']}/plan", json={"plan": "vip"}, headers=_h())
    assert r2.status_code == 400


def test_owner_set_plan_requires_key(client, monkeypatch):
    _setup_key(monkeypatch)
    r = client.put("/owner/cooperatives/1/plan", json={"plan": "pro"}, headers=_h("x"))
    assert r.status_code == 401
