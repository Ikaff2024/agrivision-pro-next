from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score


def evaluate_rainfall_balance(inp: CacaoInputs) -> ModuleResult:
    """Évalue si les conditions de pluviométrie sont optimales pour le cacao."""
    rain = inp.rainfall_mm_month
    if rain < 80.0:
        score, reason = 30.0, "Pluviométrie trop faible pour une croissance optimale."
    elif rain <= 150.0:
        score, reason = 100.0, "Pluviométrie optimale pour le cacao."
    elif rain <= 200.0:
        score, reason = 70.0, "Pluviométrie élevée mais encore acceptable."
    else:
        score, reason = 40.0, "Excès de pluie : favorise les maladies fongiques."

    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="rainfall_balance",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=[reason],
    )
