"""Dérogation export EN LOT (P3 — actions en masse, bornée).

Règle : dérogation **bornée à un lot**, un même motif tracé appliqué aux parcelles
EUDR non conformes du lot pour débloquer son expédition ; admin only ; réversible ;
journalisée par parcelle. On ne déroge jamais « toutes les parcelles » d'un coup.
"""

from tests.conftest import create_member_headers


def _login(client, email, password="pass1234", role="admin", coop="Coop LotWaiver"):
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plantation(client, h, name, owner):
    # Sans polygone / GPS / inspection -> EUDR non conforme.
    return client.post("/plantations", json={
        "name": name, "owner_name": owner, "country": "Côte d'Ivoire",
        "region": "Soubré", "hectares": 3.0,
    }, headers=h).json()


def _harvest(client, h, plantation_id, qty=500.0):
    return client.post(f"/plantations/{plantation_id}/harvests", json={
        "harvest_date": "2026-01-15T00:00:00", "quantity_kg": qty, "quality": "Bonne",
    }, headers=h).json()


def _lot(client, h, harvest_ids):
    return client.post("/lots", json={"harvest_ids": harvest_ids}, headers=h).json()


def test_lot_waiver_grants_to_all_blocking_parcels_and_unblocks_shipping(client):
    h = _login(client, "lw.grant@test.ci", coop="Coop LWGrant")
    p1 = _plantation(client, h, "NC-1", "Yao A")
    p2 = _plantation(client, h, "NC-2", "Konan B")
    lot = _lot(client, h, [_harvest(client, h, p1["id"])["id"], _harvest(client, h, p2["id"])["id"]])

    # Expédition bloquée tant qu'aucune dérogation.
    assert client.post(f"/lots/{lot['id']}/movements",
                       json={"movement_type": "export_out"}, headers=h).status_code == 409

    # Non-admin refusé.
    h_tech = create_member_headers(client, h, "lw.tech@test.ci", "technician")
    assert client.post(f"/lots/{lot['id']}/export-waiver",
                       json={"reason": "tentative interdite"}, headers=h_tech).status_code == 403

    # Motif trop court refusé (validation ≥ 8).
    assert client.post(f"/lots/{lot['id']}/export-waiver",
                       json={"reason": "court"}, headers=h).status_code == 422

    # Dérogation en lot (admin) -> les 2 parcelles dérogées avec le même motif.
    rg = client.post(f"/lots/{lot['id']}/export-waiver",
                     json={"reason": "Plan de conformite signe, echeance 30/09/2026"}, headers=h)
    assert rg.status_code == 200, rg.text
    assert rg.json()["waived"] == 2 and rg.json()["already_waived"] == 0

    # Tracé par parcelle (motif partagé visible).
    st = client.get(f"/plantations/{p1['id']}/eudr-status", headers=h).json()
    assert st["export_waiver"] is True and "30/09/2026" in (st.get("export_waiver_reason") or "")

    # Expédition débloquée.
    rship = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "export_out"}, headers=h)
    assert rship.status_code == 200, rship.text
    assert rship.json()["status"] == "shipped"

    # Idempotent : un 2e appel ne ré-applique pas (déjà dérogées, motif propre conservé).
    rg2 = client.post(f"/lots/{lot['id']}/export-waiver",
                      json={"reason": "second passage ne doit rien changer"}, headers=h)
    assert rg2.json()["waived"] == 0 and rg2.json()["already_waived"] == 2


def test_lot_waiver_revoke_reblocks(client):
    h = _login(client, "lw.rev@test.ci", coop="Coop LWRev")
    p = _plantation(client, h, "NC-R", "Brou C")
    lot = _lot(client, h, [_harvest(client, h, p["id"])["id"]])

    client.post(f"/lots/{lot['id']}/export-waiver",
                json={"reason": "Derogation a retirer ensuite"}, headers=h)
    rr = client.delete(f"/lots/{lot['id']}/export-waiver", headers=h)
    assert rr.status_code == 200 and rr.json()["revoked"] == 1

    assert client.get(f"/plantations/{p['id']}/eudr-status", headers=h).json()["export_waiver"] is False
    # Re-bloqué.
    assert client.post(f"/lots/{lot['id']}/movements",
                       json={"movement_type": "export_out"}, headers=h).status_code == 409


def test_lot_passport_exposes_blocking_and_waived_counts(client):
    h = _login(client, "lw.cnt@test.ci", coop="Coop LWCnt")
    p = _plantation(client, h, "NC-X", "Diby D")
    lot = _lot(client, h, [_harvest(client, h, p["id"])["id"]])

    s1 = client.get(f"/lots/{lot['id']}/passport", headers=h).json()["summary"]
    assert s1["export_blocking_plantations"] == 1 and s1["export_waived_plantations"] == 0

    client.post(f"/lots/{lot['id']}/export-waiver",
                json={"reason": "Motif de test suffisamment long"}, headers=h)
    s2 = client.get(f"/lots/{lot['id']}/passport", headers=h).json()["summary"]
    assert s2["export_blocking_plantations"] == 0 and s2["export_waived_plantations"] == 1
