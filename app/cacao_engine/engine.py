from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.cacao_engine.rules.thresholds import risk_level_from_score
from app.cacao_engine.modules.disease_risk import disease_risk_module
from app.cacao_engine.modules.plantation_age import evaluate_plantation_age
from app.cacao_engine.modules.rainfall_balance import evaluate_rainfall_balance
from app.cacao_engine.modules.shade_balance import evaluate_shade_balance

# Modules dont le score est un score de QUALITÉ (haut = bon).
# Ils sont inversés (100 - score) avant agrégation pour que le score
# global soit un score de RISQUE cohérent (haut = mauvais).
_QUALITY_MODULES = {"plantation_age", "rainfall_balance", "shade_balance"}


def run_engine(inp: CacaoInputs) -> EngineReport:
    """
    Point d'entrée unique du moteur CacaoEngine v1.
    Exécute les 4 sous-modules et retourne le rapport agrégé.

    Sémantique des scores :
    - disease_risk     → score de RISQUE   (0 = sain,    100 = critique)
    - plantation_age   → score de QUALITÉ  (0 = déclin,  100 = optimal)
    - rainfall_balance → score de QUALITÉ  (0 = mauvais, 100 = optimal)
    - shade_balance    → score de QUALITÉ  (0 = mauvais, 100 = optimal)

    Les modules QUALITÉ sont inversés avant agrégation pour garantir
    qu'un score global élevé signifie toujours un risque élevé.
    """
    module_results = [
        disease_risk_module(inp),
        evaluate_plantation_age(inp),
        evaluate_rainfall_balance(inp),
        evaluate_shade_balance(inp),
    ]

    risk_contributions = [
        100.0 - r.score if r.module_name in _QUALITY_MODULES else r.score
        for r in module_results
    ]

    global_score = round(sum(risk_contributions) / len(risk_contributions), 2)

    return EngineReport(
        global_score=global_score,
        global_risk_level=risk_level_from_score(global_score),
        module_results=module_results,
    )
