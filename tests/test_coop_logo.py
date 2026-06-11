"""Tests — logo de la coopérative (upload, get, delete, validation, contexte PDF)."""
from tests.conftest import TestingSessionLocal, create_member_headers

_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def _admin(client, email="logo@test.ci", coop="Coop Logo"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    coop_id = client.get("/me", headers=h).json()["cooperative_id"]
    return h, coop_id


def test_logo_upload_get_delete(client):
    h, cid = _admin(client)
    r = client.post(f"/cooperatives/{cid}/logo", headers=h,
                    files={"file": ("logo.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    g = client.get(f"/cooperatives/{cid}/logo", headers=h).json()
    assert g["logo"].startswith("data:image/png;base64,")
    assert client.delete(f"/cooperatives/{cid}/logo", headers=h).status_code == 200
    assert client.get(f"/cooperatives/{cid}/logo", headers=h).json()["logo"] is None


def test_logo_rejects_bad_type(client):
    h, cid = _admin(client, "logo.bad@test.ci", "Coop Logo Bad")
    r = client.post(f"/cooperatives/{cid}/logo", headers=h,
                    files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_logo_rejects_too_large(client):
    h, cid = _admin(client, "logo.big@test.ci", "Coop Logo Big")
    big = b"x" * (512 * 1024 + 10)
    r = client.post(f"/cooperatives/{cid}/logo", headers=h,
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 400


def test_logo_requires_admin(client):
    h_admin, cid = _admin(client, "logo.role@test.ci", "Coop Logo Role")
    h_tech = create_member_headers(client, h_admin, "logo.tech@test.ci", "technician")
    r = client.post(f"/cooperatives/{cid}/logo", headers=h_tech,
                    files={"file": ("logo.png", _PNG, "image/png")})
    assert r.status_code == 403


def test_logo_feeds_pdf_context(client):
    """Le logo téléversé est exposé par coop_brand (consommé par les PDF)."""
    h, cid = _admin(client, "logo.ctx@test.ci", "Coop Logo Ctx")
    client.post(f"/cooperatives/{cid}/logo", headers=h,
                files={"file": ("logo.png", _PNG, "image/png")})
    from app.services.reports import coop_brand
    db = TestingSessionLocal()
    try:
        brand = coop_brand(db, cid)
    finally:
        db.close()
    assert brand["coop_logo"].startswith("data:image/png;base64,")
    assert brand["coop_name"] == "Coop Logo Ctx"


def test_logo_settings(client):
    h, cid = _admin(client, "logo.set@test.ci", "Coop Logo Set")
    g = client.get(f"/cooperatives/{cid}/logo", headers=h).json()
    assert g["size"] == "md" and g["plaque"] is True          # défauts
    r = client.patch(f"/cooperatives/{cid}/logo-settings", headers=h, json={"size": "lg", "plaque": False})
    assert r.status_code == 200, r.text
    g2 = client.get(f"/cooperatives/{cid}/logo", headers=h).json()
    assert g2["size"] == "lg" and g2["plaque"] is False
    # taille invalide rejetée
    assert client.patch(f"/cooperatives/{cid}/logo-settings", headers=h,
                        json={"size": "huge"}).status_code == 400
    # reflété dans le contexte PDF
    from app.services.reports import coop_brand
    db = TestingSessionLocal()
    try:
        b = coop_brand(db, cid)
    finally:
        db.close()
    assert b["coop_logo_size"] == "lg" and b["coop_logo_plaque"] is False
