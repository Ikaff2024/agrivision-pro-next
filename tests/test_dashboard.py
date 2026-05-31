"""Tests d'integration — tableau de bord direction (lecture seule, scope coop)."""


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


def test_direction_dashboard_forbidden_for_technician(client):
    # Admin fondateur crée la coop, puis un technicien rejoint la même coop
    _register_login(client, "dir.founder@test.ci", "pass1234", coop="Coop Tech")
    h_tech = _register_login(client, "dir.tech@test.ci", "pass1234", role="technician", coop="Coop Tech")
    res = client.get("/dashboard/direction", headers=h_tech)
    assert res.status_code == 403
