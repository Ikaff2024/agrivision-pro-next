"""Tests d'integration — tableau de bord direction (lecture seule, scope coop)."""

from tests.conftest import create_member_headers


def _register_login(client, email, password, role="admin", coop="Coop Dash"):
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_direction_dashboard_requires_auth(client):
    res = client.get("/dashboard/direction")
    assert res.status_code == 401


def test_direction_dashboard_structure(client):
    h = _register_login(client, "dir.admin@test.ci", "pass1234")
    res = client.get("/dashboard/direction", headers=h)
    assert res.status_code == 200, res.text
    data = res.json()
    for key in ("perimeter", "eudr", "child_protection", "living_income", "volume", "alerts"):
        assert key in data, f"clé manquante : {key}"
    assert data["scope"] == "cooperative"
    # Coopérative neuve => périmètre vide mais structure complète
    assert data["perimeter"]["producers_active"] == 0
    assert data["eudr"]["compliance_rate_pct"] == 0.0
    assert data["living_income"]["assessments"] == 0
    assert data["volume"]["total_kg"] == 0
    # Volume non tracé : présent dans la structure, nul sur coop neuve.
    assert data["volume"]["untracked_kg"] == 0
    assert data["volume"]["untracked_rate_pct"] == 0.0


def test_direction_dashboard_reflects_plantation(client):
    h = _register_login(client, "dir.admin2@test.ci", "pass1234", coop="Coop Dash 2")
    # Création d'une plantation via l'API (producteur auto-créé + lien coop)
    created = client.post("/plantations", json={
        "name": "Parcelle Dir", "owner_name": "Kouassi Dir",
        "country": "Côte d'Ivoire", "region": "Yeyasso", "hectares": 4.0,
    }, headers=h)
    assert created.status_code in (200, 201), created.text

    res = client.get("/dashboard/direction", headers=h)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["perimeter"]["plantations"] >= 1
    assert data["perimeter"]["total_hectares"] >= 4.0


def test_direction_dashboard_untracked_volume(client):
    """Une récolte non affectée à un lot apparaît dans le volume non tracé."""
    h = _register_login(client, "dir.vol@test.ci", "pass1234", coop="Coop Vol")
    created = client.post("/plantations", json={
        "name": "Parcelle Vol", "owner_name": "Yao Vol",
        "country": "Côte d'Ivoire", "region": "Yeyasso", "hectares": 3.0,
    }, headers=h)
    assert created.status_code in (200, 201), created.text
    pid = created.json()["id"]

    harv = client.post(f"/plantations/{pid}/harvests", json={
        "harvest_date": "2026-01-15T08:00:00", "quantity_kg": 500.0, "quality": "Bonne",
    }, headers=h)
    assert harv.status_code in (200, 201), harv.text

    data = client.get("/dashboard/direction", headers=h).json()
    # Récolte non rattachée à un lot => comptée comme non tracée (= total ici).
    assert data["volume"]["total_kg"] == 500.0
    assert data["volume"]["untracked_kg"] == 500.0
    assert data["volume"]["untracked_rate_pct"] == 100.0


def test_direction_dashboard_forbidden_for_technician(client):
    h_admin = _register_login(client, "dir.founder@test.ci", "pass1234", coop="Coop Tech")
    h_tech = create_member_headers(client, h_admin, "dir.tech@test.ci", "technician")
    res = client.get("/dashboard/direction", headers=h_tech)
    assert res.status_code == 403
