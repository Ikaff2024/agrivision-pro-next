"""Tests d'intégration — authentification."""


def test_register_success(client):
    res = client.post("/auth/register", json={
        "email": "user@test.ci",
        "password": "pass1234",
        "role": "agronomist",
        "cooperative_name": "Coop CI",
        "country": "Côte d'Ivoire",
    })
    assert res.status_code == 201
    assert "user_id" in res.json()


def test_register_duplicate_email(client):
    payload = {
        "email": "dup@test.ci",
        "password": "pass",
        "role": "admin",
        "cooperative_name": "Coop X",
        "country": "Côte d'Ivoire",
    }
    client.post("/auth/register", json=payload)
    res = client.post("/auth/register", json=payload)
    assert res.status_code == 400


def test_register_invalid_role(client):
    res = client.post("/auth/register", json={
        "email": "bad@test.ci",
        "password": "pass",
        "role": "superuser",          # rôle inexistant
        "cooperative_name": "Coop X",
        "country": "Côte d'Ivoire",
    })
    assert res.status_code == 400


def test_login_success(client):
    client.post("/auth/register", json={
        "email": "login@test.ci",
        "password": "mypassword",
        "role": "admin",
        "cooperative_name": "Coop L",
        "country": "Côte d'Ivoire",
    })
    res = client.post("/auth/login", json={
        "email": "login@test.ci",
        "password": "mypassword",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()
    assert res.json()["token_type"] == "bearer"


def test_login_wrong_password(client):
    client.post("/auth/register", json={
        "email": "wp@test.ci",
        "password": "correct",
        "role": "admin",
        "cooperative_name": "C",
        "country": "CI",
    })
    res = client.post("/auth/login", json={
        "email": "wp@test.ci",
        "password": "wrong",
    })
    assert res.status_code == 401


def test_protected_route_without_token(client):
    res = client.get("/plantations")
    assert res.status_code == 401


def test_protected_route_with_invalid_token(client):
    res = client.get("/plantations", headers={"Authorization": "Bearer fake.token.here"})
    assert res.status_code == 401
