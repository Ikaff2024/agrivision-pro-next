"""Tests — lot d'import (import_batch_id) et annulation d'un import errone."""
from datetime import datetime

from app.importers.cooperative_registry import (
    RegistryParseResult, ParsedProducer, ParsedPlantation,
)
from app.importers.registry_loader import load_registry
from app.db.models import Producer, Plantation, ImportBatch, Harvest
from tests.conftest import TestingSessionLocal


OWNER_KEY = "test-owner-key"


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    coop_id = client.get("/me", headers=headers).json()["cooperative_id"]
    return headers, coop_id


def _make_parse_result(n=2, prefix="T"):
    producers = [
        ParsedProducer(code_yeyasso=f"{prefix}P{i}", nom_complet=f"Producteur {i}")
        for i in range(1, n + 1)
    ]
    plantations = [
        ParsedPlantation(code_plantation=f"{prefix}P{i}-P1", code_producteur=f"{prefix}P{i}",
                         superficie_ha=2.0)
        for i in range(1, n + 1)
    ]
    return RegistryParseResult(producers=producers, plantations=plantations,
                               detected_campaign="2025-2026")


def _seed_import(coop_id, n=2, prefix="T", fichier="registre_test.xlsx"):
    """Joue un import minimal et retourne le batch_uuid."""
    db = TestingSessionLocal()
    try:
        report = load_registry(_make_parse_result(n, prefix), db,
                               cooperative_id=coop_id, fichier_source=fichier, user_id=None)
        return report.batch_uuid
    finally:
        db.close()


# ─── L'import tague bien les entités créées ───────────────────────────────────

def test_import_tags_entities_with_batch(client):
    _, coop_id = _admin(client, "imp.tag@test.ci", "Coop Import Tag")
    batch_uuid = _seed_import(coop_id, n=3, prefix="A")

    db = TestingSessionLocal()
    try:
        prods = db.query(Producer).filter(Producer.import_batch_id == batch_uuid).all()
        plants = db.query(Plantation).filter(Plantation.import_batch_id == batch_uuid).all()
        batch = db.query(ImportBatch).filter(ImportBatch.batch_uuid == batch_uuid).first()
        assert len(prods) == 3
        assert len(plants) == 3
        assert batch is not None
        assert batch.status == "active"
        assert batch.producers_created == 3
        assert batch.plantations_created == 3
        assert batch.cooperative_id == coop_id
    finally:
        db.close()


# ─── Historique ───────────────────────────────────────────────────────────────

def test_list_batches_scoped_to_coop(client):
    h_a, coop_a = _admin(client, "imp.a@test.ci", "Coop Imp A")
    h_b, coop_b = _admin(client, "imp.b@test.ci", "Coop Imp B")
    _seed_import(coop_a, n=2, prefix="A")
    _seed_import(coop_b, n=2, prefix="B")

    r = client.get("/import/batches", headers=h_a)
    assert r.status_code == 200
    batches = r.json()
    assert len(batches) == 1                      # ne voit QUE sa coop
    assert batches[0]["producers_created"] == 2
    assert batches[0]["status"] == "active"


def test_list_batches_requires_admin(client):
    from tests.conftest import create_member_headers
    h_admin, _ = _admin(client, "imp.adm@test.ci", "Coop Imp Adm")
    h_tech = create_member_headers(client, h_admin, "imp.tech@test.ci", "technician")
    assert client.get("/import/batches", headers=h_tech).status_code == 403


# ─── Annulation ────────────────────────────────────────────────────────────────

def test_cancel_import_removes_entities(client):
    h, coop_id = _admin(client, "imp.cancel@test.ci", "Coop Imp Cancel")
    batch_uuid = _seed_import(coop_id, n=3, prefix="C")

    r = client.delete(f"/import/batches/{batch_uuid}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["producers_deleted"] == 3
    assert r.json()["plantations_deleted"] == 3

    db = TestingSessionLocal()
    try:
        assert db.query(Producer).filter(Producer.import_batch_id == batch_uuid).count() == 0
        assert db.query(Plantation).filter(Plantation.import_batch_id == batch_uuid).count() == 0
        batch = db.query(ImportBatch).filter(ImportBatch.batch_uuid == batch_uuid).first()
        assert batch.status == "cancelled"
        assert batch.cancelled_at is not None
    finally:
        db.close()


def test_cancel_blocked_by_derived_harvest(client):
    """Garde-fou : une récolte sur une plantation du lot interdit l'annulation."""
    h, coop_id = _admin(client, "imp.guard@test.ci", "Coop Imp Guard")
    batch_uuid = _seed_import(coop_id, n=2, prefix="G")

    # Ajoute une récolte sur une plantation du lot
    db = TestingSessionLocal()
    try:
        plant = db.query(Plantation).filter(Plantation.import_batch_id == batch_uuid).first()
        db.add(Harvest(plantation_id=plant.id, harvest_date=datetime(2026, 1, 15),
                       quantity_kg=100.0, quality="Bonne"))
        db.commit()
    finally:
        db.close()

    r = client.delete(f"/import/batches/{batch_uuid}", headers=h)
    assert r.status_code == 409
    assert "récolte" in r.json()["detail"].lower()

    # Rien n'a été supprimé
    db = TestingSessionLocal()
    try:
        assert db.query(Producer).filter(Producer.import_batch_id == batch_uuid).count() == 2
        batch = db.query(ImportBatch).filter(ImportBatch.batch_uuid == batch_uuid).first()
        assert batch.status == "active"
    finally:
        db.close()


def test_cancel_unknown_batch_404(client):
    h, _ = _admin(client, "imp.404@test.ci", "Coop Imp 404")
    assert client.delete("/import/batches/inexistant", headers=h).status_code == 404


def test_cancel_other_coop_batch_404(client):
    h_a, coop_a = _admin(client, "imp.x@test.ci", "Coop Imp X")
    h_b, coop_b = _admin(client, "imp.y@test.ci", "Coop Imp Y")
    batch_a = _seed_import(coop_a, n=2, prefix="X")
    # B ne doit pas pouvoir annuler le lot de A
    assert client.delete(f"/import/batches/{batch_a}", headers=h_b).status_code == 404


def test_cancel_already_cancelled_409(client):
    h, coop_id = _admin(client, "imp.twice@test.ci", "Coop Imp Twice")
    batch_uuid = _seed_import(coop_id, n=1, prefix="W")
    assert client.delete(f"/import/batches/{batch_uuid}", headers=h).status_code == 200
    assert client.delete(f"/import/batches/{batch_uuid}", headers=h).status_code == 409


# ─── Annulation par le propriétaire (IKAFFANAN) ───────────────────────────────

def test_owner_can_cancel_any_batch(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    _, coop_id = _admin(client, "imp.owner@test.ci", "Coop Imp Owner")
    batch_uuid = _seed_import(coop_id, n=2, prefix="O")

    r = client.delete(f"/import/owner/batches/{batch_uuid}", headers={"X-Owner-Key": OWNER_KEY})
    assert r.status_code == 200, r.text
    assert r.json()["producers_deleted"] == 2

    db = TestingSessionLocal()
    try:
        assert db.query(Plantation).filter(Plantation.import_batch_id == batch_uuid).count() == 0
    finally:
        db.close()


def test_owner_cancel_requires_key(client, monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", OWNER_KEY)
    _, coop_id = _admin(client, "imp.ownerk@test.ci", "Coop Imp OwnerK")
    batch_uuid = _seed_import(coop_id, n=1, prefix="K")
    r = client.delete(f"/import/owner/batches/{batch_uuid}", headers={"X-Owner-Key": "mauvaise"})
    assert r.status_code == 401
