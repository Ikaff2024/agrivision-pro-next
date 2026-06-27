"""Profil de la coopérative : renommage + responsables (managers)."""
from tests.conftest import create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    cid = client.get("/me", headers=h).json()["cooperative_id"]
    return h, cid


def test_update_name_and_managers(client):
    h, cid = _admin(client, "coop.profile@test.ci", "Vieux Nom Coop")
    r = client.patch(f"/cooperatives/{cid}/profile", json={
        "name": "Nouveau Nom Coop", "country": "Côte d'Ivoire",
        "managers": [
            {"name": "Kouadio Yao", "role": "Président", "phone": "0700000000"},
            {"name": "Aya Koffi", "role": "Directrice"},
            {"name": "   "},   # ignoré (sans nom)
        ],
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Nouveau Nom Coop"
    assert len(body["managers"]) == 2
    assert body["managers"][0]["name"] == "Kouadio Yao"
    assert body["managers"][0]["role"] == "Président"

    got = client.get(f"/cooperatives/{cid}/profile", headers=h).json()
    assert got["name"] == "Nouveau Nom Coop"
    assert got["country"] == "Côte d'Ivoire"
    assert got["managers"][1]["name"] == "Aya Koffi"


def test_name_cannot_be_empty(client):
    h, cid = _admin(client, "coop.empty@test.ci", "Coop X prof")
    assert client.patch(f"/cooperatives/{cid}/profile", json={"name": "   "}, headers=h).status_code == 400


def test_cross_coop_forbidden(client):
    ha, ca = _admin(client, "coop.a@test.ci", "Coop A prof")
    hb, cb = _admin(client, "coop.b@test.ci", "Coop B prof")
    assert client.patch(f"/cooperatives/{ca}/profile", json={"name": "Hack"}, headers=hb).status_code == 403


def test_requires_admin_to_edit(client):
    ha, ca = _admin(client, "coop.adm@test.ci", "Coop Adm prof")
    h_ag = create_member_headers(client, ha, "agro.prof@test.ci", "agronomist")
    # Lecture autorisée pour un membre, mais édition réservée admin.
    assert client.get(f"/cooperatives/{ca}/profile", headers=h_ag).status_code == 200
    assert client.patch(f"/cooperatives/{ca}/profile", json={"name": "X"}, headers=h_ag).status_code == 403


def test_requires_auth(client):
    ha, ca = _admin(client, "coop.auth@test.ci", "Coop Auth prof")
    assert client.get(f"/cooperatives/{ca}/profile").status_code in (401, 403)
