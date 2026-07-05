"""Anti-doublon achat ↔ récolte (intégrité des volumes).

Un achat avec parcelle génère une récolte. Si on enregistre une récolte PUIS un
achat sur la même parcelle/campagne, on crée 2 récoltes pour le même cacao →
volume doublé. Le lien `harvest_id` permet de RATTACHER l'achat à la récolte
existante au lieu d'en recréer une (cf. garde-fou « alerte + lien » du frontend).
"""


def _login(client, email, coop="Coop Dedup"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plantation(client, h, name="P-Dedup", owner="Yao Dedup"):
    return client.post("/plantations", json={
        "name": name, "owner_name": owner, "country": "Côte d'Ivoire",
        "region": "Soubré", "hectares": 2.0,
    }, headers=h).json()


def _producer_id(client, h, owner):
    for p in client.get("/producers?limit=5000", headers=h).json():
        if p.get("nom_complet") == owner:
            # On n'ACHETE qu'aux NON-MEMBRES -> reclasse le producteur du test d'achat.
            client.patch(f"/producers/{p['id']}/type",
                         json={"type_producteur": "non_membre"}, headers=h)
            return p["id"]
    return None


def _harvest_count(client, h, plantation_id):
    return len(client.get(f"/plantations/{plantation_id}/harvests", headers=h).json())


def test_duplicate_check_and_link_prevents_double_harvest(client):
    h = _login(client, "ded.link@test.ci", coop="Coop DedLink")
    pl = _plantation(client, h)
    pid = _producer_id(client, h, "Yao Dedup")
    assert pid is not None

    # 1er achat avec parcelle → génère 1 récolte liée
    r1 = client.post("/purchases", json={
        "producer_id": pid, "plantation_id": pl["id"], "season": "2025-2026",
        "net_weight_kg": 100, "price_per_kg_fcfa": 1500,
    }, headers=h)
    assert r1.status_code == 201, r1.text
    assert r1.json()["harvest_id"]
    assert _harvest_count(client, h, pl["id"]) == 1

    # duplicate-check signale la récolte existante
    dc = client.get(f"/purchases/duplicate-check?plantation_id={pl['id']}&season=2025-2026", headers=h).json()
    assert dc["has_duplicate_risk"] is True and len(dc["existing_harvests"]) == 1
    existing_hid = dc["existing_harvests"][0]["id"]

    # 2e achat LIÉ à la récolte existante → AUCUNE nouvelle récolte
    r2 = client.post("/purchases", json={
        "producer_id": pid, "plantation_id": pl["id"], "harvest_id": existing_hid,
        "season": "2025-2026", "net_weight_kg": 100, "price_per_kg_fcfa": 1500,
    }, headers=h)
    assert r2.status_code == 201, r2.text
    assert r2.json()["harvest_id"] == existing_hid
    assert _harvest_count(client, h, pl["id"]) == 1  # pas de doublon de volume


def test_purchase_without_link_creates_second_harvest(client):
    """Documente le piège : sans lien, un 2e achat recrée une récolte (volume doublé)."""
    h = _login(client, "ded.trap@test.ci", coop="Coop DedTrap")
    pl = _plantation(client, h, name="P-Trap", owner="Bro Trap")
    pid = _producer_id(client, h, "Bro Trap")

    base = {"producer_id": pid, "plantation_id": pl["id"], "season": "2025-2026",
            "net_weight_kg": 80, "price_per_kg_fcfa": 1500}
    assert client.post("/purchases", json=base, headers=h).status_code == 201
    assert _harvest_count(client, h, pl["id"]) == 1
    assert client.post("/purchases", json=base, headers=h).status_code == 201  # non lié
    assert _harvest_count(client, h, pl["id"]) == 2  # ← le doublon que l'alerte évite


def test_link_to_foreign_harvest_rejected(client):
    h1 = _login(client, "ded.a@test.ci", coop="Coop DedA")
    pl = _plantation(client, h1, name="P-A", owner="Aka A")
    pid = _producer_id(client, h1, "Aka A")
    hid = client.post("/purchases", json={
        "producer_id": pid, "plantation_id": pl["id"], "season": "2025-2026",
        "net_weight_kg": 50, "price_per_kg_fcfa": 1500,
    }, headers=h1).json()["harvest_id"]

    # Une autre coop ne peut pas lier un achat à la récolte de la première
    h2 = _login(client, "ded.b@test.ci", coop="Coop DedB")
    pl2 = _plantation(client, h2, name="P-B", owner="Bea B")
    pid2 = _producer_id(client, h2, "Bea B")
    r = client.post("/purchases", json={
        "producer_id": pid2, "plantation_id": pl2["id"], "harvest_id": hid,
        "season": "2025-2026", "net_weight_kg": 50, "price_per_kg_fcfa": 1500,
    }, headers=h2)
    assert r.status_code in (403, 404)
