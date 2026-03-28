import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Base de données en mémoire pour les tests — jamais de contact avec la DB réelle
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "")

from app.db.database import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

engine_test = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Recrée les tables avant chaque test, les supprime après."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    """Crée un utilisateur admin et retourne son token JWT."""
    client.post("/auth/register", json={
        "email": "admin@test.ci",
        "password": "testpass123",
        "role": "admin",
        "cooperative_name": "Coop Test",
        "country": "Côte d'Ivoire",
    })
    res = client.post("/auth/login", json={
        "email": "admin@test.ci",
        "password": "testpass123",
    })
    return res.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def plantation_id(client, auth_headers):
    """Crée une plantation de test et retourne son ID."""
    res = client.post("/plantations", json={
        "name": "Plantation Test",
        "owner_name": "Konan Kouassi",
        "country": "Côte d'Ivoire",
        "region": "Soubré",
        "latitude": 5.78,
        "longitude": -6.59,
        "hectares": 4.5,
    }, headers=auth_headers)
    assert res.status_code == 200
    return res.json()["id"]
