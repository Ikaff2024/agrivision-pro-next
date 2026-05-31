"""Tests d'integration — achats producteurs (module #2)."""


def _login(client, email, password="pass1234", role="admin", coop="Coop Buy"):
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plantation(client, h, name="P1", owner="Kouassi"):
    return client.post("/plantations", json={
        "name": name, "owner_name": owner, "country": "Côte d'Ivoire",
        "region": "Yeyasso", "hectares": 3.0,
    }, headers=h).json()


def test_purchase_requires_auth(client):
    assert client.get("/purchases").status_code == 401


def test_create_purchase_computes_total_and_net(client):
    h = _login(client, "buy.c@test.ci", coop="Coop Buy C")
    p = _plantation(client, h)
    r = client.post("/purchases", json={
        "producer_id": p["producer_id"], "plantation_id": p["id"],
        "gross_weight_kg": 105, "tare_kg": 5, "price_per_kg_fcfa": 1000,
        "bag_count": 2, "quality": "Bonne", "season": "2025-2026",
    }, headers=h)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["net_weight_kg"] == 100.0          # 105 - 5
    assert d["total_amount_fcfa"] == 100000.0   # 100 * 1000
    assert d["harvest_id"] is not None          # recolte generee
    assert d["payment_status"] == "pending"


def test_purchase_generates_traceable_harvest(client):
    h = _login(client, "buy.h@test.ci", coop="Coop Buy H")
    p = _plantation(client, h)
    pr = client.post("/purchases", json={
        "producer_id": p["producer_id"], "plantation_id": p["id"],
        "net_weight_kg": 250, "price_per_kg_fcfa": 900,
    }, headers=h).json()
    # La recolte generee est visible et affectable a un lot
    hv = client.get(f"/plantations/{p['id']}/harvests", headers=h).json()
    assert any(x["id"] == pr["harvest_id"] for x in hv)
    lot = client.post("/lots", json={"harvest_ids": [pr["harvest_id"]]}, headers=h)
    assert lot.status_code == 201
    assert lot.json()["total_weight_kg"] == 250.0


def test_purchase_summary(client):
    h = _login(client, "buy.s@test.ci", coop="Coop Buy S")
    p = _plantation(client, h)
    base = {"producer_id": p["producer_id"], "plantation_id": p["id"], "price_per_kg_fcfa": 1000}
    client.post("/purchases", json={**base, "net_weight_kg": 100, "payment_status": "paid"}, headers=h)
    client.post("/purchases", json={**base, "net_weight_kg": 50}, headers=h)
    s = client.get("/purchases/summary", headers=h).json()
    assert s["purchases"] == 2
    assert s["total_net_kg"] == 150.0
    assert s["total_amount_fcfa"] == 150000.0
    assert s["paid_count"] == 1 and s["pending_count"] == 1


def test_purchase_mark_paid(client):
    h = _login(client, "buy.p@test.ci", coop="Coop Buy P")
    p = _plantation(client, h)
    pr = client.post("/purchases", json={
        "producer_id": p["producer_id"], "net_weight_kg": 80, "price_per_kg_fcfa": 1000,
        "create_harvest": False,
    }, headers=h).json()
    assert pr["payment_status"] == "pending"
    r = client.post(f"/purchases/{pr['id']}/mark-paid", json={"payment_method": "mobile_money"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["payment_status"] == "paid"
    assert r.json()["payment_method"] == "mobile_money"


def test_purchase_net_weight_required(client):
    h = _login(client, "buy.n@test.ci", coop="Coop Buy N")
    p = _plantation(client, h)
    r = client.post("/purchases", json={"producer_id": p["producer_id"]}, headers=h)
    assert r.status_code == 400


def test_purchase_flags_blocked_producer(client):
    h = _login(client, "buy.b@test.ci", coop="Coop Buy B")
    p = _plantation(client, h)
    client.post("/compliance/blocks", json={
        "producer_id": p["producer_id"], "block_description": "Cas travail enfant",
    }, headers=h)
    pr = client.post("/purchases", json={
        "producer_id": p["producer_id"], "net_weight_kg": 60, "create_harvest": False,
    }, headers=h).json()
    # L'achat est enregistre mais signale le blocage (drapeau, pas de hard-block)
    assert pr["producer_blocked"] is True
