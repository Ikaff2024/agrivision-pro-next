"""Signalement PUBLIC sans compte — rattachement à la BONNE coopérative + cloisonnement."""
import base64
import json


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    coop_id = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "==")).get("coop_id")
    return {"Authorization": "Bearer " + tok}, coop_id


def _token(client, headers, coop_id):
    r = client.post(f"/cooperatives/{coop_id}/public-report-token", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["public_report_token"]


def test_public_report_attaches_to_correct_coop(client):
    ha, coop_a = _admin(client, "pub.a@test.ci", "Coop Pub A")
    hb, coop_b = _admin(client, "pub.b@test.ci", "Coop Pub B")
    token_a = _token(client, ha, coop_a)
    assert token_a and len(token_a) >= 8

    # Le lien public expose bien le nom de la coop A.
    info = client.get(f"/public/report-info?c={token_a}")
    assert info.status_code == 200 and info.json()["cooperative_name"] == "Coop Pub A"

    # Signalement public (sans auth) via le jeton de A.
    r = client.post("/public/complaints", json={
        "coop_token": token_a, "complaint_type": "child_labor", "severity": "high",
        "description": "Enfant vu à la machette près du campement.",
    })
    assert r.status_code == 201, r.text
    assert r.json()["reference"]

    # A le voit ; B ne le voit PAS (rattachement direct à la coop A).
    list_a = client.get("/complaints", headers=ha).json()
    list_b = client.get("/complaints", headers=hb).json()
    assert any("child_labor" == c.get("complaint_type") for c in list_a), "A doit voir son signalement public"
    ids_a = {c["id"] for c in list_a}
    ids_b = {c["id"] for c in list_b}
    assert ids_a and ids_a.isdisjoint(ids_b), "Fuite : B ne doit voir aucun signalement de A"


def test_public_report_invalid_token(client):
    assert client.get("/public/report-info?c=doesnotexist").status_code == 404
    r = client.post("/public/complaints", json={
        "coop_token": "bad-token-xyz", "description": "Test description ok longueur.",
    })
    assert r.status_code == 404


def test_public_token_requires_admin(client):
    from tests.conftest import create_member_headers
    ha, coop_a = _admin(client, "pub.founder@test.ci", "Coop Pub R")
    h_tech = create_member_headers(client, ha, "pub.tech@test.ci", "technician")
    r = client.post(f"/cooperatives/{coop_a}/public-report-token", headers=h_tech)
    assert r.status_code == 403
