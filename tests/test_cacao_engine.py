"""Tests unitaires — moteur CacaoEngine (sans base de données)."""
import pytest
from app.cacao_engine.engine import run_engine
from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.rules.thresholds import risk_level_from_score
from app.cacao_engine.modules.disease_risk import disease_risk_module
from app.cacao_engine.modules.plantation_age import evaluate_plantation_age
from app.cacao_engine.modules.rainfall_balance import evaluate_rainfall_balance
from app.cacao_engine.modules.shade_balance import evaluate_shade_balance


def make_inputs(**kwargs):
    defaults = dict(
        country="Côte d'Ivoire",
        rainfall_mm_month=120.0,
        humidity_pct=70.0,
        avg_temp_c=27.0,
    )
    defaults.update(kwargs)
    return CacaoInputs(**defaults)


# ── Thresholds ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (0.0, "LOW"), (34.9, "LOW"),
    (35.0, "MEDIUM"), (69.9, "MEDIUM"),
    (70.0, "HIGH"), (100.0, "HIGH"),
])
def test_risk_level_from_score(score, expected):
    assert risk_level_from_score(score) == expected


# ── Disease risk ─────────────────────────────────────────────────────────────

def test_disease_risk_high_humidity():
    result = disease_risk_module(make_inputs(humidity_pct=90.0))
    assert result.score >= 40.0

def test_disease_risk_low_conditions():
    result = disease_risk_module(make_inputs(
        humidity_pct=60.0, rainfall_mm_month=100.0, avg_temp_c=24.0, shade_tree_density_pct=30.0
    ))
    assert result.score == 0.0
    assert result.risk_level == "LOW"

def test_disease_risk_no_shade_penalty():
    result = disease_risk_module(make_inputs(shade_tree_density_pct=None))
    assert result.score >= 10.0


# ── Plantation age ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("age,expected_score", [
    (1.0, 20.0),
    (5.0, 60.0),
    (15.0, 100.0),
    (30.0, 50.0),
    (40.0, 20.0),
    (None, 20.0),
])
def test_plantation_age_scores(age, expected_score):
    result = evaluate_plantation_age(make_inputs(plantation_age_years=age))
    assert result.score == expected_score


# ── Rainfall balance ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("rain,expected_score", [
    (50.0, 30.0),
    (120.0, 100.0),
    (180.0, 70.0),
    (300.0, 40.0),
])
def test_rainfall_balance_scores(rain, expected_score):
    result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=rain))
    assert result.score == expected_score


# ── Shade balance ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shade,expected_score", [
    (10.0, 40.0),
    (35.0, 100.0),
    (60.0, 70.0),
    (80.0, 40.0),
    (None, 40.0),
])
def test_shade_balance_scores(shade, expected_score):
    result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=shade))
    assert result.score == expected_score


# ── Engine global ─────────────────────────────────────────────────────────────

def test_engine_returns_4_modules():
    report = run_engine(make_inputs())
    assert len(report.module_results) == 4

def test_engine_score_is_average():
    inp = make_inputs()
    report = run_engine(inp)
    expected = sum(r.score for r in report.module_results) / 4
    assert abs(report.global_score - round(expected, 2)) < 0.01

def test_engine_score_bounded():
    report = run_engine(make_inputs(
        humidity_pct=100.0, rainfall_mm_month=500.0, avg_temp_c=45.0
    ))
    assert 0.0 <= report.global_score <= 100.0

def test_engine_risk_level_consistent():
    report = run_engine(make_inputs())
    assert report.global_risk_level == risk_level_from_score(report.global_score)

def test_engine_known_high_risk():
    """Conditions extrêmes → risque HIGH attendu."""
    report = run_engine(make_inputs(
        humidity_pct=95.0,
        rainfall_mm_month=300.0,
        avg_temp_c=33.0,
        shade_tree_density_pct=80.0,
        plantation_age_years=1.0,
    ))
    assert report.global_risk_level == "HIGH"

def test_engine_known_low_risk():
    """Conditions optimales → risque LOW attendu."""
    report = run_engine(make_inputs(
        humidity_pct=60.0,
        rainfall_mm_month=120.0,
        avg_temp_c=24.0,
        shade_tree_density_pct=35.0,
        plantation_age_years=15.0,
    ))
    assert report.global_risk_level == "LOW"
