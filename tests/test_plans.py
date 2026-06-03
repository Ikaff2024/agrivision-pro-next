"""Tests — plans d'abonnement & feature-gating."""
from app.services.plans import allowed_modules, has_module, normalize_plan, plan_overview
from tests.conftest import create_member_headers


def _login(client, email, coop="Coop Plan", role="admin"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


# ── Catalogue (unitaire) ─────────────────────────────────────────────────────

def test_starter_plan_is_core_only():
    mods = set(allowed_modules("starter"))
    assert "plantations" in mods and "diagnostic" in mods
    assert "lots" not in mods and "satellite" not in mods and "cacaoguard" not in mods


def test_pro_includes_commercial_not_premium():
    assert has_module("pro", "lots") and has_module("pro", "purchases")
    assert not has_module("pro", "satellite")  # premium


def test_enterprise_includes_everything():
    for m in ["plantations", "cacaoguard", "lots", "satellite", "farmforce", "direction"]:
        assert has_module("enterprise", m)


def test_unknown_plan_defaults_enterprise():
    assert normalize_plan("bidon") == "enterprise"
    assert normalize_plan(None) == "enterprise"


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_me_features_default_enterprise(client):
    h = _login(client, "plan.ent@test.ci", coop="Coop Ent")
    r = client.get("/me/features", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plan"] == "enterprise"
    assert "satellite" in d["modules"] and "lots" in d["modules"]


def test_set_plan_and_features_reflect(client):
    h = _login(client, "plan.set@test.ci", coop="Coop Set")
    # Recupere l'id de coop via /me
    coop_id = client.get("/me", headers=h).json()["cooperative_id"]
    r = client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "starter"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "starter"
    # Les features refletent le downgrade
    feats = client.get("/me/features", headers=h).json()
    assert feats["plan"] == "starter"
    assert "lots" not in feats["modules"] and "satellite" not in feats["modules"]
    assert "plantations" in feats["modules"]


def test_set_plan_invalid(client):
    h = _login(client, "plan.inv@test.ci", coop="Coop PlanInv")
    coop_id = client.get("/me", headers=h).json()["cooperative_id"]
    r = client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "ultra"}, headers=h)
    assert r.status_code == 400


def test_set_plan_requires_admin(client):
    h_admin = _login(client, "plan.founder@test.ci", coop="Coop PlanRole")
    h_tech = create_member_headers(client, h_admin, "plan.tech@test.ci", "technician")
    coop_id = client.get("/me", headers=h_tech).json()["cooperative_id"]
    r = client.patch(f"/cooperatives/{coop_id}/plan", json={"plan": "pro"}, headers=h_tech)
    assert r.status_code == 403


def test_me_features_requires_auth(client):
    assert client.get("/me/features").status_code == 401
