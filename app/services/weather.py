"""
Météo agricole automatique via Open-Meteo (gratuit, sans clé), CÔTÉ SERVEUR.

Comble un manque réel : les champs météo du diagnostic étaient saisis à la main.
Fournit température, humidité et pluviométrie (cumul 30 j) pour des coordonnées,
afin de pré-remplir le diagnostic. Cache mémoire (par zone), dégradation
gracieuse (None si indisponible), aucune clé requise.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("agrivision")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE: dict = {}          # {(lat2, lon2): (ts, data)}
_TTL = 3600                # 1 h


async def get_weather(latitude: float, longitude: float) -> Optional[dict]:
    """Météo agricole pour un point. Best-effort : None en cas d'échec.

    Renvoie : temperature_c, humidity_pct, rainfall_mm_month (cumul 30 j),
    source, latitude, longitude.
    """
    if latitude is None or longitude is None:
        return None
    key = (round(float(latitude), 2), round(float(longitude), 2))
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation",
        "daily": "precipitation_sum",
        "past_days": 30,
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            d = r.json()
        current = d.get("current") or {}
        daily = (d.get("daily") or {}).get("precipitation_sum") or []
        rain_30d = round(sum(x for x in daily if isinstance(x, (int, float))), 1)
        temp = current.get("temperature_2m")
        hum = current.get("relative_humidity_2m")
        if temp is None and hum is None and not daily:
            return None
        data = {
            "temperature_c": temp,
            "humidity_pct": hum,
            "rainfall_mm_month": rain_30d,
            "source": "open-meteo",
            "latitude": latitude,
            "longitude": longitude,
        }
        _CACHE[key] = (now, data)
        return data
    except Exception as e:  # noqa: BLE001
        logger.warning("Météo Open-Meteo indisponible (%s,%s) : %s", latitude, longitude, e)
        return None
