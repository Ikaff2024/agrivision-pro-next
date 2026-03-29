"""
Tests unitaires — CacaoEngine v1
Couvre les 4 modules individuels + l'agrégation globale + les cas limites.
"""
import pytest
from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.engine import run_engine
from app.cacao_engine.modules.disease_risk import disease_risk_module
from app.cacao_engine.modules.rainfall_balance import evaluate_rainfall_balance
from app.cacao_engine.modules.plantation_age import evaluate_plantation_age
from app.cacao_engine.modules.shade_balance import evaluate_shade_balance
from app.cacao_engine.rules.thresholds import risk_level_from_score


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_inputs(**kwargs) -> CacaoInputs:
    """Crée un CacaoInputs avec des valeurs neutres par défaut."""
    defaults = dict(
        country="Côte d'Ivoire",
        region="Soubré",
        rainfall_mm_month=120.0,   # optimal
        humidity_pct=65.0,         # neutre
        avg_temp_c=24.0,           # neutre
        plantation_age_years=15.0, # maturité
        shade_tree_density_pct=35.0,  # optimal
    )
    defaults.update(kwargs)
    return CacaoInputs(**defaults)


# ─── Thresholds ───────────────────────────────────────────────────────────────

class TestRiskLevelFromScore:
    def test_low_boundary(self):
        assert risk_level_from_score(0.0) == "LOW"
        assert risk_level_from_score(34.9) == "LOW"

    def test_medium_boundary(self):
        assert risk_level_from_score(35.0) == "MEDIUM"
        assert risk_level_from_score(69.9) == "MEDIUM"

    def test_high_boundary(self):
        assert risk_level_from_score(70.0) == "HIGH"
        assert risk_level_from_score(100.0) == "HIGH"

    def test_clamping(self):
        # Les scores hors limites doivent quand même retourner un niveau valide
        assert risk_level_from_score(-10.0) == "LOW"
        assert risk_level_from_score(150.0) == "HIGH"


# ─── Module disease_risk ──────────────────────────────────────────────────────

class TestDiseaseRiskModule:
    def test_optimal_conditions_score_zero(self):
        """Humidité faible, pluie faible, temp fraîche, ombrage normal → score 0."""
        inp = make_inputs(humidity_pct=60.0, rainfall_mm_month=100.0,
                          avg_temp_c=22.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 0.0
        assert result.risk_level == "LOW"

    def test_high_humidity_adds_40(self):
        inp = make_inputs(humidity_pct=88.0, rainfall_mm_month=100.0,
                          avg_temp_c=22.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 40.0

    def test_moderate_humidity_adds_20(self):
        inp = make_inputs(humidity_pct=78.0, rainfall_mm_month=100.0,
                          avg_temp_c=22.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 20.0

    def test_very_high_rain_adds_30(self):
        inp = make_inputs(humidity_pct=60.0, rainfall_mm_month=260.0,
                          avg_temp_c=22.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 30.0

    def test_high_rain_adds_15(self):
        inp = make_inputs(humidity_pct=60.0, rainfall_mm_month=180.0,
                          avg_temp_c=22.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 15.0

    def test_very_high_temp_adds_20(self):
        inp = make_inputs(humidity_pct=60.0, rainfall_mm_month=100.0,
                          avg_temp_c=31.0, shade_tree_density_pct=35.0)
        result = disease_risk_module(inp)
        assert result.score == 20.0

    def test_dense_shade_adds_15(self):
        inp = make_inputs(humidity_pct=60.0, rainfall_mm_month=100.0,
                          avg_temp_c=22.0, shade_tree_density_pct=75.0)
        result = disease_risk_module(inp)
        assert result.score == 15.0

    def test_worst_case_capped_at_100(self):
        """Toutes les conditions au pire → score capé à 100."""
        inp = make_inputs(humidity_pct=90.0, rainfall_mm_month=300.0,
                          avg_temp_c=32.0, shade_tree_density_pct=80.0)
        result = disease_risk_module(inp)
        assert result.score == 100.0
        assert result.risk_level == "HIGH"

    def test_critical_scenario_man(self):
        """Scénario 3 validé en production : Man, conditions critiques."""
        inp = make_inputs(humidity_pct=88.0, rainfall_mm_month=290.0,
                          avg_temp_c=31.0, shade_tree_density_pct=75.0)
        result = disease_risk_module(inp)
        # 40 (humidity≥85) + 30 (rain≥250) + 20 (temp≥30) + 15 (shade≥70) = 105 → 100
        assert result.score == 100.0


# ─── Module rainfall_balance ──────────────────────────────────────────────────

class TestRainfallBalance:
    def test_optimal_range_score_100(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=120.0))
        assert result.score == 100.0

    def test_too_low_score_30(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=50.0))
        assert result.score == 30.0

    def test_elevated_acceptable_score_70(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=175.0))
        assert result.score == 70.0

    def test_excess_score_40(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=290.0))
        assert result.score == 40.0

    def test_boundary_150_is_optimal(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=150.0))
        assert result.score == 100.0

    def test_boundary_151_is_elevated(self):
        result = evaluate_rainfall_balance(make_inputs(rainfall_mm_month=151.0))
        assert result.score == 70.0


# ─── Module plantation_age ────────────────────────────────────────────────────

class TestPlantationAge:
    def test_mature_score_100(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=15.0))
        assert result.score == 100.0

    def test_too_young_score_20(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=2.0))
        assert result.score == 20.0

    def test_growing_phase_score_60(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=6.0))
        assert result.score == 60.0

    def test_aging_score_50(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=30.0))
        assert result.score == 50.0

    def test_very_old_score_20(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=38.0))
        assert result.score == 20.0

    def test_boundary_25_is_mature(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=25.0))
        assert result.score == 100.0

    def test_boundary_8_is_mature(self):
        result = evaluate_plantation_age(make_inputs(plantation_age_years=8.0))
        assert result.score == 100.0


# ─── Module shade_balance ─────────────────────────────────────────────────────

class TestShadeBalance:
    def test_optimal_score_100(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=35.0))
        assert result.score == 100.0

    def test_insufficient_score_40(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=15.0))
        assert result.score == 40.0

    def test_elevated_score_70(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=60.0))
        assert result.score == 70.0

    def test_excessive_score_40(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=80.0))
        assert result.score == 40.0

    def test_boundary_50_is_optimal(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=50.0))
        assert result.score == 100.0

    def test_boundary_20_is_optimal(self):
        result = evaluate_shade_balance(make_inputs(shade_tree_density_pct=20.0))
        assert result.score == 100.0


# ─── Moteur global — intégration ─────────────────────────────────────────────

class TestRunEngine:
    def test_scenario_1_optimal_soubre(self):
        """Scénario 1 validé en prod : Soubré, tout optimal → score 0 / LOW."""
        inp = make_inputs(
            rainfall_mm_month=120.0,
            humidity_pct=65.0,
            avg_temp_c=24.0,
            plantation_age_years=15.0,
            shade_tree_density_pct=35.0,
        )
        report = run_engine(inp)
        assert report.global_score == 0.0
        assert report.global_risk_level == "LOW"

    def test_scenario_2_medium_daloa(self):
        """Scénario 2 validé en prod : Daloa → score 36.25 / MEDIUM."""
        inp = make_inputs(
            rainfall_mm_month=180.0,
            humidity_pct=78.0,
            avg_temp_c=27.0,
            plantation_age_years=6.0,
            shade_tree_density_pct=55.0,
        )
        report = run_engine(inp)
        assert report.global_score == pytest.approx(36.25, abs=0.1)
        assert report.global_risk_level == "MEDIUM"

    def test_scenario_3_high_man(self):
        """Scénario 3 validé en prod : Man → score 75 / HIGH."""
        inp = make_inputs(
            rainfall_mm_month=290.0,
            humidity_pct=88.0,
            avg_temp_c=31.0,
            plantation_age_years=38.0,
            shade_tree_density_pct=75.0,
        )
        report = run_engine(inp)
        assert report.global_score == pytest.approx(75.0, abs=0.1)
        assert report.global_risk_level == "HIGH"

    def test_report_has_4_modules(self):
        """Le rapport doit toujours contenir 4 modules."""
        report = run_engine(make_inputs())
        assert len(report.module_results) == 4

    def test_module_names_present(self):
        """Les 4 noms de modules doivent être présents."""
        report = run_engine(make_inputs())
        names = {m.module_name for m in report.module_results}
        assert names == {"disease_risk", "plantation_age", "rainfall_balance", "shade_balance"}

    def test_global_score_between_0_and_100(self):
        """Le score global doit toujours être dans [0, 100]."""
        for humidity in [0, 50, 100]:
            for rain in [0, 150, 400]:
                inp = make_inputs(humidity_pct=float(humidity),
                                  rainfall_mm_month=float(rain))
                report = run_engine(inp)
                assert 0.0 <= report.global_score <= 100.0

    def test_quality_modules_inversion(self):
        """
        Vérification que l'inversion est bien appliquée :
        conditions optimales → score global 0 (pas 75 comme avant le fix).
        """
        inp = make_inputs(
            humidity_pct=60.0,
            avg_temp_c=22.0,
            rainfall_mm_month=120.0,
            plantation_age_years=15.0,
            shade_tree_density_pct=35.0,
        )
        report = run_engine(inp)
        # Si l'inversion n'est pas appliquée, le score serait ~75 (HIGH)
        assert report.global_score < 35.0, (
            f"Score={report.global_score} — L'inversion des modules qualité "
            f"n'est peut-être pas appliquée."
        )
