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
        "nom_complet": "Kouassi Konan", "code_yeyasso": "YEY-001", "type_producteur": "membre",
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
    dup = client.post("/producers", json={"nom_complet": "Homonyme", "code_yeyasso": "YEY-001", "type_producteur": "membre"}, headers=h)
    assert dup.status_code == 409


def test_producers_count_and_pagination(client):
    """P2 scale : /producers/count + pagination limit/skip cohérents avec la liste."""
    h = _login(client, email="pager.admin@test.ci", coop="Coop Pager")
    for i in range(5):
        r = client.post("/producers", json={"nom_complet": f"Producteur {i:02d}", "type_producteur": "membre"}, headers=h)
        assert r.status_code == 201, r.text
    # /producers/count = total filtré, scope coopérative
    assert client.get("/producers/count", headers=h).json()["total"] == 5
    # Pagination : deux pages de 2, disjointes
    p0 = client.get("/producers?limit=2&skip=0", headers=h).json()
    p1 = client.get("/producers?limit=2&skip=2", headers=h).json()
    assert len(p0) == 2 and len(p1) == 2
    assert {p["id"] for p in p0}.isdisjoint({p["id"] for p in p1})
    # Le count applique les MÊMES filtres que la liste (sinon le pager serait faux)
    assert client.get("/producers/count?search=03", headers=h).json()["total"] == 1


def test_create_producer_requires_name(client):
    h = _login(client, "prod.name@test.ci", "Coop Name")
    r = client.post("/producers", json={"nom_complet": "A", "type_producteur": "membre"}, headers=h)  # < 2 caractères
    assert r.status_code == 422


def test_create_producer_requires_auth(client):
    r = client.post("/producers", json={"nom_complet": "Sans authentification", "type_producteur": "membre"})
    assert r.status_code in (401, 403)


def test_create_producer_requires_category(client):
    """La categorie (membre/non-membre) est OBLIGATOIRE a la creation."""
    h = _login(client, "prod.cat@test.ci", "Coop Cat")
    r = client.post("/producers", json={"nom_complet": "Sans categorie"}, headers=h)
    assert r.status_code == 422, r.text
    r2 = client.post("/producers", json={"nom_complet": "Cat invalide", "type_producteur": "vip"}, headers=h)
    assert r2.status_code == 422, r2.text
    r3 = client.post("/producers", json={"nom_complet": "Cat ok", "type_producteur": "non_membre"}, headers=h)
    assert r3.status_code == 201, r3.text
    assert r3.json()["type_producteur"] == "non_membre"


def test_bulk_set_producer_type(client):
    """Reclassement en masse : bascule tous les 'membre' filtres en 'non_membre'."""
    h = _login(client, "prod.bulk@test.ci", "Coop Bulk")
    for i in range(3):
        client.post("/producers", json={
            "nom_complet": f"Bulk {i}", "localite": "Zone Z", "type_producteur": "membre",
        }, headers=h)
    client.post("/producers", json={
        "nom_complet": "Hors zone", "localite": "Ailleurs", "type_producteur": "membre",
    }, headers=h)
    r = client.post("/producers/bulk-type", json={
        "type_producteur": "non_membre", "from_type": "membre", "localite": "Zone Z",
    }, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3 and r.json()["matched"] == 3
    non_m = client.get("/producers?type_producteur=non_membre", headers=h).json()
    assert {"Bulk 0", "Bulk 1", "Bulk 2"}.issubset({p["nom_complet"] for p in non_m})
    membres = client.get("/producers?type_producteur=membre", headers=h).json()
    assert "Hors zone" in {p["nom_complet"] for p in membres}


def test_bulk_set_producer_type_requires_admin(client):
    h_admin = _login(client, "prod.bulkadmin@test.ci", "Coop BulkR")
    h_tech = create_member_headers(client, h_admin, "prod.bulktech@test.ci", "technician")
    r = client.post("/producers/bulk-type", json={"type_producteur": "non_membre"}, headers=h_tech)
    assert r.status_code == 403, r.text


def test_create_producer_technician_and_gestionnaire_allowed(client):
    h_admin = _login(client, "prod.founder@test.ci", "Coop Roles P")
    h_tech = create_member_headers(client, h_admin, "prod.tech@test.ci", "technician")
    h_gest = create_member_headers(client, h_admin, "prod.gest@test.ci", "gestionnaire")
    assert client.post("/producers", json={"nom_complet": "Par technicien", "type_producteur": "membre"}, headers=h_tech).status_code == 201
    assert client.post("/producers", json={"nom_complet": "Par gestionnaire", "type_producteur": "non_membre"}, headers=h_gest).status_code == 201


def test_create_producer_cooperative_scoped(client):
    """Le producteur créé n'est visible que dans sa coopérative."""
    ha = _login(client, "prod.a@test.ci", "Coop P A")
    hb = _login(client, "prod.b@test.ci", "Coop P B")
    pid = client.post("/producers", json={"nom_complet": "Visible A", "type_producteur": "membre"}, headers=ha).json()["id"]
    assert pid not in [p["id"] for p in client.get("/producers", headers=hb).json()]


# ── Mise à jour d'un producteur (PUT) ────────────────────────────────────────
def test_update_producer_fields(client):
    h = _login(client, "prod.upd@test.ci", "Coop Upd")
    pid = client.post("/producers", json={"nom_complet": "Avant Edit", "localite": "Ancienne", "type_producteur": "membre"}, headers=h).json()["id"]
    r = client.put(f"/producers/{pid}", json={
        "nom_complet": "Apres Edit", "localite": "Soubré", "telephone": "0712345678",
        "sexe": "F", "code_saco": "SACO-9", "latitude": 5.78, "longitude": -6.59,
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nom_complet"] == "Apres Edit" and body["localite"] == "Soubré"
    assert body["sexe"] == "F" and body["code_saco"] == "SACO-9" and body["latitude"] == 5.78
    got = client.get(f"/producers/{pid}", headers=h).json()
    assert got["nom_complet"] == "Apres Edit" and got["telephone"] == "0712345678"


def test_update_producer_partial_keeps_other_fields(client):
    h = _login(client, "prod.partial@test.ci", "Coop Partial")
    pid = client.post("/producers", json={
        "nom_complet": "Garde Code", "code_yeyasso": "KEEP-1", "localite": "Méagui", "type_producteur": "membre",
    }, headers=h).json()["id"]
    r = client.put(f"/producers/{pid}", json={"telephone": "0799"}, headers=h)  # seul le tel change
    assert r.status_code == 200
    body = r.json()
    assert body["telephone"] == "0799"
    assert body["code_yeyasso"] == "KEEP-1" and body["localite"] == "Méagui"  # inchangés (exclude_unset)


def test_update_producer_code_dedup(client):
    h = _login(client, "prod.upddup@test.ci", "Coop UpdDup")
    client.post("/producers", json={"nom_complet": "P1", "code_yeyasso": "C-1", "type_producteur": "membre"}, headers=h)
    p2 = client.post("/producers", json={"nom_complet": "P2", "code_yeyasso": "C-2", "type_producteur": "non_membre"}, headers=h).json()["id"]
    assert client.put(f"/producers/{p2}", json={"code_yeyasso": "C-1"}, headers=h).status_code == 409


def test_update_producer_cooperative_scoped(client):
    ha = _login(client, "prod.ua@test.ci", "Coop UA")
    hb = _login(client, "prod.ub@test.ci", "Coop UB")
    pid = client.post("/producers", json={"nom_complet": "Chez A", "type_producteur": "membre"}, headers=ha).json()["id"]
    assert client.put(f"/producers/{pid}", json={"nom_complet": "Pirate"}, headers=hb).status_code == 404
