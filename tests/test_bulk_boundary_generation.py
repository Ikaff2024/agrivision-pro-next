"""Génération en masse des délimitations (P3 — passage à l'échelle 7000+ parcelles).

POST /plantations/boundaries/generate-missing : crée des polygones carrés
(depuis GPS + superficie déclarés, méthode « generated ») pour les parcelles
sans délimitation, **par lots**, sans jamais toucher une parcelle déjà
délimitée ni une autre coopérative.
"""
import json

from app.db.models import Cooperative, Plantation, PlantationBoundary, User
from tests.conftest import TestingSessionLocal, create_member_headers

VALID_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [-6.59, 5.78], [-6.58, 5.78], [-6.58, 5.79], [-6.59, 5.79], [-6.59, 5.78],
    ]],
})

ENDPOINT = "/plantations/boundaries/generate-missing"


def _coop_id(email="admin@fixture.ci"):
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().cooperative_id
    finally:
        db.close()


def _add_plant(coop_id, *, lat=5.785, lng=-6.585, hectares=2.0, delimited=False, name="P"):
    db = TestingSessionLocal()
    try:
        p = Plantation(
            name=name, owner_name="T", country="CI", region="Soubre",
            latitude=lat, longitude=lng, hectares=hectares,
            cooperative_id=coop_id,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        if delimited:
            db.add(PlantationBoundary(
                plantation_id=p.id, geojson=VALID_POLYGON,
                area_hectares=1.0, points_count=5, method="manual",
            ))
            db.commit()
        return p.id
    finally:
        db.close()


def _boundary_for(pid):
    db = TestingSessionLocal()
    try:
        return db.query(PlantationBoundary).filter(
            PlantationBoundary.plantation_id == pid
        ).first()
    finally:
        db.close()


def test_generate_missing_creates_squares(client, auth_headers):
    coop_id = _coop_id()
    p_gps = _add_plant(coop_id, hectares=2.0, name="avec-gps")
    p_delim = _add_plant(coop_id, delimited=True, name="deja-delimite")
    p_nogps = _add_plant(coop_id, lat=None, lng=None, name="sans-gps")

    r = client.post(ENDPOINT, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated"] == 1      # seule p_gps est générable
    assert body["remaining"] == 0
    assert body["without_gps"] == 1    # p_nogps : GPS manquant → non générable

    # p_gps : polygone carré « generated » dont l'aire ≈ superficie déclarée
    b = _boundary_for(p_gps)
    assert b is not None and b.method == "generated"
    assert b.points_count == 5
    assert abs(b.area_hectares - 2.0) < 0.1

    # p_delim : délimitation d'origine intacte (pas écrasée)
    assert _boundary_for(p_delim).method == "manual"

    # p_nogps : toujours sans délimitation
    assert _boundary_for(p_nogps) is None


def test_generate_missing_refreshes_eudr_cache(client, auth_headers):
    pid = _add_plant(_coop_id(), hectares=1.5, name="cache")
    client.post(ENDPOINT, headers=auth_headers)
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        assert p.eudr_computed_at is not None
        assert bool(p.eudr_has_polygon) is True   # le carré généré = polygone valide
    finally:
        db.close()


def test_generate_missing_is_batched(client, auth_headers):
    coop_id = _coop_id()
    for i in range(3):
        _add_plant(coop_id, name=f"batch-{i}")

    body = client.post(f"{ENDPOINT}?limit=2", headers=auth_headers).json()
    assert body["generated"] == 2
    assert body["remaining"] == 1

    body2 = client.post(f"{ENDPOINT}?limit=2", headers=auth_headers).json()
    assert body2["generated"] == 1
    assert body2["remaining"] == 0


def test_generate_missing_scoped_by_coop(client, auth_headers):
    # Parcelle dans une AUTRE coopérative : ne doit jamais être délimitée.
    db = TestingSessionLocal()
    try:
        other = Cooperative(name="Autre Coop", country="CI")
        db.add(other)
        db.flush()
        p = Plantation(
            name="autre", owner_name="X", country="CI", region="R",
            latitude=5.0, longitude=-6.0, hectares=1.0, cooperative_id=other.id,
        )
        db.add(p)
        db.commit()
        other_pid = p.id
    finally:
        db.close()

    client.post(ENDPOINT, headers=auth_headers)
    assert _boundary_for(other_pid) is None


def test_generate_missing_requires_privilege(client, auth_headers):
    _add_plant(_coop_id(), name="x")
    tech_headers = create_member_headers(client, auth_headers, "tech@fixture.ci", "technician")
    r = client.post(ENDPOINT, headers=tech_headers)
    assert r.status_code == 403
