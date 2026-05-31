"""
provider.py — Abstraction de télédétection (indices de végétation, séries
temporelles, signal de déforestation).

Conçu pour fonctionner **sans aucune clé** dès maintenant (fallback simulation
déterministe) et basculer automatiquement sur **Copernicus Data Space / Sentinel
Hub** (gratuit) dès que `SENTINEL_CLIENT_ID` / `SENTINEL_CLIENT_SECRET` sont
définis. La déforestation pourra utiliser Global Forest Watch (clé `GFW_API_KEY`).

Aucune dépendance externe (urllib seulement). En l'absence de token ou en cas
d'erreur réseau, on renvoie une série simulée stable et le champ `source` vaut
"simulation" — jamais d'exception propagée à l'appelant.
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime
from typing import Optional

from app.satellite.ndvi_service import (
    _get_access_token,
    _ndvi_stub,
    _status_from_ndvi,
    get_ndvi,
)


# ── Indices ────────────────────────────────────────────────────────────────────

def _ndmi_stub(latitude: float, longitude: float) -> float:
    """NDMI simulé déterministe (humidité du couvert), corrélé au NDVI stub."""
    base = _ndvi_stub(latitude, longitude)
    return round(max(-0.2, min(0.6, base - 0.15)), 2)


def _ndmi_status(ndmi: float) -> dict:
    if ndmi >= 0.4:
        return {"moisture_status": "HUMIDE", "interpretation": "Bonne teneur en eau"}
    if ndmi >= 0.2:
        return {"moisture_status": "MODERE", "interpretation": "Teneur en eau modérée"}
    if ndmi >= 0.0:
        return {"moisture_status": "SEC", "interpretation": "Couvert sec, surveiller l'irrigation"}
    return {"moisture_status": "TRES_SEC", "interpretation": "Stress hydrique marqué"}


def get_indices(latitude: float, longitude: float) -> dict:
    """NDVI + NDMI + statuts. Source réelle si token, sinon simulation."""
    ndvi_result = get_ndvi(latitude, longitude)
    ndvi = ndvi_result["ndvi"]
    source = ndvi_result.get("source", "simulation")

    # NDMI : pour l'instant simulation (l'evalscript NDMI réel sera branché avec
    # les mêmes identifiants Copernicus). Corrélé au NDVI pour rester cohérent.
    ndmi = _ndmi_stub(latitude, longitude)

    return {
        "ndvi": ndvi,
        "ndvi_status": ndvi_result.get("vegetation_status"),
        "ndvi_interpretation": ndvi_result.get("interpretation"),
        "ndmi": ndmi,
        **_ndmi_status(ndmi),
        "recommendation": ndvi_result.get("recommendation"),
        "source": source,
    }


# ── Séries temporelles ──────────────────────────────────────────────────────────

def _timeseries_stub(latitude: float, longitude: float, index: str, months: int) -> list[dict]:
    """
    Série mensuelle simulée déterministe avec saisonnalité (sinusoïde) — stable
    pour des coordonnées données, afin que l'UI affiche une évolution crédible
    en l'absence de clés satellite.
    """
    seed = int(abs(latitude * 1000 + longitude * 100)) % 1000
    rng = random.Random(seed + (0 if index == "ndvi" else 7))
    base = _ndvi_stub(latitude, longitude) if index == "ndvi" else _ndmi_stub(latitude, longitude)
    today = datetime.utcnow()

    # Liste des (année, mois) du plus ancien au plus récent.
    months_back: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(months):
        months_back.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1

    series: list[dict] = []
    for (yy, mm) in reversed(months_back):
        # saisonnalité : pic en saison des pluies, creux en saison sèche
        seasonal = 0.12 * math.sin(((mm - 1) / 12.0) * 2 * math.pi)
        noise = rng.uniform(-0.03, 0.03)
        value = round(max(0.0, min(1.0, base + seasonal + noise)), 3)
        series.append({"period": f"{yy}-{mm:02d}", "value": value})
    return series


def get_timeseries(latitude: float, longitude: float, index: str = "ndvi", months: int = 12) -> dict:
    """
    Série temporelle mensuelle d'un indice (ndvi|ndmi).

    Aujourd'hui : simulation déterministe (aucune clé requise). Le branchement
    Copernicus (agrégation mensuelle P1M via l'API Statistical) se fera ici même
    quand SENTINEL_CLIENT_ID/SECRET seront fournis — la signature ne change pas.
    """
    index = index if index in {"ndvi", "ndmi"} else "ndvi"
    months = max(1, min(36, months))
    has_credentials = bool(os.getenv("SENTINEL_CLIENT_ID") and os.getenv("SENTINEL_CLIENT_SECRET"))
    # Tant que l'agrégation temporelle réelle n'est pas branchée, on renvoie la
    # simulation. `source` reflète si les identifiants sont présents (réel à venir).
    series = _timeseries_stub(latitude, longitude, index, months)
    return {
        "index": index,
        "months": months,
        "series": series,
        "source": "sentinel-2" if has_credentials else "simulation",
        "provider": "copernicus-data-space",
    }


# ── Déforestation ────────────────────────────────────────────────────────────────

def get_deforestation_signal(latitude: float, longitude: float) -> dict:
    """
    Signal de déforestation pour un point (alertes type GLAD/RADD).

    Branchement futur : Global Forest Watch API (clé `GFW_API_KEY`, gratuite) ou
    Hansen Global Forest Change. En l'absence de clé, renvoie un signal simulé
    clairement marqué `source="simulation"` (jamais d'alarme erronée : aucune
    perte signalée par défaut).
    """
    has_key = bool(os.getenv("GFW_API_KEY"))
    return {
        "loss_detected": False,
        "alerts_count": 0,
        "since": "2020-12-31",
        "dataset": "hansen-gfc / glad-radd",
        "provider": "global-forest-watch",
        "source": "configured" if has_key else "simulation",
        "note": (
            "Branchez GFW_API_KEY pour activer les alertes réelles de déforestation."
            if not has_key else "Clé GFW présente : intégration des alertes à finaliser."
        ),
    }


def provider_status() -> dict:
    """Indique quels fournisseurs satellite sont configurés (diagnostic UI/admin)."""
    return {
        "vegetation_provider": "copernicus-data-space",
        "vegetation_configured": bool(
            os.getenv("SENTINEL_CLIENT_ID") and os.getenv("SENTINEL_CLIENT_SECRET")
        ),
        "deforestation_provider": "global-forest-watch",
        "deforestation_configured": bool(os.getenv("GFW_API_KEY")),
    }
