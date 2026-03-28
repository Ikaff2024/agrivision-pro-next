from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score

def evaluate_rainfall_balance(inp: CacaoInputs) -> ModuleResult:
    rain = inp.rainfall_mm_month
    if rain < 80.0:
        score, reason = 30.0, "Pluviometrie trop faible pour une croissance optimale."
    elif rain <= 150.0:
        score, reason = 100.0, "Pluviometrie optimale pour le cacao."
    elif rain <= 200.0:
        score, reason = 70.0, "Pluviometrie elevee mais encore acceptable."
    else:
        score, reason = 40.0, "Exces de pluie : favorise les maladies fongiques."
    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="rainfall_balance",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=[reason]
    )
