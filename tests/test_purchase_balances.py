"""Tests — soldes de paiement par producteur + règlement groupé (module Achats)."""
from tests.conftest import create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _producer_id(client, headers):
    """Crée une plantation (auto-crée un producteur) et renvoie son id."""
    client.post("/plantations", json={
        "name": "Parcelle Pay", "owner_name": "Producteur Pay",
        "country": "CI", "region": "Yeyasso", "hectares": 2.0,
    }, headers=headers)
    return client.get("/producers?limit=50", headers=headers).json()[0]["id"]


def _purchase(client, headers, producer_id, net, price, status="pending"):
    r = client.post("/purchases", json={
        "producer_id": producer_id, "net_weight_kg": net,
        "price_per_kg_fcfa": price, "payment_status": status,
    }, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_producer_balances_aggregates_outstanding(client):
    h = _admin(client, "pay.admin@test.ci", "Coop Pay")
    pid = _producer_id(client, h)
    _purchase(client, h, pid, 100, 1000, "pending")  # 100 000 dû
    _purchase(client, h, pid, 50, 1000, "pending")   # 50 000 dû
    _purchase(client, h, pid, 30, 1000, "paid")      # 30 000 payé

    body = client.get("/purchases/producer-balances", headers=h).json()
    assert len(body["producers"]) == 1
    p = body["producers"][0]
    assert p["producer_id"] == pid
    assert p["purchases"] == 3
    assert p["pending_amount_fcfa"] == 150000
    assert p["pending_count"] == 2
    assert p["paid_amount_fcfa"] == 30000
    assert p["total_amount_fcfa"] == 180000
    assert body["totals"]["producers_with_outstanding"] == 1
    assert body["totals"]["outstanding_amount_fcfa"] == 150000


def test_settle_producer_clears_pending(client):
    h = _admin(client, "pay.settle@test.ci", "Coop Pay Settle")
    pid = _producer_id(client, h)
    _purchase(client, h, pid, 100, 1000, "pending")
    _purchase(client, h, pid, 50, 1000, "pending")

    r = client.post(f"/purchases/producer/{pid}/settle", json={"payment_method": "cash"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["settled_count"] == 2
    assert r.json()["settled_amount_fcfa"] == 150000

    # Plus rien en attente.
    body = client.get("/purchases/producer-balances", headers=h).json()
    assert body["producers"][0]["pending_amount_fcfa"] == 0
    assert body["totals"]["producers_with_outstanding"] == 0


def test_settle_requires_admin(client):
    h_admin = _admin(client, "pay.founder@test.ci", "Coop Pay Role")
    pid = _producer_id(client, h_admin)
    _purchase(client, h_admin, pid, 100, 1000, "pending")
    h_tech = create_member_headers(client, h_admin, "pay.tech@test.ci", "technician")
    r = client.post(f"/purchases/producer/{pid}/settle", json={}, headers=h_tech)
    assert r.status_code == 403


def test_settle_unknown_producer_404(client):
    h = _admin(client, "pay.404@test.ci", "Coop Pay 404")
    assert client.post("/purchases/producer/999999/settle", json={}, headers=h).status_code == 404


def test_balances_requires_auth(client):
    assert client.get("/purchases/producer-balances").status_code == 401


def test_balances_scoped_to_coop(client):
    h_a = _admin(client, "pay.a@test.ci", "Coop Pay A")
    pid_a = _producer_id(client, h_a)
    _purchase(client, h_a, pid_a, 100, 1000, "pending")
    h_b = _admin(client, "pay.b@test.ci", "Coop Pay B")
    # B ne voit aucun solde (coop vide)
    body = client.get("/purchases/producer-balances", headers=h_b).json()
    assert body["producers"] == []
