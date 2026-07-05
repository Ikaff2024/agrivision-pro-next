"""Regle statut cooperatif (membre/non-membre) : recolte vs achat + pre-controle EUDR.

- MEMBRE      -> la coop organise la RECOLTE (achat interdit).
- NON-MEMBRE  -> on ACHETE sa production (recolte interdite ; l'achat cree la trace).
- Pre-controle EUDR : verdict deforestation d'une parcelle avant achat/integration.
"""


def _admin(client, email, coop="Coop Rule"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plantation(client, h, name="P-Rule", owner="Owner Rule"):
    return client.post("/plantations", json={
        "name": name, "owner_name": owner, "country": "Côte d'Ivoire",
        "region": "Soubré", "hectares": 2.0,
    }, headers=h).json()


def _set_type(client, h, producer_id, value):
    r = client.patch(f"/producers/{producer_id}/type",
                     json={"type_producteur": value}, headers=h)
    assert r.status_code == 200, r.text


def test_purchase_from_member_is_blocked(client):
    h = _admin(client, "rule.member@test.ci", coop="Coop RuleM")
    p = _plantation(client, h)
    # Producteur MEMBRE par defaut -> achat refuse.
    r = client.post("/purchases", json={
        "producer_id": p["producer_id"], "net_weight_kg": 80, "price_per_kg_fcfa": 1000,
    }, headers=h)
    assert r.status_code == 409, r.text
    assert "membre" in r.json()["detail"].lower()


def test_purchase_from_non_member_ok(client):
    h = _admin(client, "rule.nonmember@test.ci", coop="Coop RuleN")
    p = _plantation(client, h)
    _set_type(client, h, p["producer_id"], "non_membre")
    r = client.post("/purchases", json={
        "producer_id": p["producer_id"], "net_weight_kg": 80, "price_per_kg_fcfa": 1000,
    }, headers=h)
    assert r.status_code == 201, r.text


def test_harvest_on_non_member_parcel_is_blocked(client):
    h = _admin(client, "rule.harv@test.ci", coop="Coop RuleH")
    p = _plantation(client, h)
    _set_type(client, h, p["producer_id"], "non_membre")
    r = client.post(f"/plantations/{p['id']}/harvests", json={
        "harvest_date": "2025-11-01", "quantity_kg": 120, "quality": "Bonne",
    }, headers=h)
    assert r.status_code == 409, r.text
    assert "non-membre" in r.json()["detail"].lower()


def test_harvest_on_member_parcel_ok(client):
    h = _admin(client, "rule.harv.ok@test.ci", coop="Coop RuleHO")
    p = _plantation(client, h)  # membre par defaut
    r = client.post(f"/plantations/{p['id']}/harvests", json={
        "harvest_date": "2025-11-01", "quantity_kg": 120, "quality": "Bonne",
    }, headers=h)
    assert r.status_code == 201, r.text


def test_precheck_returns_verdict(client):
    h = _admin(client, "rule.pc@test.ci", coop="Coop RulePC")
    r = client.post("/satellite/precheck", json={"latitude": 5.78, "longitude": -6.59}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verdict"] in ("ELIGIBLE", "NON_ELIGIBLE", "INDETERMINE")
    assert "eligible" in d and "title" in d and "message" in d
    assert d["level"] in ("low", "medium", "high")


def test_precheck_requires_auth(client):
    assert client.post("/satellite/precheck", json={"latitude": 5.0, "longitude": -6.0}).status_code == 401
