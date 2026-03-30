"""
ndvi_service.py — Service NDVI via Copernicus Data Space Ecosystem (CDSE).

API gratuite : https://dataspace.copernicus.eu
Sentinel-2 Level-2A — Résolution 10m — Revisite ~5 jours sur l'Afrique de l'Ouest.

Variables d'environnement requises (Railway) :
    SENTINEL_CLIENT_ID      → Client ID OAuth2 CDSE
    SENTINEL_CLIENT_SECRET  → Client Secret OAuth2 CDSE
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

CDSE_TOKEN_URL   = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

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


def _fetch_ndvi_cdse(latitude: float, longitude: float, token: str) -> Optional[float]:
    """
    Calcule le NDVI moyen via Sentinel Hub Process API (format corrigé).
    Utilise une bounding box de ~1km autour du point.
    """
    delta = 0.005  # ~500m en degrés latitude/longitude

    date_to   = datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z")
    date_from = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")

    evalscript = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08"],
      units: "REFLECTANCE"
    }],
    output: {
      bands: 1,
      sampleType: "FLOAT32"
    }
  };
}
function evaluatePixel(sample) {
  var ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 0.0001);
  return [ndvi];
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
                            "to":   date_to
                        },
                        "maxCloudCoverage": 50,
                        "mosaickingOrder": "leastCC"
                    }
                }
            ]
        },
        "output": {
            "width":  5,
            "height": 5,
            "responses": [
                {
                    "identifier": "default",
                    "format": {
                        "type": "image/tiff"
                    }
                }
            ]
        },
        "evalscript": evalscript
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(CDSE_PROCESS_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type",  "application/json")
        req.add_header("Accept",        "application/octet-stream")

        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()

        # Parser le GeoTIFF minimal : extraire les valeurs float32
        # Les pixels NDVI sont encodés en float32 dans le TIFF
        import struct
        floats = []
        # Chercher les float32 valides dans le binaire (entre -1 et 1)
        for i in range(0, len(raw) - 4, 4):
            try:
                val = struct.unpack_from('<f', raw, i)[0]
                if -1.0 <= val <= 1.0 and val == val:  # exclure NaN
                    floats.append(val)
            except Exception:
                continue

        if not floats:
            logger.warning("Aucune valeur NDVI extraite du TIFF.")
            return None

        # Prendre la médiane pour éviter les outliers
        floats.sort()
        median = floats[len(floats) // 2]
        ndvi = round(median, 3)
        logger.info("NDVI Sentinel-2 réel: %.3f (lat=%.4f, lon=%.4f, n=%d pixels)",
                    ndvi, latitude, longitude, len(floats))
        return ndvi

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.warning("HTTP %d depuis Sentinel Hub : %s", e.code, body[:300])
        return None
    except Exception as e:
        logger.warning("Erreur appel API Sentinel Hub : %s", e)
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
            "recommendation": "La végétation est dense et en bonne santé. Continuez votre programme d'entretien habituel.",
        }
    elif ndvi >= 0.5:
        return {
            "vegetation_status": "MODERATE",
            "interpretation": "Modérée",
            "recommendation": "La végétation montre des signes de stress modéré. Vérifiez l'irrigation et la fertilisation.",
        }
    elif ndvi >= 0.3:
        return {
            "vegetation_status": "STRESSED",
            "interpretation": "Stressée",
            "recommendation": "Stress végétatif détecté. Inspection terrain recommandée dans les 7 jours.",
        }
    else:
        return {
            "vegetation_status": "CRITICAL",
            "interpretation": "Critique",
            "recommendation": "Végétation en état critique. Intervention urgente requise.",
        }


def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    ndvi: Optional[float] = None
    source = "sentinel-2"

    token = _get_access_token()
    if token:
        ndvi = _fetch_ndvi_cdse(latitude, longitude, token)

    if ndvi is None:
        ndvi = _ndvi_stub(latitude, longitude)
        source = "simulation"
        if not os.getenv("SENTINEL_CLIENT_ID"):
            logger.info("NDVI en mode simulation (SENTINEL_CLIENT_ID non configuré).")
        else:
            logger.warning("NDVI en mode simulation (échec API Sentinel).")

    result = _status_from_ndvi(ndvi)
    result["ndvi"] = ndvi
    result["source"] = source
    return result
