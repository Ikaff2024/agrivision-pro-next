"""
Script utilitaire Windows — crée tous les fichiers manquants restants.
Lancer depuis la racine du projet : python setup_remaining.py
"""
import os

# S'assurer que tous les dossiers existent
dirs = [
    "app", "app/db", "app/auth", "app/api",
    "app/cacao_engine", "app/cacao_engine/rules", "app/cacao_engine/modules",
    "app/ml", "app/satellite", "tests", "uploads"
]
for d in dirs:
    os.makedirs(d, exist_ok=True)

files = {

"app/satellite/ndvi_service.py": '''import random
from typing import Dict, Union

def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    """Service NDVI simule — connecter a Sentinel Hub en production."""
    ndvi = round(random.uniform(0.3, 0.9), 2)
    if ndvi > 0.7:
        status = "HEALTHY"
    elif ndvi > 0.5:
        status = "MODERATE"
    else:
        status = "STRESSED"
    return {"ndvi": ndvi, "vegetation_status": status}
''',

"app/satellite/__init__.py": "",

"app/ml/image_diagnosis.py": '''import time

def analyze_leaf_image(image_path: str) -> dict:
    """Simule l inference d un modele ML de detection de maladies foliaires."""
    time.sleep(0.5)
    return {
        "disease": "Black Pod Disease",
        "confidence": 0.78,
        "severity": "MEDIUM",
        "recommendation": "Inspecter les cabosses et appliquer un fongicide a base de cuivre.",
    }
''',

"app/ml/__init__.py": "",

"app/cacao_engine/engine.py": '''from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.cacao_engine.rules.thresholds import risk_level_from_score
from app.cacao_engine.modules.disease_risk import disease_risk_module
from app.cacao_engine.modules.plantation_age import evaluate_plantation_age
from app.cacao_engine.modules.rainfall_balance import evaluate_rainfall_balance
from app.cacao_engine.modules.shade_balance import evaluate_shade_balance

def run_engine(inp: CacaoInputs) -> EngineReport:
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
''',

"app/cacao_engine/inputs.py": '''from typing import Optional
from pydantic import BaseModel, Field

class CacaoInputs(BaseModel):
    country: str
    rainfall_mm_month: float = Field(..., ge=0, le=600)
    humidity_pct: float = Field(..., ge=0, le=100)
    avg_temp_c: float = Field(..., ge=10, le=45)
    region: Optional[str] = None
    plantation_age_years: Optional[float] = Field(default=None, ge=0, le=100)
    shade_tree_density_pct: Optional[float] = Field(default=None, ge=0, le=100)
''',

"app/cacao_engine/outputs.py": '''from dataclasses import dataclass, field
from typing import List

@dataclass
class ModuleResult:
    module_name: str
    score: float
    risk_level: str
    reasons: List[str] = field(default_factory=list)

@dataclass
class EngineReport:
    global_score: float
    global_risk_level: str
    module_results: List[ModuleResult] = field(default_factory=list)
''',

"app/cacao_engine/__init__.py": "",

"app/__init__.py": "",
"app/db/__init__.py": "",
"app/auth/__init__.py": "",
"app/api/__init__.py": "",
"app/cacao_engine/rules/__init__.py": "",
"app/cacao_engine/modules/__init__.py": "",
"tests/__init__.py": "",
}

created = 0
skipped = 0
for path, content in files.items():
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  CREE   {path}")
        created += 1
    else:
        print(f"  OK     {path}")
        skipped += 1

print(f"\n{created} fichier(s) cree(s), {skipped} deja present(s).")
print("Lance maintenant : uvicorn main:app --reload")
