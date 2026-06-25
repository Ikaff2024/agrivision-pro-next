"""Déforestation à l'export (intégrité EUDR).

Posture (retours terrain) : une parcelle dont la déforestation est **détectée**
BLOQUE l'expédition (même si son statut global n'est pas non_conforme) ; une
déforestation **non vérifiée** n'empêche pas l'export mais est SIGNALÉE dans le
passeport (alerte). cf. scoring « au prorata » qui laissait passer ces cas.
"""
import json
from datetime import datetime, timezone

from app.db.models import (
    DeforestationCheck, Harvest, Plantation, PlantationBoundary, Producer, User,
)
from tests.conftest import TestingSessionLocal

# Polygone valide en zone cacao CI (≈ 1 ha) → polygone/aire/GPS OK (parcelle
# "à vérifier" 4/6, NON non_conforme) pour isoler l'effet de la déforestation.
VALID_POLY = json.dumps({"type": "Polygon", "coordinates": [[
    [-6.590, 5.780], [-6.585, 5.780], [-6.585, 5.785], [-6.590, 5.785], [-6.590, 5.780],
]]})


def _coop_id(email="admin@fixture.ci"):
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().cooperative_id
    finally:
        db.close()


def _parcel_with_harvest(coop_id, name, *, defo=None):
    """Parcelle ~à_vérifier (polygone+aire+GPS+producteur sans blocage) + 1 récolte.
    `defo` = None (non vérifiée) | 'deforestation_detected' | 'clear'."""
    db = TestingSessionLocal()
    try:
        prod = Producer(nom_complet="Prod " + name, cooperative_id=coop_id, is_active=True)
        db.add(prod)
        db.flush()
        p = Plantation(
            name=name, owner_name="O", country="CI", region="Soubre",
            latitude=5.782, longitude=-6.587, hectares=1.0,
            cooperative_id=coop_id, producer_id=prod.id,
        )
        db.add(p)
        db.flush()
        db.add(PlantationBoundary(
            plantation_id=p.id, geojson=VALID_POLY, area_hectares=1.0,
            points_count=5, method="manual",
        ))
        hv = Harvest(
            plantation_id=p.id, harvest_date=datetime.now(timezone.utc),
            quantity_kg=100.0, quality="Bonne", season="2025-2026",
        )
        db.add(hv)
        if defo:
            db.add(DeforestationCheck(
                plantation_id=p.id, verdict=defo, check_date=datetime.now(timezone.utc),
                source="field_visit",
                forest_loss_year=(2022 if defo == "deforestation_detected" else None),
            ))
        db.commit()
        return p.id, hv.id
    finally:
        db.close()


def test_detected_deforestation_blocks_export(client, auth_headers):
    _, hid = _parcel_with_harvest(_coop_id(), "Defo-Detected", defo="deforestation_detected")
    lot = client.post("/lots", json={"harvest_ids": [hid]}, headers=auth_headers).json()
    # Déforestation détectée → expédition refusée même si le statut n'est pas non_conforme.
    r = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "export_out"}, headers=auth_headers)
    assert r.status_code == 409, r.text
    reasons = [p.get("reason") for p in r.json()["detail"]["non_compliant_plantations"]]
    assert "deforestation_detected" in reasons


def test_unverified_deforestation_alerts_but_ships(client, auth_headers):
    _, hid = _parcel_with_harvest(_coop_id(), "Defo-Unverified", defo=None)
    lot = client.post("/lots", json={"harvest_ids": [hid]}, headers=auth_headers).json()
    pp = client.get(f"/lots/{lot['id']}/passport", headers=auth_headers).json()
    assert pp["summary"]["export_deforestation_unverified"] >= 1
    assert pp["summary"]["export_blocking_plantations"] == 0   # non vérifiée ne bloque pas
    # … et l'expédition passe (alerte, pas blocage).
    r = client.post(f"/lots/{lot['id']}/movements", json={"movement_type": "export_out"}, headers=auth_headers)
    assert r.status_code == 200, r.text


def test_clear_deforestation_no_alert(client, auth_headers):
    _, hid = _parcel_with_harvest(_coop_id(), "Defo-Clear", defo="clear")
    lot = client.post("/lots", json={"harvest_ids": [hid]}, headers=auth_headers).json()
    pp = client.get(f"/lots/{lot['id']}/passport", headers=auth_headers).json()
    assert pp["summary"]["export_deforestation_unverified"] == 0
    assert pp["summary"]["export_blocking_plantations"] == 0
