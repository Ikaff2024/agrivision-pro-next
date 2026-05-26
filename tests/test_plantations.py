"""Tests d'intégration — plantations."""


from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Plantation, PlantationAssignment, User
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
