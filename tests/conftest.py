"""
conftest.py — Fixtures partagées pour les tests d'intégration AgriVision Pro.
Placé dans : tests/conftest.py
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db import models  # noqa: F401
from main import app

# StaticPool = toutes les connexions partagent la MÊME DB en mémoire
# Sans ça : SQLite crée une DB vide à chaque connexion → "no such table"
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=TEST_ENGINE
)


@pytest.fixture(scope="function")
def setup_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture(scope="function")
def client(setup_db):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client):
    r = client.post("/auth/register", json={
        "email": "admin@fixture.ci",
        "password": "testpass123",
        "role": "admin",
        "cooperative_name": "Coop Test Fixture",
        "country": "Côte d'Ivoire",
    })
    assert r.status_code == 201, f"Register échoué: {r.text}"

    r = client.post("/auth/login", json={
        "email": "admin@fixture.ci",
        "password": "testpass123",
    })
    assert r.status_code == 200, f"Login échoué: {r.text}"

    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="function")
def plantation_id(client, auth_headers):
    r = client.post("/plantations", json={
        "name": "Plantation Test Fixture",
        "owner_name": "Kouamé Test",
        "country": "Côte d'Ivoire",
        "region": "Soubré",
        "latitude": 5.78,
        "longitude": -6.59,
        "hectares": 3.0,
    }, headers=auth_headers)
    assert r.status_code == 200, f"Plantation fixture échouée: {r.text}"
    return r.json()["id"]
