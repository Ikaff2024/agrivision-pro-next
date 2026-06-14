"""Tests du cache de score EUDR (P1 — passage à l'échelle 7000+ parcelles).

Vérifie que le score mis en cache reflète exactement le calcul live, que le
peuplement paresseux (`ensure_scores`) est correct + idempotent, et que le
recompute en masse est scopé par coopérative.
"""
import json

from app.db.models import Cooperative, Plantation, PlantationBoundary
from app.eudr.scoring import compute_eudr_score
from app.eudr.score_cache import (
    cached_dict,
    ensure_scores,
    refresh_all_eudr,
    refresh_plantation_eudr,
)
from tests.conftest import TestingSessionLocal

VALID_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [-6.59, 5.78], [-6.58, 5.78], [-6.58, 5.79], [-6.59, 5.79], [-6.59, 5.78],
    ]],
})


def _coop(db, name="Coop Cache"):
    c = Cooperative(name=name, country="CI")
    db.add(c)
    db.flush()
    return c


def _plant(db, coop, *, hectares=1.0, name="P"):
    p = Plantation(
        name=name, owner_name="T", country="CI", region="Soubre",
        latitude=5.785, longitude=-6.585, hectares=hectares,
        cooperative_id=coop.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _boundary(db, p, area=1.0):
    b = PlantationBoundary(
        plantation_id=p.id, geojson=VALID_POLYGON,
        area_hectares=area, points_count=5, method="manual",
    )
    db.add(b)
    db.commit()
    db.refresh(p)
    _ = p.boundary  # force lazy load
    return b


def test_refresh_writes_cache_matching_live_compute(client):
    db = TestingSessionLocal()
    try:
        p = _plant(db, _coop(db))
        assert p.eudr_computed_at is None
        live = compute_eudr_score(p, db)
        refresh_plantation_eudr(p, db)
        db.commit()
        db.refresh(p)
        assert p.eudr_computed_at is not None
        assert p.eudr_status == live.status
        assert p.eudr_score == live.score
        assert p.eudr_max_score == live.max_score
        assert bool(p.eudr_has_polygon) == live.has_polygon
        assert p.eudr_rules_failed == [r.rule_id for r in live.rules if not r.passed]
    finally:
        db.close()


def test_ensure_scores_populates_then_idempotent(client):
    db = TestingSessionLocal()
    try:
        coop = _coop(db, "Coop Ensure")
        ps = [_plant(db, coop, name=f"P{i}") for i in range(3)]
        assert all(p.eudr_computed_at is None for p in ps)
        ensure_scores(ps, db)
        assert all(p.eudr_computed_at is not None for p in ps)
        stamps = [p.eudr_computed_at for p in ps]
        ensure_scores(ps, db)  # 2e passe : ne doit rien recalculer
        assert [p.eudr_computed_at for p in ps] == stamps
    finally:
        db.close()


def test_cache_consistent_with_polygon(client):
    db = TestingSessionLocal()
    try:
        p = _plant(db, _coop(db, "Coop Consist"), hectares=1.0)
        _boundary(db, p, area=1.0)
        live = compute_eudr_score(p, db)
        refresh_plantation_eudr(p, db)
        db.commit()
        db.refresh(p)
        d = cached_dict(p)
        assert d["status"] == live.status
        assert d["has_polygon"] is True
        assert "polygon_valid" not in (p.eudr_rules_failed or [])
    finally:
        db.close()


def test_refresh_all_scoped_by_coop(client):
    db = TestingSessionLocal()
    try:
        coop_a = _coop(db, "Coop A")
        coop_b = _coop(db, "Coop B")
        pa = [_plant(db, coop_a, name=f"A{i}") for i in range(2)]
        pb = [_plant(db, coop_b, name=f"B{i}") for i in range(3)]
        n = refresh_all_eudr(db, coop_id=coop_a.id)
        assert n == 2
        for p in pa + pb:
            db.refresh(p)
        assert all(p.eudr_computed_at is not None for p in pa)
        assert all(p.eudr_computed_at is None for p in pb)  # coop B non touchée
    finally:
        db.close()
