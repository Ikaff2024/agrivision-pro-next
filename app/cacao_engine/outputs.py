from dataclasses import dataclass, field
from typing import List


@dataclass
class ModuleResult:
    """Résultat d'un module d'évaluation du moteur."""
    module_name: str
    score: float
    risk_level: str
    reasons: List[str] = field(default_factory=list)


@dataclass
class EngineReport:
    """Rapport complet d'exécution du moteur CacaoEngine."""
    global_score: float
    global_risk_level: str
    module_results: List[ModuleResult] = field(default_factory=list)
