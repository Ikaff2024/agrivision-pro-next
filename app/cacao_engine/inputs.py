from typing import Optional
from pydantic import BaseModel, Field


class CacaoInputs(BaseModel):
    """
    Entrées du moteur CacaoEngine v1.
    Migré de dataclass vers Pydantic BaseModel pour :
    - Validation automatique des bornes (retourne HTTP 422 si invalide)
    - Compatibilité native avec FastAPI request body
    """
    country: str
    rainfall_mm_month: float = Field(..., ge=0.0, le=1000.0)
    humidity_pct: float      = Field(..., ge=0.0, le=100.0)
    avg_temp_c: float        = Field(..., ge=-10.0, le=60.0)

    region: Optional[str]               = None
    plantation_age_years: Optional[float] = Field(None, ge=0.0, le=100.0)
    shade_tree_density_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
