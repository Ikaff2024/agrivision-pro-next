from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score

def disease_risk_module(inp: CacaoInputs) -> ModuleResult:
    score = 0.0
    reasons = []
    if inp.humidity_pct >= 85.0:
        score += 40.0
        reasons.append(f"Humidite tres elevee ({inp.humidity_pct}%) : fort risque fongique (+40).")
    elif inp.humidity_pct >= 75.0:
        score += 20.0
        reasons.append(f"Humidite elevee ({inp.humidity_pct}%) : risque modere (+20).")
    if inp.rainfall_mm_month >= 250.0:
        score += 30.0
        reasons.append(f"Pluviometrie tres forte ({inp.rainfall_mm_month} mm) (+30).")
    elif inp.rainfall_mm_month >= 150.0:
        score += 15.0
        reasons.append(f"Pluviometrie forte ({inp.rainfall_mm_month} mm) (+15).")
    if inp.avg_temp_c >= 30.0:
        score += 20.0
        reasons.append(f"Temperature tres elevee ({inp.avg_temp_c}C) (+20).")
    elif inp.avg_temp_c >= 26.0:
        score += 10.0
        reasons.append(f"Temperature chaude ({inp.avg_temp_c}C) (+10).")
    if inp.shade_tree_density_pct is None:
        score += 10.0
        reasons.append("Ombrage inconnu : penalite de prudence (+10).")
    elif inp.shade_tree_density_pct >= 70.0:
        score += 15.0
        reasons.append(f"Ombrage trop dense ({inp.shade_tree_density_pct}%) (+15).")
    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="disease_risk",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=reasons
    )
