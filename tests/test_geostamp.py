"""Géo-horodatage anti-fraude de la collecte terrain — socle (service + table).

Vérifie le calcul de distance, le verdict d'intégrité (verified/far/no_fix/
overridden/no_reference) et l'enregistrement. cf. retours terrain « verrouiller la triche ».
"""
from app.services import geostamp
from tests.conftest import TestingSessionLocal


# ── Distance ─────────────────────────────────────────────────────────────────
def test_haversine_same_point_zero():
    assert geostamp.haversine_m(5.78, -6.59, 5.78, -6.59) == 0.0


def test_haversine_one_degree_lat_about_111km():
    d = geostamp.haversine_m(5.0, -6.59, 6.0, -6.59)
    assert 110000 < d < 112000


# ── Verdict ──────────────────────────────────────────────────────────────────
def test_status_verified_when_close():
    status, dist = geostamp.compute_status(5.7800, -6.5900, 5.7802, -6.5901, threshold_m=500)
    assert status == "verified" and dist is not None and dist < 500


def test_status_far_when_beyond_threshold():
    status, dist = geostamp.compute_status(5.78, -6.59, 5.80, -6.59, threshold_m=500)
    assert status == "far" and dist > 500


def test_status_no_fix_without_gps_or_reason():
    assert geostamp.compute_status(None, None, 5.78, -6.59)[0] == "no_fix"


def test_status_overridden_with_reason():
    assert geostamp.compute_status(None, None, 5.78, -6.59, override_reason="Pas de signal GPS au champ")[0] == "overridden"


def test_status_no_reference_without_expected():
    assert geostamp.compute_status(5.78, -6.59, None, None)[0] == "no_reference"


# ── Enregistrement ───────────────────────────────────────────────────────────
def test_record_and_latest(client):
    db = TestingSessionLocal()
    try:
        gs = geostamp.record_geostamp(
            db, entity_type="monitoring_visit", entity_id=42, cooperative_id=1,
            captured_lat=5.7801, captured_lng=-6.5901,
            expected_lat=5.7800, expected_lng=-6.5900,
            recorded_by="agent@coop.ci", threshold_m=500,
        )
        db.commit()
        assert gs.geo_status == "verified" and gs.distance_m is not None
        assert gs.captured_at is not None  # heure serveur posée

        latest = geostamp.latest_for(db, "monitoring_visit", 42)
        assert latest is not None and latest.id == gs.id
        m = geostamp.latest_map(db, "monitoring_visit", [42, 99])
        assert 42 in m and 99 not in m
        assert geostamp.geostamp_dict(latest)["geo_status"] == "verified"
    finally:
        db.close()
