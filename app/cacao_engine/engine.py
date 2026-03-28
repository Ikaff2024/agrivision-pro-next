from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.cacao_engine.rules.thresholds import risk_level_from_score
from app.cacao_engine.modules.disease_risk import disease_risk_module
from app.cacao_engine.modules.plantation_age import evaluate_plantation_age
from app.cacao_engine.modules.rainfall_balance import evaluate_rainfall_balance
from app.cacao_engine.modules.shade_balance import evaluate_shade_balance


def run_engine(inp: CacaoInputs) -> EngineReport:
    """
    Point d'entrée unique du moteur CacaoEngine v1.
    Exécute les 4 sous-modules et retourne le rapport agrégé.
    """
    module_results = [
        disease_risk_module(inp),
        evaluate_plantation_age(inp),
        evaluate_rainfall_balance(inp),
        evaluate_shade_balance(inp),
    ]

    global_score = sum(r.score for r in module_results) / len(module_results)

    return EngineReport(
        global_score=round(global_score, 2),
        global_risk_level=risk_level_from_score(global_score),
        module_results=module_results,
    )
