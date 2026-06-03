"""Tests d'integration — tracabilite des lots (module #1)."""

from tests.conftest import create_member_headers


def _login(client, email, password="pass1234", role="admin", coop="Coop Lots"):
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


def _harvest(client, h, plantation_id, qty=500.0):
    return client.post(f"/plantations/{plantation_id}/harvests", json={
        "harvest_date": "2026-01-15T00:00:00", "quantity_kg": qty, "quality": "Bonne",
    }, headers=h).json()


def test_warehouse_crud_scoped(client):
    h = _login(client, "lot.w@test.ci", coop="Coop W")
    r = client.post("/warehouses", json={"name": "Magasin Central", "location": "Man", "capacity_kg": 50000}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Magasin Central"
    lst = client.get("/warehouses", headers=h)
    assert lst.status_code == 200 and len(lst.json()) == 1


def test_create_lot_with_harvests_and_totals(client):
    h = _login(client, "lot.c@test.ci", coop="Coop C")
    p = _plantation(client, h)
    h1 = _harvest(client, h, p["id"], 500)
    h2 = _harvest(client, h, p["id"], 300)
    r = client.post("/lots", json={"season": "2025-2026", "harvest_ids": [h1["id"], h2["id"]]}, headers=h)
    assert r.status_code == 201, r.text
    lot = r.json()
    assert lot["code"].startswith("LOT-")
    assert lot["total_weight_kg"] == 800.0
    assert lot["harvest_count"] == 2
    assert any(m["movement_type"] == "creation" for m in lot["movements"])


def test_lot_passport_structure(client):
    h = _login(client, "lot.pp@test.ci", coop="Coop PP")
    p = _plantation(client, h)
    hv = _harvest(client, h, p["id"], 1000)
    lot = client.post("/lots", json={"harvest_ids": [hv["id"]]}, headers=h).json()
    r = client.get(f"/lots/{lot['id']}/passport", headers=h)
    assert r.status_code == 200, r.text
    pp = r.json()
    assert pp["summary"]["total_weight_kg"] == 1000.0
    assert pp["summary"]["producers"] == 1
    assert len(pp["composition"]) == 1
    assert "eudr_compliance_rate_pct" in pp["summary"]


def test_lot_passport_pdf(client):
    h = _login(client, "lot.pdf@test.ci", coop="Coop PDF")
    p = _plantation(client, h)
    hv = _harvest(client, h, p["id"], 500)
    lot = client.post("/lots", json={"harvest_ids": [hv["id"]]}, headers=h).json()
    r = client.get(f"/lots/{lot['id']}/passport.pdf", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "Passeport_" in r.headers.get("content-disposition", "")


def test_lot_merge(client):
    h = _login(client, "lot.m@test.ci", coop="Coop M")
    p = _plantation(client, h)
    hv1 = _harvest(client, h, p["id"], 400)
    hv2 = _harvest(client, h, p["id"], 600)
    l1 = client.post("/lots", json={"harvest_ids": [hv1["id"]]}, headers=h).json()
    l2 = client.post("/lots", json={"harvest_ids": [hv2["id"]]}, headers=h).json()
    r = client.post("/lots/merge", json={"source_lot_ids": [l1["id"], l2["id"]]}, headers=h)
    assert r.status_code == 201, r.text
    target = r.json()
    assert target["total_weight_kg"] == 1000.0
    assert any(m["movement_type"] == "merge_in" for m in target["movements"])
    # Les lots sources passent en 'merged' et sont vides
    s1 = client.get(f"/lots/{l1['id']}", headers=h).json()
    assert s1["status"] == "merged" and s1["total_weight_kg"] == 0


def test_lot_movements_and_status(client):
    h = _login(client, "lot.mv@test.ci", coop="Coop MV")
    p = _plantation(client, h)
    hv = _harvest(client, h, p["id"], 700)
    wh = client.post("/warehouses", json={"name": "Magasin"}, headers=h).json()
    lot = client.post("/lots", json={"harvest_ids": [hv["id"]]}, headers=h).json()
    # entree magasin
    r1 = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "warehouse_in", "to_warehouse_id": wh["id"]}, headers=h)
    assert r1.status_code == 200 and r1.json()["warehouse_id"] == wh["id"]
    # scellage puis expedition
    client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "seal"}, headers=h)
    r3 = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "export_out", "reference": "BL-001"}, headers=h)
    assert r3.json()["status"] == "shipped"
    r4 = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "wrong"}, headers=h)
    assert r4.status_code == 400


def test_lot_blocks_child_labor_producer(client):
    """Un producteur sous blocage CacaoGuard ne peut pas etre affecte a un lot."""
    h = _login(client, "lot.block@test.ci", coop="Coop Block")
    p = _plantation(client, h)
    hv = _harvest(client, h, p["id"], 500)
    producer_id = p["producer_id"]
    # Cree un blocage de tracabilite actif sur ce producteur
    blk = client.post("/compliance/blocks", json={
        "producer_id": producer_id, "block_description": "Cas travail enfant",
    }, headers=h)
    assert blk.status_code in (200, 201), blk.text
    # L'affectation au lot doit etre refusee (409)
    r = client.post("/lots", json={"harvest_ids": [hv["id"]]}, headers=h)
    assert r.status_code == 409, r.text
    assert "blocked_producers" in str(r.json())


def test_lot_requires_auth_and_role(client):
    assert client.get("/lots").status_code == 401
    h_admin = _login(client, "lot.founder@test.ci", coop="Coop Tech L")
    h_tech = create_member_headers(client, h_admin, "lot.tech@test.ci", "technician")
    # lecture autorisee
    assert client.get("/lots", headers=h_tech).status_code == 200
    # creation interdite au technicien
    assert client.post("/lots", json={"harvest_ids": []}, headers=h_tech).status_code == 403
