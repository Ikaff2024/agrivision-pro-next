from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score


def evaluate_plantation_age(inp: CacaoInputs) -> ModuleResult:
    """Évalue le potentiel de rendement en fonction de l'âge de la plantation."""
    if inp.plantation_age_years is None:
        score, reason = 20.0, "Âge inconnu : pénalité de prudence appliquée."
    elif inp.plantation_age_years < 3.0:
        score, reason = 20.0, "Plantation trop jeune : production encore faible."
    elif inp.plantation_age_years < 8.0:
        score, reason = 60.0, "Plantation en phase de montée en production."
    elif inp.plantation_age_years <= 25.0:
        score, reason = 100.0, "Plantation en pleine maturité productive."
    elif inp.plantation_age_years <= 35.0:
        score, reason = 50.0, "Plantation vieillissante : rendement en déclin."
    else:
        score, reason = 20.0, "Plantation très vieille : replantation recommandée."

    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="plantation_age",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=[reason],
    )
