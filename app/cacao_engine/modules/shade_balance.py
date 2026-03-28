from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score

def evaluate_shade_balance(inp: CacaoInputs) -> ModuleResult:
    if inp.shade_tree_density_pct is None:
        score, reason = 40.0, "Densite d ombrage inconnue : penalite appliquee."
    elif inp.shade_tree_density_pct < 20.0:
        score, reason = 40.0, "Ombrage insuffisant : stress thermique possible."
    elif inp.shade_tree_density_pct <= 50.0:
        score, reason = 100.0, "Ombrage optimal pour la culture du cacao."
    elif inp.shade_tree_density_pct <= 70.0:
        score, reason = 70.0, "Ombrage eleve : peut limiter la photosynthese."
    else:
        score, reason = 40.0, "Ombrage excessif : humidite stagnante et risque de maladies."
    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="shade_balance",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=[reason]
    )
