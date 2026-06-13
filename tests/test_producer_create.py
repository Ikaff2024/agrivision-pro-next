"""Création directe d'un producteur (sans passer par une parcelle)."""

from tests.conftest import create_member_headers


def _login(client, email="prod.admin@test.ci", coop="Coop Prod"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_create_producer_direct_and_listed(client):
    h = _login(client)
    r = client.post("/producers", json={
        "nom_complet": "Kouassi Konan", "code_yeyasso": "YEY-001",
        "localite": "Soubré", "telephone": "0700000000", "sexe": "H",
    }, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["nom_complet"] == "Kouassi Konan"
    assert r.json()["code_yeyasso"] == "YEY-001"

    # Apparaît immédiatement dans l'annuaire.
    listed = client.get("/producers", headers=h).json()
    assert pid in [p["id"] for p in listed]

    # Dédoublonnage sur le code interne → 409.
    dup = client.post("/producers", json={"nom_complet": "Homonyme", "code_yeyasso": "YEY-001"}, headers=h)
    assert dup.status_code == 409


def test_create_producer_requires_name(client):
    h = _login(client, "prod.name@test.ci", "Coop Name")
    r = client.post("/producers", json={"nom_complet": "A"}, headers=h)  # < 2 caractères
    assert r.status_code == 422


def test_create_producer_requires_auth(client):
    r = client.post("/producers", json={"nom_complet": "Sans authentification"})
    assert r.status_code in (401, 403)


def test_create_producer_technician_and_gestionnaire_allowed(client):
    h_admin = _login(client, "prod.founder@test.ci", "Coop Roles P")
    h_tech = create_member_headers(client, h_admin, "prod.tech@test.ci", "technician")
    h_gest = create_member_headers(client, h_admin, "prod.gest@test.ci", "gestionnaire")
    assert client.post("/producers", json={"nom_complet": "Par technicien"}, headers=h_tech).status_code == 201
    assert client.post("/producers", json={"nom_complet": "Par gestionnaire"}, headers=h_gest).status_code == 201


def test_create_producer_cooperative_scoped(client):
    """Le producteur créé n'est visible que dans sa coopérative."""
    ha = _login(client, "prod.a@test.ci", "Coop P A")
    hb = _login(client, "prod.b@test.ci", "Coop P B")
    pid = client.post("/producers", json={"nom_complet": "Visible A"}, headers=ha).json()["id"]
    assert pid not in [p["id"] for p in client.get("/producers", headers=hb).json()]
