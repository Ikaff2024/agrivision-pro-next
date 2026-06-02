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

import json
import logging
import math
import os
import random
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from app.satellite.ndvi_service import (
    CDSE_STATS_URL,
    _get_access_token,
    _ndvi_stub,
    _status_from_ndvi,
    get_ndvi,
)

logger = logging.getLogger("agrivision.satellite")

# Evalscripts Sentinel-2 par indice (Statistical API).
#   NDVI = (B08 - B04) / (B08 + B04)   — vigueur de la végétation
#   NDMI = (B08 - B11) / (B08 + B11)   — teneur en eau du couvert
_EVALSCRIPTS = {
    "ndvi": ("B04", "B08"),
    "ndmi": ("B11", "B08"),
}


def _evalscript(index: str) -> str:
    b_low, b_high = _EVALSCRIPTS[index]
    return f"""
//VERSION=3
function setup() {{
  return {{
    input: [{{ bands: ["{b_low}", "{b_high}"], units: "REFLECTANCE" }}],
    output: [
      {{ id: "index",    bands: 1, sampleType: "FLOAT32" }},
      {{ id: "dataMask", bands: 1, sampleType: "UINT8"   }}
    ]
  }};
}}
function evaluatePixel(s) {{
  var v = (s.{b_high} - s.{b_low}) / (s.{b_high} + s.{b_low} + 0.0001);
  var mask = (s.{b_high} + s.{b_low} > 0.01) ? 1 : 0;
  return {{ index: [v], dataMask: [mask] }};
}}
"""


def _fetch_index_series(latitude, longitude, index, token, months, interval="P1M"):
    """
    Récupère une série temporelle d'un indice via l'API Statistical de
    Copernicus (Sentinel-2 L2A). Retourne une liste [{period, value}] ou None.
    """
    delta = 0.005  # ~500 m
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=31 * months)
    payload = {
        "input": {
            "bounds": {
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                "bbox": [longitude - delta, latitude - delta, longitude + delta, latitude + delta],
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"maxCloudCoverage": 70, "mosaickingOrder": "leastCC"},
            }],
        },
        "aggregation": {
            "timeRange": {
                "from": date_from.strftime("%Y-%m-%dT00:00:00Z"),
                "to": date_to.strftime("%Y-%m-%dT00:00:00Z"),
            },
            "aggregationInterval": {"of": interval},
            "evalscript": _evalscript(index),
            "resx": 0.0001,
            "resy": 0.0001,
        },
        "calculations": {"default": {"statistics": {"default": {}}}},
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(CDSE_STATS_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        logger.warning("CDSE série %s échouée : %s", index, exc)
        return None

    series: list[dict] = []
    for itv in result.get("data", []):
        mean = (
            itv.get("outputs", {}).get("index", {}).get("bands", {})
            .get("B0", {}).get("stats", {}).get("mean")
        )
        if mean is None or mean != mean:  # None / NaN
            continue
        period = (itv.get("interval", {}).get("from") or "")[:7]  # YYYY-MM
        series.append({"period": period, "value": round(float(mean), 3)})
    return series or None


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


def _interpret_ndvi(ndvi: float) -> dict:
    """
    Interpretation NDVI ALIGNEE sur app/api/routes._interpret_ndvi (garde-fou
    anti-detracteur), pour une coherence stricte entre /satellite/ndvi et
    /satellite/indices. Seuils cacaoculture : <=0.35 indetermine (sol nu/eau,
    confiance faible, pas de reco), 0.35-0.50 stressee, 0.50-0.70 moderee, >0.70 saine.
    """
    if ndvi <= 0.35:
        return {
            "ndvi_status": "INDETERMINE",
            "ndvi_interpretation": "Indéterminée",
            "confidence": "low",
            "recommendation": (
                "Indice de végétation très faible (NDVI = "
                f"{ndvi:.2f}) : sol nu, zone urbaine/eau ou couvert très dégradé. "
                "Vérifiez que les coordonnées correspondent à la plantation. "
                "Aucune recommandation agronomique automatique."
            ),
        }
    if ndvi <= 0.50:
        return {"ndvi_status": "STRESSED", "ndvi_interpretation": "Stressée", "confidence": "high",
                "recommendation": "Stress végétatif : vérifier irrigation/fertilisation, inspection conseillée."}
    if ndvi <= 0.70:
        return {"ndvi_status": "MODERATE", "ndvi_interpretation": "Modérée", "confidence": "high",
                "recommendation": "Végétation moyenne à dense : poursuivre l'entretien habituel."}
    return {"ndvi_status": "HEALTHY", "ndvi_interpretation": "Saine", "confidence": "high",
            "recommendation": "Couvert dense et en bonne santé."}


def get_indices(latitude: float, longitude: float) -> dict:
    """NDVI + NDMI + statuts. Source réelle si token, sinon simulation."""
    ndvi_result = get_ndvi(latitude, longitude)
    ndvi = ndvi_result["ndvi"]
    source = ndvi_result.get("source", "simulation")

    # NDMI réel via Copernicus si identifiants présents, sinon simulation.
    ndmi = None
    token = _get_access_token()
    if token:
        recent = _fetch_index_series(latitude, longitude, "ndmi", token, months=2, interval="P1M")
        if recent:
            ndmi = recent[-1]["value"]
    if ndmi is None:
        ndmi = _ndmi_stub(latitude, longitude)

    interp = _interpret_ndvi(ndvi)
    return {
        "ndvi": ndvi,
        "ndvi_status": interp["ndvi_status"],
        "ndvi_interpretation": interp["ndvi_interpretation"],
        "ndvi_confidence": interp["confidence"],
        "ndmi": ndmi,
        **_ndmi_status(ndmi),
        "recommendation": interp["recommendation"],
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

    # Série réelle via Copernicus si identifiants présents, sinon simulation.
    token = _get_access_token()
    if token:
        real = _fetch_index_series(latitude, longitude, index, token, months=months, interval="P1M")
        if real:
            return {
                "index": index,
                "months": months,
                "series": real,
                "source": "sentinel-2",
                "provider": "copernicus-data-space",
            }

    return {
        "index": index,
        "months": months,
        "series": _timeseries_stub(latitude, longitude, index, months),
        "source": "simulation",
        "provider": "copernicus-data-space",
    }


# ── Déforestation ────────────────────────────────────────────────────────────────

_GFW_HOST = "data-api.globalforestwatch.org"
_GFW_DATASET = "gfw_integrated_alerts"  # GLAD-L + GLAD-S2 + RADD combinés
_EUDR_CUTOFF = "2020-12-31"             # déforestation interdite après cette date (EUDR)
_gfw_version_cache: dict = {"version": None, "fetched_at": 0}


def _gfw_request(method: str, path: str, key: str, body: Optional[bytes] = None, timeout: int = 60):
    """
    Requête HTTPS vers la GFW Data API via http.client.

    ⚠️ L'en-tête doit être EXACTEMENT `x-api-key` en minuscules : la GFW Data API
    est sensible à la casse et rejette `X-Api-Key` (urllib capitalise, d'où ce
    client bas niveau qui préserve la casse).
    """
    import http.client
    conn = http.client.HTTPSConnection(_GFW_HOST, timeout=timeout)
    headers = {"x-api-key": key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            logger.warning("GFW %s %s -> HTTP %d : %s", method, path, resp.status, raw[:200])
            return None
        return json.loads(raw)
    finally:
        conn.close()


def _gfw_latest_version(key: str) -> Optional[str]:
    """Dernière version datée du dataset d'alertes (mise en cache 24 h)."""
    import time
    if _gfw_version_cache["version"] and time.time() < _gfw_version_cache["fetched_at"] + 86400:
        return _gfw_version_cache["version"]
    try:
        data = _gfw_request("GET", f"/dataset/{_GFW_DATASET}", key, timeout=15)
        versions = (data or {}).get("data", {}).get("versions", [])
        if not versions:
            return None
        _gfw_version_cache["version"] = versions[-1]
        _gfw_version_cache["fetched_at"] = time.time()
        return versions[-1]
    except Exception as exc:  # noqa: BLE001
        logger.warning("GFW : récupération de version échouée : %s", exc)
        return None


def _point_buffer_polygon(latitude: float, longitude: float, d: float = 0.01) -> dict:
    """Polygone carré (~1 km par défaut) centré sur un point — fallback sans parcelle."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [longitude - d, latitude - d], [longitude + d, latitude - d],
            [longitude + d, latitude + d], [longitude - d, latitude + d],
            [longitude - d, latitude - d],
        ]],
    }


def _fetch_deforestation(geometry: dict, key: str) -> Optional[int]:
    """Compte les alertes de déforestation post-2020 sur une géométrie. None si erreur."""
    version = _gfw_latest_version(key)
    if not version:
        return None
    body = json.dumps({
        "sql": f"SELECT count(*) FROM results WHERE {_GFW_DATASET}__date >= '{_EUDR_CUTOFF}'",
        "geometry": geometry,
    }).encode("utf-8")
    try:
        data = _gfw_request(
            "POST", f"/dataset/{_GFW_DATASET}/{version}/query/json", key, body=body, timeout=90
        )
        if data is None:
            return None
        rows = data.get("data", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("GFW : requête alertes échouée : %s", exc)
        return None
    return int(rows[0].get("count", 0)) if rows else 0


def _deforestation_result(count: int, scope: str) -> dict:
    zone = "la parcelle" if scope == "parcel" else "une zone d'environ 1 km autour du point"
    return {
        "loss_detected": count > 0,
        "alerts_count": count,
        "since": _EUDR_CUTOFF,
        "scope": scope,  # 'parcel' (polygone exact) | 'buffer_1km' (point)
        "dataset": "gfw_integrated_alerts (GLAD-L / GLAD-S2 / RADD)",
        "provider": "global-forest-watch",
        "source": "global-forest-watch",
        "note": (
            f"{count} alerte(s) de déforestation depuis {_EUDR_CUTOFF} sur {zone}."
            if count else f"Aucune alerte de déforestation depuis {_EUDR_CUTOFF} sur {zone}."
        ),
    }


def _deforestation_simulation(scope: str) -> dict:
    return {
        "loss_detected": False,
        "alerts_count": 0,
        "since": _EUDR_CUTOFF,
        "scope": scope,
        "dataset": "gfw_integrated_alerts (GLAD-L / GLAD-S2 / RADD)",
        "provider": "global-forest-watch",
        "source": "simulation",
        "note": "Définissez GFW_API_KEY pour activer les alertes réelles de déforestation.",
    }


def get_deforestation_signal(latitude: float, longitude: float) -> dict:
    """
    Signal de déforestation pour un POINT (zone ~1 km autour). Réel via GFW si clé
    présente, sinon simulation (jamais d'alarme erronée). Erreur réseau => simulation.
    """
    key = os.getenv("GFW_API_KEY")
    if key:
        count = _fetch_deforestation(_point_buffer_polygon(latitude, longitude), key)
        if count is not None:
            return _deforestation_result(count, scope="buffer_1km")
    return _deforestation_simulation(scope="buffer_1km")


def get_deforestation_for_geometry(geometry: dict) -> dict:
    """
    Signal de déforestation sur le POLYGONE EXACT d'une parcelle (GeoJSON Polygon).
    Plus precis pour l'EUDR que le buffer de point. Fallback simulation si pas de clé.
    """
    key = os.getenv("GFW_API_KEY")
    if key and geometry:
        count = _fetch_deforestation(geometry, key)
        if count is not None:
            return _deforestation_result(count, scope="parcel")
    return _deforestation_simulation(scope="parcel")


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
