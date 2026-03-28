from typing import Optional
from pydantic import BaseModel, Field


class CacaoInputs(BaseModel):
    """
    Entrées du moteur agronomique CacaoEngine v1.
    Utilise Pydantic pour la validation automatique par FastAPI.
    """
    country: str
    rainfall_mm_month: float = Field(..., ge=0, le=600)
    humidity_pct: float = Field(..., ge=0, le=100)
    avg_temp_c: float = Field(..., ge=10, le=45)

    region: Optional[str] = None
    plantation_age_years: Optional[float] = Field(default=None, ge=0, le=100)
    shade_tree_density_pct: Optional[float] = Field(default=None, ge=0, le=100)
