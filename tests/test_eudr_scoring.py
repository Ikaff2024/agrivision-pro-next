"""Tests pour le moteur de scoring EUDR-01a (5 regles)."""
import json
from datetime import date, datetime, timedelta

import pytest

from app.db.models import (
    Cooperative,
    DeforestationCheck,
    Inspection,
    Plantation,
    PlantationBoundary,
    Producer,
    User,
)
from app.db.models_social import BlockReason, BlockStatus, TraceabilityBlock
from app.eudr.scoring import (
    AREA_TOLERANCE_PCT,
    CI_BBOX,
    EudrScore,
    METHODOLOGY_VERSION,
    _status_from_score,
    compute_eudr_score,
    rule_area_matches,
    rule_gps_in_cocoa_zone,
    rule_no_active_traceability_block,
    rule_no_deforestation,
    rule_polygon_valid,
    rule_recent_inspection,
)
from tests.conftest import TestingSessionLocal


# ----------------------------------------------------------------------------
# Helpers de seed
# ----------------------------------------------------------------------------

VALID_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [-6.59, 5.78],
        [-6.58, 5.78],
        [-6.58, 5.79],
        [-6.59, 5.79],
        [-6.59, 5.78],
    ]],
})

POLYGON_OUTSIDE_CI = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [10.0, 20.0],
        [10.5, 20.0],
        [10.5, 20.5],
        [10.0, 20.0],
    ]],
})


def _make_plantation(db, *, hectares=1.0, with_producer=False, with_coop=True):
    coop = Cooperative(name="Coop EUDR", country="CI") if with_coop else None
    producer = None
    if coop:
        db.add(coop)
        db.flush()  # ensure coop.id is set
    if with_producer:
        producer = Producer(cooperative_id=coop.id if coop else None, nom_complet="Producteur EUDR", is_active=True)
        db.add(producer)
        db.flush()  # ensure producer.id is set
    p = Plantation(
        name="Parcelle EUDR",
        owner_name="Test",
        country="Cote d'Ivoire",
        region="Soubre",
        latitude=5.785,
        longitude=-6.585,
        hectares=hectares,
        cooperative_id=coop.id if coop else None,
        producer_id=producer.id if producer else None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _add_boundary(db, plantation, geojson=VALID_POLYGON, area=1.0, points=5):
    b = PlantationBoundary(
        plantation_id=plantation.id,
        geojson=geojson,
        area_hectares=area,
        points_count=points,
        method="manual",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    # Force loading of the boundary relationship before session detach
    db.refresh(plantation)
    _ = plantation.boundary  # trigger lazy load
    return b


def _add_deforestation_check(db, plantation, *, verdict="clear", source="manual",
                             forest_loss_year=None):
    c = DeforestationCheck(
        plantation_id=plantation.id,
        verdict=verdict,
        source=source,
        forest_loss_year=forest_loss_year,
        check_date=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ----------------------------------------------------------------------------
# Regle 1 : polygon_valid
# ----------------------------------------------------------------------------

def test_polygon_valid_no_boundary(client):
    r = rule_polygon_valid(None)
    assert r.passed is False
    assert "Aucune" in r.detail


def test_polygon_valid_with_valid_geojson(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    b = _add_boundary(db, p, points=5)
    r = rule_polygon_valid(b)
    db.close()
    assert r.passed is True


def test_polygon_valid_with_invalid_json(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    b = _add_boundary(db, p, geojson="not-json", points=5)
    r = rule_polygon_valid(b)
    db.close()
    assert r.passed is False
    assert "invalide" in r.detail.lower()


def test_polygon_valid_too_few_points(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    b = _add_boundary(db, p, points=2)
    r = rule_polygon_valid(b)
    db.close()
    assert r.passed is False


# ----------------------------------------------------------------------------
# Regle 2 : area_matches
# ----------------------------------------------------------------------------

def test_area_matches_within_tolerance(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=2.0)
    b = _add_boundary(db, p, area=2.15)  # +7.5%
    r = rule_area_matches(p, b)
    db.close()
    assert r.passed is True


def test_area_matches_outside_tolerance(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=2.0)
    b = _add_boundary(db, p, area=3.0)  # +50%
    r = rule_area_matches(p, b)
    db.close()
    assert r.passed is False


def test_area_matches_missing_declared(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=None)
    b = _add_boundary(db, p, area=2.0)
    r = rule_area_matches(p, b)
    db.close()
    assert r.passed is False
    assert "declaree manquante" in r.detail.lower()


def test_area_matches_no_boundary(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=2.0)
    db.close()
    r = rule_area_matches(p, None)
    assert r.passed is False


# ----------------------------------------------------------------------------
# Regle 3 : gps_in_cocoa_zone
# ----------------------------------------------------------------------------

def test_gps_in_cocoa_zone_polygon_inside(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    b = _add_boundary(db, p, geojson=VALID_POLYGON)
    r = rule_gps_in_cocoa_zone(p, b)
    db.close()
    assert r.passed is True


def test_gps_in_cocoa_zone_polygon_outside(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    b = _add_boundary(db, p, geojson=POLYGON_OUTSIDE_CI)
    r = rule_gps_in_cocoa_zone(p, b)
    db.close()
    assert r.passed is False
    assert "hors bbox" in r.detail.lower()


def test_gps_in_cocoa_zone_fallback_point(client):
    """Sans polygone, on regarde le point GPS principal."""
    db = TestingSessionLocal()
    p = _make_plantation(db)
    db.close()
    r = rule_gps_in_cocoa_zone(p, None)
    assert r.passed is True  # 5.785, -6.585 est dans la bbox CI


def test_gps_in_cocoa_zone_no_data(client):
    db = TestingSessionLocal()
    p = Plantation(name="X", owner_name="X", country="CI", latitude=None, longitude=None)
    db.add(p); db.commit(); db.refresh(p)
    db.close()
    r = rule_gps_in_cocoa_zone(p, None)
    assert r.passed is False


# ----------------------------------------------------------------------------
# Regle 4 : recent_inspection
# ----------------------------------------------------------------------------

def test_recent_inspection_within_window(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    db.add(Inspection(
        plantation_id=p.id,
        type="EXTERNE",
        date=datetime.utcnow() - timedelta(days=120),
        resultat="CONFORME",
    ))
    db.commit()
    r = rule_recent_inspection(p, db)
    db.close()
    assert r.passed is True


def test_recent_inspection_too_old(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    db.add(Inspection(
        plantation_id=p.id,
        type="INTERNE",
        date=datetime.utcnow() - timedelta(days=400),
        resultat="CONFORME",
    ))
    db.commit()
    r = rule_recent_inspection(p, db)
    db.close()
    assert r.passed is False


def test_recent_inspection_none(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    r = rule_recent_inspection(p, db)
    db.close()
    assert r.passed is False
    assert "aucune" in r.detail.lower()


# ----------------------------------------------------------------------------
# Regle 5 : no_active_traceability_block
# ----------------------------------------------------------------------------

def test_no_block_when_no_producer(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, with_producer=False)
    r = rule_no_active_traceability_block(p, db)
    db.close()
    assert r.passed is True
    assert "non applicable" in r.detail.lower()


def test_no_block_no_active_block(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, with_producer=True)
    r = rule_no_active_traceability_block(p, db)
    db.close()
    assert r.passed is True


def test_no_block_with_active_block(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, with_producer=True)
    user = User(email="eudr.audit@test.ci", password_hash="x", role="admin")
    db.add(user); db.flush()
    db.add(TraceabilityBlock(
        producer_id=p.producer_id,
        block_reason=BlockReason.CHILD_LABOR_CASE,
        block_description="test",
        status=BlockStatus.ACTIVE,
        blocked_by=user.id,
    ))
    db.commit()
    r = rule_no_active_traceability_block(p, db)
    assert r.passed is False
    assert "child_labor_case" in r.detail
    db.close()


def test_resolved_block_does_not_count(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, with_producer=True)
    user = User(email="eudr.resolver@test.ci", password_hash="x", role="admin")
    db.add(user); db.flush()
    db.add(TraceabilityBlock(
        producer_id=p.producer_id,
        block_reason=BlockReason.NON_COMPLIANCE,
        block_description="resolved",
        status=BlockStatus.RESOLVED,
        blocked_by=user.id,
    ))
    db.commit()
    r = rule_no_active_traceability_block(p, db)
    assert r.passed is True
    db.close()


# ----------------------------------------------------------------------------
# Status thresholds
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (0, "non_conforme"), (1, "non_conforme"),
    (2, "a_verifier"), (3, "a_verifier"),
    (4, "conforme"), (5, "conforme"),
])
def test_status_thresholds(score, expected):
    status, _ = _status_from_score(score, 5)
    assert status == expected


# ----------------------------------------------------------------------------
# Orchestrateur compute_eudr_score
# ----------------------------------------------------------------------------

def test_compute_score_perfect_plantation(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=1.0, with_producer=True)
    _add_boundary(db, p, geojson=VALID_POLYGON, area=1.05, points=5)
    db.add(Inspection(plantation_id=p.id, type="EXTERNE", date=datetime.utcnow() - timedelta(days=30)))
    db.commit()
    _add_deforestation_check(db, p, verdict="clear")
    s = compute_eudr_score(p, db)
    db.close()
    assert s.score == 5          # 5 regles ENVIRONNEMENTALES (social dissocie)
    assert s.max_score == 5
    assert s.status == "conforme"
    assert s.badge_color == "green"
    assert s.has_polygon is True
    assert s.methodology_version == METHODOLOGY_VERSION


def test_area_mismatch_caps_conforme_to_a_verifier(client):
    """Règle bloquante : une superficie incohérente (>20%) interdit le badge
    « conforme » même si le prorata l'accorderait (4/5) — cohérence fiche ↔ menu EUDR."""
    db = TestingSessionLocal()
    p = _make_plantation(db, hectares=1.0, with_producer=True)
    _add_boundary(db, p, geojson=VALID_POLYGON, area=5.0, points=5)  # aire géo très ≠ déclarée
    db.add(Inspection(plantation_id=p.id, type="EXTERNE", date=datetime.utcnow() - timedelta(days=10)))
    db.commit()
    _add_deforestation_check(db, p, verdict="clear")
    s = compute_eudr_score(p, db)
    db.close()
    failed = {r.rule_id for r in s.rules if not r.passed}
    assert s.score == 4 and "area_matches" in failed   # seule la cohérence d'aire échoue
    assert s.status == "a_verifier"                      # bloquée, pas « conforme »
    assert s.badge_color == "orange"


# ----------------------------------------------------------------------------
# Regle 6 (EUDR-01b) : no_deforestation
# ----------------------------------------------------------------------------

def test_deforestation_no_check_fails(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    r = rule_no_deforestation(p, db)
    db.close()
    assert r.passed is False
    assert "Aucun controle" in r.detail


def test_deforestation_clear_passes(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    _add_deforestation_check(db, p, verdict="clear", source="hansen_gfc")
    r = rule_no_deforestation(p, db)
    db.close()
    assert r.passed is True


def test_deforestation_detected_fails(client):
    db = TestingSessionLocal()
    p = _make_plantation(db)
    _add_deforestation_check(db, p, verdict="deforestation_detected", forest_loss_year=2022)
    r = rule_no_deforestation(p, db)
    db.close()
    assert r.passed is False
    assert "2022" in r.detail


def test_deforestation_latest_check_wins(client):
    """Le controle le plus recent prime (clear apres une detection => passe)."""
    db = TestingSessionLocal()
    p = _make_plantation(db)
    _add_deforestation_check(db, p, verdict="deforestation_detected", forest_loss_year=2021)
    _add_deforestation_check(db, p, verdict="clear", source="field_visit")
    r = rule_no_deforestation(p, db)
    db.close()
    assert r.passed is True


def test_compute_score_no_polygon_no_inspection(client):
    db = TestingSessionLocal()
    p = _make_plantation(db, with_producer=True)  # only GPS point in bbox
    s = compute_eudr_score(p, db)
    db.close()
    # polygon_valid: False (no polygon)
    # area_matches: False (no geo area)
    # gps_in_cocoa_zone: True (fallback point in bbox)
    # recent_inspection: False
    # no_deforestation: False (aucun controle) => 1/5 (social dissocie)
    assert s.score == 1
    assert s.max_score == 5
    assert s.status == "non_conforme"  # 1/5 = 20% (< 40%)
    assert s.badge_color == "red"
    assert s.has_polygon is False


def test_compute_score_worst_case(client):
    db = TestingSessionLocal()
    # Plantation hors bbox + sans producteur + sans rien
    p = Plantation(
        name="X", owner_name="X", country="X",
        latitude=20.0, longitude=10.0, hectares=None,
    )
    db.add(p); db.commit(); db.refresh(p)
    s = compute_eudr_score(p, db)
    db.close()
    # Toutes les règles échouent (social dissocié → plus de no_active_block vacuously-true)
    assert s.score == 0
    assert s.status == "non_conforme"
    assert s.badge_color == "red"
