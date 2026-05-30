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


def _register_login(client, email, password, role="admin", coop="Coop PW"):
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_change_password_success(client):
    h = _register_login(client, "chg@test.ci", "oldpass1")
    res = client.post("/auth/change-password", json={
        "current_password": "oldpass1", "new_password": "newpass2",
    }, headers=h)
    assert res.status_code == 200, res.text
    # L'ancien mot de passe ne marche plus, le nouveau oui.
    assert client.post("/auth/login", json={"email": "chg@test.ci", "password": "oldpass1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "chg@test.ci", "password": "newpass2"}).status_code == 200


def test_change_password_wrong_current(client):
    h = _register_login(client, "chg2@test.ci", "oldpass1")
    res = client.post("/auth/change-password", json={
        "current_password": "WRONG", "new_password": "newpass2",
    }, headers=h)
    assert res.status_code == 401


def test_change_password_too_short(client):
    h = _register_login(client, "chg3@test.ci", "oldpass1")
    res = client.post("/auth/change-password", json={
        "current_password": "oldpass1", "new_password": "123",
    }, headers=h)
    assert res.status_code == 400


def test_protected_route_without_token(client):
    res = client.get("/plantations")
    assert res.status_code == 401


def test_protected_route_with_invalid_token(client):
    res = client.get("/plantations", headers={"Authorization": "Bearer fake.token.here"})
    assert res.status_code == 401
