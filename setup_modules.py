"""
Script utilitaire Windows — crée les fichiers manquants du moteur CacaoEngine.
Lancer depuis la racine du projet : python setup_modules.py
"""
import os

os.makedirs("app/cacao_engine/modules", exist_ok=True)
os.makedirs("app/cacao_engine/rules", exist_ok=True)

files = {
"app/cacao_engine/modules/disease_risk.py": '''from app.cacao_engine.inputs import CacaoInputs
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
''',

"app/cacao_engine/modules/plantation_age.py": '''from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import ModuleResult
from app.cacao_engine.rules.thresholds import risk_level_from_score

def evaluate_plantation_age(inp: CacaoInputs) -> ModuleResult:
    if inp.plantation_age_years is None:
        score, reason = 20.0, "Age inconnu : penalite de prudence."
    elif inp.plantation_age_years < 3.0:
        score, reason = 20.0, "Plantation trop jeune : production encore faible."
    elif inp.plantation_age_years < 8.0:
        score, reason = 60.0, "Plantation en phase de montee en production."
    elif inp.plantation_age_years <= 25.0:
        score, reason = 100.0, "Plantation en pleine maturite productive."
    elif inp.plantation_age_years <= 35.0:
        score, reason = 50.0, "Plantation vieillissante : rendement en declin."
    else:
        score, reason = 20.0, "Plantation tres vieille : replantation recommandee."
    final_score = max(0.0, min(100.0, score))
    return ModuleResult(
        module_name="plantation_age",
        score=final_score,
        risk_level=risk_level_from_score(final_score),
        reasons=[reason]
    )
''',

"app/cacao_engine/modules/rainfall_balance.py": '''from app.cacao_engine.inputs import CacaoInputs
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
''',

"app/cacao_engine/modules/shade_balance.py": '''from app.cacao_engine.inputs import CacaoInputs
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
''',

"app/cacao_engine/modules/__init__.py": "",
"app/cacao_engine/rules/__init__.py": "",

"app/cacao_engine/rules/thresholds.py": '''from enum import Enum

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

def risk_level_from_score(score: float) -> str:
    safe = max(0.0, min(100.0, score))
    if safe < 35.0:
        return RiskLevel.LOW.value
    elif safe < 70.0:
        return RiskLevel.MEDIUM.value
    return RiskLevel.HIGH.value
''',
}

for path, content in files.items():
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK  {path}")

print("\nTous les fichiers crees. Lance : uvicorn main:app --reload")
