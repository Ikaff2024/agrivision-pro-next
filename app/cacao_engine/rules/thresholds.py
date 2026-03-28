from enum import Enum

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
