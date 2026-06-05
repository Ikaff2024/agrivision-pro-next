"""Météo agricole automatique (Open-Meteo) — pré-remplissage du diagnostic.

GET /weather/current?latitude=&longitude= : température, humidité, pluviométrie
(cumul 30 j). Côté serveur, gratuit, sans clé. 503 si momentanément indisponible.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.auth_service import get_current_user
from app.db.models import User
from app.services.weather import get_weather

router = APIRouter(prefix="/weather", tags=["Météo agricole"])


@router.get("/current")
async def weather_current(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    current_user: User = Depends(get_current_user),
):
    data = await get_weather(latitude, longitude)
    if not data:
        raise HTTPException(status_code=503, detail="Météo momentanément indisponible. Réessayez plus tard.")
    return data
