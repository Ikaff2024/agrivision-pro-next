"""Tests d'intégration — plantations."""


from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Plantation, PlantationAssignment, Producer, User
from tests.conftest import TestingSessionLocal


def test_create_plantation(client, auth_headers):
    res = client.post("/plantations", json={
        "name": "Plantation Soubré",
        "owner_name": "Yao Kouamé",
        "country": "Côte d'Ivoire",
        "region": "Soubré",
        "latitude": 5.78,
        "longitude": -6.59,
        "hectares": 3.0,
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Plantation Soubré"
    assert data["cooperative_id"] is not None  # toujours rattachée


def test_create_plantation_creates_and_links_producer(client, auth_headers):
    """Créer une plantation doit générer le Producteur correspondant et le lier,
    pour qu'il apparaisse dans les listes (Protection enfant, EUDR, CacaoGuard)."""
    res = client.post("/plantations", json={
        "name": "Parcelle Daloa",
        "owner_name": "Anthony DELORE",
        "country": "Côte d'Ivoire",
        "hectares": 4.5,
    }, headers=auth_headers)
    assert res.status_code == 200
    plantation = res.json()
    assert plantation["producer_id"] is not None

    # Le producteur apparaît bien dans /producers (la liste utilisée par la
    # page Protection enfant).
    producers = client.get("/producers?limit=1000", headers=auth_headers).json()
    names = [p["nom_complet"] for p in producers]
    assert "Anthony DELORE" in names

    # Lien correct entre la plantation et le producteur créé.
    matching = [p for p in producers if p["nom_complet"] == "Anthony DELORE"]
    assert matching and matching[0]["id"] == plantation["producer_id"]


def test_update_plantation_fields(client, auth_headers):
    """Modifier une plantation existante (ex: corriger la région vide)."""
    created = client.post("/plantations", json={
        "name": "Parcelle A", "owner_name": "Yao K", "country": "CI", "hectares": 3.0,
    }, headers=auth_headers).json()
    pid = created["id"]

    res = client.put(f"/plantations/{pid}", json={
        "region": "Man", "hectares": 4.2,
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["region"] == "Man"
    assert data["hectares"] == 4.2
    # Les champs non fournis restent inchangés.
    assert data["name"] == "Parcelle A"


def test_update_plantation_owner_relinks_producer(client, auth_headers):
    """Changer le propriétaire recrée/relie le Producteur correspondant."""
    created = client.post("/plantations", json={
        "name": "Parcelle B", "owner_name": "Ancien Proprio", "country": "CI",
    }, headers=auth_headers).json()
    pid = created["id"]

    res = client.put(f"/plantations/{pid}", json={"owner_name": "Nouveau Proprio"},
                     headers=auth_headers)
    assert res.status_code == 200
    new_producer_id = res.json()["producer_id"]

    producers = client.get("/producers?limit=1000", headers=auth_headers).json()
    match = [p for p in producers if p["nom_complet"] == "Nouveau Proprio"]
    assert match and match[0]["id"] == new_producer_id


def test_update_plantation_not_found(client, auth_headers):
    res = client.put("/plantations/99999", json={"region": "X"}, headers=auth_headers)
    assert res.status_code == 404


def test_update_plantation_invalid_hectares_rejected(client, auth_headers):
    created = client.post("/plantations", json={
        "name": "Parcelle C", "owner_name": "Z", "country": "CI",
    }, headers=auth_headers).json()
    res = client.put(f"/plantations/{created['id']}", json={"hectares": 0.1},
                     headers=auth_headers)
    assert res.status_code == 422


def test_create_plantation_reuses_existing_producer(client, auth_headers):
    """Deux plantations du même propriétaire (même coop) partagent un seul
    Producteur — pas de doublon."""
    payload = {
        "owner_name": "Marie Koffi",
        "country": "Côte d'Ivoire",
        "hectares": 2.0,
    }
    r1 = client.post("/plantations", json={**payload, "name": "P1"}, headers=auth_headers)
    r2 = client.post("/plantations", json={**payload, "name": "P2"}, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["producer_id"] == r2.json()["producer_id"]

    producers = client.get("/producers?limit=1000", headers=auth_headers).json()
    assert sum(1 for p in producers if p["nom_complet"] == "Marie Koffi") == 1


def test_create_plantation_requires_admin(client, auth_headers):
    # L'agronome rejoint la coop existante → reste agronomist → ne peut pas créer
    client.post("/auth/register", json={
        "email": "agro@test.ci",
        "password": "pass123",
        "role": "agronomist",
        "cooperative_name": "Coop Test Fixture",  # coop existante → pas admin
        "country": "Côte d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "agro@test.ci", "password": "pass123"
    }).json()["access_token"]

    res = client.post("/plantations", json={
        "name": "P", "owner_name": "O", "country": "CI"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_get_plantations(client, auth_headers, plantation_id):
    res = client.get("/plantations", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert any(p["id"] == plantation_id for p in res.json())


def test_get_plantation_by_id(client, auth_headers, plantation_id):
    res = client.get(f"/plantations/{plantation_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["plantation"]["id"] == plantation_id


def test_get_plantation_not_found(client, auth_headers):
    res = client.get("/plantations/99999", headers=auth_headers)
    assert res.status_code == 404


def test_cooperative_isolation(client):
    """Deux coopératives distinctes ne voient pas les plantations de l'autre."""
    # Coop A
    client.post("/auth/register", json={
        "email": "admin_a@test.ci", "password": "pass123",
        "role": "admin", "cooperative_name": "Coop A", "country": "CI"
    })
    token_a = client.post("/auth/login", json={
        "email": "admin_a@test.ci", "password": "pass123"
    }).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Coop B
    client.post("/auth/register", json={
        "email": "admin_b@test.ci", "password": "pass123",
        "role": "admin", "cooperative_name": "Coop B", "country": "CI"
    })
    token_b = client.post("/auth/login", json={
        "email": "admin_b@test.ci", "password": "pass123"
    }).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Coop A crée une plantation
    client.post("/plantations", json={
        "name": "Plantation A", "owner_name": "A", "country": "CI"
    }, headers=headers_a)

    # Coop B ne doit pas la voir
    res = client.get("/plantations", headers=headers_b)
    assert all(p["name"] != "Plantation A" for p in res.json())


def test_plantations_limit_can_return_more_than_200(client, auth_headers):
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).filter(Cooperative.name == "Coop Test Fixture").first()
        db.add_all([
            Plantation(
                name=f"Bulk Plantation {i:03d}",
                owner_name="Bulk Owner",
                country="CI",
                cooperative_id=coop.id,
            )
            for i in range(230)
        ])
        db.commit()
    finally:
        db.close()

    res = client.get("/plantations?limit=5000", headers=auth_headers)

    assert res.status_code == 200
    bulk_rows = [p for p in res.json() if p["name"].startswith("Bulk Plantation")]
    assert len(bulk_rows) == 230


def test_plantations_can_filter_by_producer(client, auth_headers):
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).filter(Cooperative.name == "Coop Test Fixture").first()
        producer_a = Producer(cooperative_id=coop.id, nom_complet="Producteur A", is_active=True)
        producer_b = Producer(cooperative_id=coop.id, nom_complet="Producteur B", is_active=True)
        db.add_all([producer_a, producer_b])
        db.commit()
        p1 = Plantation(
            name="Producer A Plot",
            owner_name="Producteur A",
            country="CI",
            cooperative_id=coop.id,
            producer_id=producer_a.id,
        )
        p2 = Plantation(
            name="Producer B Plot",
            owner_name="Producteur B",
            country="CI",
            cooperative_id=coop.id,
            producer_id=producer_b.id,
        )
        db.add_all([p1, p2])
        db.commit()
        producer_a_id = producer_a.id
    finally:
        db.close()

    res = client.get(f"/plantations?producer_id={producer_a_id}&limit=5000", headers=auth_headers)

    assert res.status_code == 200, res.text
    names = {p["name"] for p in res.json()}
    assert "Producer A Plot" in names
    assert "Producer B Plot" not in names


def test_technician_only_sees_assigned_plantations(client, auth_headers):
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).filter(Cooperative.name == "Coop Test Fixture").first()
        tech = User(
            email="tech.assigned@test.ci",
            password_hash="x",
            role="technician",
            cooperative_id=coop.id,
        )
        p1 = Plantation(name="Assigned P", owner_name="A", country="CI", cooperative_id=coop.id)
        p2 = Plantation(name="Unassigned P", owner_name="B", country="CI", cooperative_id=coop.id)
        db.add_all([tech, p1, p2])
        db.commit()
        db.add(PlantationAssignment(plantation_id=p1.id, technician_id=tech.id, is_active=True))
        db.commit()
        token = create_access_token({"sub": tech.email, "role": tech.role, "coop_id": coop.id})
    finally:
        db.close()

    res = client.get("/plantations?limit=5000", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    names = {p["name"] for p in res.json()}
    assert "Assigned P" in names
    assert "Unassigned P" not in names


def test_admin_can_list_unassigned_and_assign_bulk(client, auth_headers):
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).filter(Cooperative.name == "Coop Test Fixture").first()
        tech = User(
            email="tech.bulk@test.ci",
            password_hash="x",
            role="technician",
            cooperative_id=coop.id,
        )
        p1 = Plantation(name="To Assign 1", owner_name="A", country="CI", cooperative_id=coop.id)
        p2 = Plantation(name="To Assign 2", owner_name="B", country="CI", cooperative_id=coop.id)
        db.add_all([tech, p1, p2])
        db.commit()
        tech_id, p1_id, p2_id = tech.id, p1.id, p2.id
    finally:
        db.close()

    unassigned = client.get("/assignments/unassigned?limit=5000", headers=auth_headers)
    assert unassigned.status_code == 200
    unassigned_ids = {p["id"] for p in unassigned.json()["items"]}
    assert {p1_id, p2_id}.issubset(unassigned_ids)

    assigned = client.post(
        "/assignments/bulk",
        json={"technician_id": tech_id, "plantation_ids": [p1_id, p2_id]},
        headers=auth_headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["total"] == 2

    filtered = client.get(f"/plantations?limit=5000&technician_id={tech_id}", headers=auth_headers)
    assert filtered.status_code == 200
    assert {p["id"] for p in filtered.json()} == {p1_id, p2_id}
