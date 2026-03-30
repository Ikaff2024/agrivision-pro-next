"""
ndvi_service.py — Service NDVI via Copernicus Data Space / Sentinel Hub Statistical API.

L'API Statistical retourne directement des statistiques JSON (mean, min, max, stdev)
sans nécessiter de parsing de fichiers raster binaires.

Variables d'environnement requises :
    SENTINEL_CLIENT_ID
    SENTINEL_CLIENT_SECRET
"""
import os
import json
import time
import random
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Union, Optional

logger = logging.getLogger("agrivision.ndvi")

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
CDSE_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

_token_cache: Dict = {"token": None, "expires_at": 0}


def _get_access_token() -> Optional[str]:
    client_id     = os.getenv("SENTINEL_CLIENT_ID")
    client_secret = os.getenv("SENTINEL_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    try:
        data = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(CDSE_TOKEN_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        token = payload["access_token"]
        _token_cache["token"] = token
        _token_cache["expires_at"] = time.time() + payload.get("expires_in", 600)
        logger.info("Token CDSE obtenu, expire dans %ss", payload.get("expires_in", 600))
        return token
    except Exception as e:
        logger.warning("Échec obtention token CDSE : %s", e)
        return None


def _fetch_ndvi_statistical(
    latitude: float, longitude: float, token: str
) -> Optional[float]:
    """
    Utilise l'API Statistical de Sentinel Hub pour obtenir le NDVI moyen.
    Retourne un JSON avec mean/min/max — pas de parsing raster.
    """
    delta     = 0.005   # ~500m
    date_to   = datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z")
    date_from = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%dT00:00:00Z")

    evalscript = """
//VERSION=3
function setup() {
  return {
    input: [
      { bands: ["B04", "B08"], units: "REFLECTANCE" },
      { bands: ["SCL"],        units: "DN" }
    ],
    output: [
      { id: "ndvi",     bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1, sampleType: "UINT8"   }
    ]
  };
}
function evaluatePixel(samples) {
  // Exclure nuages (SCL 8,9,10) et eau (SCL 6)
  var valid = [6,8,9,10].includes(samples.SCL) ? 0 : 1;
  var ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04 + 0.0001);
  return { ndvi: [ndvi], dataMask: [valid] };
}
"""

    payload = {
        "input": {
            "bounds": {
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                },
                "bbox": [
                    longitude - delta,
                    latitude  - delta,
                    longitude + delta,
                    latitude  + delta,
                ]
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": date_from,
                            "to":   date_to,
                        },
                        "maxCloudCoverage": 70,
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "aggregation": {
            "timeRange": {
                "from": date_from,
                "to":   date_to,
            },
            "aggregationInterval": {
                "of": "P30D"   # agrégation sur 30 jours
            },
            "evalscript": evalscript,
            "resx": 0.0001,    # ~10m résolution
            "resy": 0.0001,
        },
        "calculations": {
            "default": {
                "histograms": {"default": {"nBins": 5, "lowEdge": -1.0, "highEdge": 1.0}},
                "statistics": {"default": {"percentiles": {"k": [25, 50, 75]}}}
            }
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(CDSE_STATS_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type",  "application/json")
        req.add_header("Accept",        "application/json")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        # Extraire la valeur NDVI moyenne depuis la réponse Statistical
        # Structure: data[0].outputs.ndvi.bands.B0.stats.mean
        intervals = result.get("data", [])
        if not intervals:
            logger.warning("Sentinel Statistical: aucun intervalle retourné.")
            return None

        # Prendre le dernier intervalle (le plus récent)
        last = intervals[-1]
        ndvi_band = (
            last.get("outputs", {})
                .get("ndvi", {})
                .get("bands", {})
                .get("B0", {})
                .get("stats", {})
        )

        mean = ndvi_band.get("mean")
        if mean is None or mean != mean:   # None ou NaN
            logger.warning("Sentinel Statistical: mean NDVI non disponible.")
            return None

        ndvi = round(float(mean), 3)
        logger.info(
            "NDVI Sentinel-2 réel (Statistical): %.3f (lat=%.4f, lon=%.4f)",
            ndvi, latitude, longitude,
        )
        return ndvi

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.warning("HTTP %d Sentinel Statistical : %s", e.code, body[:300])
        return None
    except Exception as e:
        logger.warning("Erreur Sentinel Statistical : %s", e)
        return None


def _ndvi_stub(latitude: float, longitude: float) -> float:
    """Fallback déterministe — même valeur pour mêmes coordonnées."""
    seed = int(abs(latitude * 1000 + longitude * 100)) % 1000
    random.seed(seed)
    return round(random.uniform(0.35, 0.85), 2)


def _status_from_ndvi(ndvi: float) -> dict:
    if ndvi >= 0.7:
        return {
            "vegetation_status": "HEALTHY",
            "interpretation": "Excellente",
            "recommendation": (
                "La végétation est dense et en bonne santé. "
                "Continuez votre programme d'entretien habituel."
            ),
        }
    elif ndvi >= 0.5:
        return {
            "vegetation_status": "MODERATE",
            "interpretation": "Modérée",
            "recommendation": (
                "La végétation montre des signes de stress modéré. "
                "Vérifiez l'irrigation et la fertilisation."
            ),
        }
    elif ndvi >= 0.3:
        return {
            "vegetation_status": "STRESSED",
            "interpretation": "Stressée",
            "recommendation": (
                "Stress végétatif détecté. "
                "Inspection terrain recommandée dans les 7 jours."
            ),
        }
    else:
        return {
            "vegetation_status": "CRITICAL",
            "interpretation": "Critique",
            "recommendation": (
                "Végétation en état critique. "
                "Intervention urgente requise — possible maladie ou sécheresse sévère."
            ),
        }


def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    ndvi: Optional[float] = None
    source = "sentinel-2"

    token = _get_access_token()
    if token:
        ndvi = _fetch_ndvi_statistical(latitude, longitude, token)

    if ndvi is None:
        ndvi = _ndvi_stub(latitude, longitude)
        source = "simulation"
        if not os.getenv("SENTINEL_CLIENT_ID"):
            logger.info("NDVI simulation (SENTINEL_CLIENT_ID non configuré).")
        else:
            logger.warning("NDVI simulation (échec API Sentinel Statistical).")

    result = _status_from_ndvi(ndvi)
    result["ndvi"]   = ndvi
    result["source"] = source
    return result
