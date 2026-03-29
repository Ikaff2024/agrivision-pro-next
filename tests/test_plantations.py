"""Tests d'intégration — plantations."""


def test_create_plantation(client, auth_headers):
    res = client.post("/plantations", json={
        "name": "Plantation Soubré",
        "owner_name": "Yao Kouamé",
        "country": "Côte d'Ivoire",
        "region": "Soubré",
        "latitude": 5.78,
        "longitude": -6.59,
        "hectares": 3.0,
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Plantation Soubré"
    assert data["cooperative_id"] is not None  # toujours rattachée


def test_create_plantation_requires_admin(client, auth_headers):
    # L'agronome rejoint la coop existante → reste agronomist → ne peut pas créer
    client.post("/auth/register", json={
        "email": "agro@test.ci",
        "password": "pass123",
        "role": "agronomist",
        "cooperative_name": "Coop Test Fixture",  # coop existante → pas admin
        "country": "Côte d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "agro@test.ci", "password": "pass123"
    }).json()["access_token"]

    res = client.post("/plantations", json={
        "name": "P", "owner_name": "O", "country": "CI"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_get_plantations(client, auth_headers, plantation_id):
    res = client.get("/plantations", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert any(p["id"] == plantation_id for p in res.json())


def test_get_plantation_by_id(client, auth_headers, plantation_id):
    res = client.get(f"/plantations/{plantation_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["plantation"]["id"] == plantation_id


def test_get_plantation_not_found(client, auth_headers):
    res = client.get("/plantations/99999", headers=auth_headers)
    assert res.status_code == 404


def test_cooperative_isolation(client):
    """Deux coopératives distinctes ne voient pas les plantations de l'autre."""
    # Coop A
    client.post("/auth/register", json={
        "email": "admin_a@test.ci", "password": "pass123",
        "role": "admin", "cooperative_name": "Coop A", "country": "CI"
    })
    token_a = client.post("/auth/login", json={
        "email": "admin_a@test.ci", "password": "pass123"
    }).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Coop B
    client.post("/auth/register", json={
        "email": "admin_b@test.ci", "password": "pass123",
        "role": "admin", "cooperative_name": "Coop B", "country": "CI"
    })
    token_b = client.post("/auth/login", json={
        "email": "admin_b@test.ci", "password": "pass123"
    }).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Coop A crée une plantation
    client.post("/plantations", json={
        "name": "Plantation A", "owner_name": "A", "country": "CI"
    }, headers=headers_a)

    # Coop B ne doit pas la voir
    res = client.get("/plantations", headers=headers_b)
    assert all(p["name"] != "Plantation A" for p in res.json())
