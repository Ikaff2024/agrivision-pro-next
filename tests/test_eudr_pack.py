"""Tests — pack de diligence raisonnée EUDR par lot (ZIP livrable acheteur)."""
import io
import zipfile

from tests.conftest import create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _lot_with_parcel(client, headers):
    """Crée parcelle → récolte → lot ; retourne le lot_id."""
    p = client.post("/plantations", json={
        "name": "Parcelle Pack", "owner_name": "Producteur Pack",
        "country": "CI", "region": "Zone-Test", "hectares": 2.0,
        "latitude": 6.1, "longitude": -6.7,
    }, headers=headers)
    assert p.status_code in (200, 201), p.text
    pid = p.json()["id"]
    h = client.post(f"/plantations/{pid}/harvests", json={
        "harvest_date": "2026-02-01T08:00:00", "quantity_kg": 500, "quality": "Bonne",
    }, headers=headers)
    assert h.status_code in (200, 201), h.text
    hid = h.json()["id"]
    lot = client.post("/lots", json={"season": "2025-2026", "harvest_ids": [hid]}, headers=headers)
    assert lot.status_code in (200, 201), lot.text
    return lot.json()["id"]


def test_eudr_pack_returns_zip_with_expected_entries(client):
    h = _admin(client, "pack.admin@test.ci", "Coop Pack")
    lot_id = _lot_with_parcel(client, h)

    r = client.get(f"/lots/{lot_id}/eudr-pack.zip", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert ".zip" in r.headers.get("content-disposition", "")

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert any(n.startswith("DDS/") and n.endswith(".pdf") for n in names), names
    assert "parcelles.geojson" in names
    assert "recapitulatif.csv" in names
    assert "LISEZ-MOI.txt" in names

    # Le DDS est un vrai PDF
    dds_name = next(n for n in names if n.startswith("DDS/"))
    assert zf.read(dds_name)[:5] == b"%PDF-"
    # Le récapitulatif contient l'en-tête + la parcelle
    recap = zf.read("recapitulatif.csv").decode("utf-8-sig")
    assert "Statut EUDR" in recap
    assert "Parcelle Pack" in recap


def test_eudr_pack_empty_lot_400(client):
    h = _admin(client, "pack.empty@test.ci", "Coop Pack Empty")
    lot = client.post("/lots", json={"season": "2025-2026", "harvest_ids": []}, headers=h)
    assert lot.status_code in (200, 201), lot.text
    r = client.get(f"/lots/{lot.json()['id']}/eudr-pack.zip", headers=h)
    assert r.status_code == 400


def test_eudr_pack_technician_forbidden(client):
    h_admin = _admin(client, "pack.founder@test.ci", "Coop Pack Role")
    lot_id = _lot_with_parcel(client, h_admin)
    h_tech = create_member_headers(client, h_admin, "pack.tech@test.ci", "technician")
    r = client.get(f"/lots/{lot_id}/eudr-pack.zip", headers=h_tech)
    assert r.status_code == 403


def test_eudr_pack_requires_auth(client):
    assert client.get("/lots/1/eudr-pack.zip").status_code == 401


def test_eudr_pack_other_coop_forbidden(client):
    h_a = _admin(client, "pack.a@test.ci", "Coop Pack A")
    lot_a = _lot_with_parcel(client, h_a)
    h_b = _admin(client, "pack.b@test.ci", "Coop Pack B")
    r = client.get(f"/lots/{lot_a}/eudr-pack.zip", headers=h_b)
    assert r.status_code == 403
