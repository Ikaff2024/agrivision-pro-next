"""Cockpit certification : couverture, registre, affectation en masse, échéances."""
from datetime import date, timedelta

from app.db.models import Certification
from tests.conftest import TestingSessionLocal


def _login(client, email, coop="Coop Cockpit"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _cert(code="FT", name="Fairtrade"):
    db = TestingSessionLocal()
    try:
        c = db.query(Certification).filter(Certification.code == code).first()
        if not c:
            c = Certification(code=code, nom_complet=name, actif=True)
            db.add(c); db.commit(); db.refresh(c)
        return c.id
    finally:
        db.close()


def _plantation(client, h, name):
    return client.post("/plantations", json={
        "name": name, "owner_name": "O", "country": "CI", "region": "Soubré", "hectares": 2.0,
    }, headers=h).json()


def test_bulk_assign_coverage_and_register(client):
    h = _login(client, "cock.a@test.ci")
    cid = _cert("FT")
    p1 = _plantation(client, h, "P1")
    p2 = _plantation(client, h, "P2")
    exp = (date.today() + timedelta(days=365)).isoformat()

    r = client.post("/certification/bulk-assign", json={
        "certification_id": cid, "plantation_ids": [p1["id"], p2["id"]],
        "date_obtention": date.today().isoformat(), "date_expiration": exp,
    }, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2

    cov = client.get("/certification/coverage", headers=h).json()
    ft = next(c for c in cov["certifications"] if c["code"] == "FT")
    assert ft["plantations_certified"] == 2
    assert ft["pct_plantations"] == 100.0
    assert ft["expired"] == 0 and ft["expiring_soon"] == 0

    reg = client.get("/certification/register", headers=h).json()
    assert reg["count"] == 2
    assert all(row["code"] == "FT" and row["status"] == "valid" for row in reg["rows"])


def test_expiry_buckets_and_filter(client):
    h = _login(client, "cock.exp@test.ci", coop="Coop Exp")
    cid = _cert("RA", "Rainforest Alliance")
    p = _plantation(client, h, "P-exp")
    past = (date.today() - timedelta(days=5)).isoformat()
    client.post("/certification/bulk-assign", json={
        "certification_id": cid, "plantation_ids": [p["id"]], "date_expiration": past,
    }, headers=h)
    cov = client.get("/certification/coverage", headers=h).json()
    ra = next(c for c in cov["certifications"] if c["code"] == "RA")
    assert ra["expired"] == 1
    expired = client.get("/certification/register?status=expired", headers=h).json()
    assert expired["count"] == 1 and expired["rows"][0]["status"] == "expired"
    # Filtre statut "valid" → aucune
    assert client.get("/certification/register?status=valid", headers=h).json()["count"] == 0


def test_bulk_remove(client):
    h = _login(client, "cock.rm@test.ci", coop="Coop Rm")
    cid = _cert("EUDR", "EUDR")
    p = _plantation(client, h, "P-rm")
    client.post("/certification/bulk-assign", json={
        "certification_id": cid, "plantation_ids": [p["id"]],
    }, headers=h)
    r = client.post("/certification/bulk-remove", json={
        "certification_id": cid, "plantation_ids": [p["id"]],
    }, headers=h)
    assert r.status_code == 200 and r.json()["deleted"] == 1
    cov = client.get("/certification/coverage", headers=h).json()
    eudr = next(c for c in cov["certifications"] if c["code"] == "EUDR")
    assert eudr["plantations_certified"] == 0


def test_cockpit_cross_coop_isolation(client):
    ha = _login(client, "cock.iso.a@test.ci", coop="Coop Iso A")
    hb = _login(client, "cock.iso.b@test.ci", coop="Coop Iso B")
    cid = _cert("FT")
    pa = _plantation(client, ha, "PA")
    client.post("/certification/bulk-assign", json={
        "certification_id": cid, "plantation_ids": [pa["id"]],
    }, headers=ha)
    # Coop B ne voit pas le registre de A
    assert client.get("/certification/register", headers=hb).json()["count"] == 0
    # B ne peut pas affecter une certif à la parcelle de A (hors périmètre)
    rb = client.post("/certification/bulk-assign", json={
        "certification_id": cid, "plantation_ids": [pa["id"]],
    }, headers=hb)
    assert rb.status_code == 200 and rb.json()["applied"] == 0


def test_cockpit_requires_auth(client):
    assert client.get("/certification/coverage").status_code == 401
    assert client.get("/certification/register").status_code == 401


def test_bulk_assign_requires_write_role(client):
    h = _login(client, "cock.role@test.ci", coop="Coop Role")
    cid = _cert("FT")
    h_tech = create_member_headers_local(client, h, "cock.tech@test.ci", "technician")
    r = client.post("/certification/bulk-assign", json={"certification_id": cid, "plantation_ids": []}, headers=h_tech)
    assert r.status_code == 403


def create_member_headers_local(client, admin_headers, email, role):
    from tests.conftest import create_member_headers
    return create_member_headers(client, admin_headers, email, role)
