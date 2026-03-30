"""
ndvi_service.py — Service NDVI via Copernicus Data Space Ecosystem (CDSE).

API gratuite : https://dataspace.copernicus.eu
Sentinel-2 Level-2A — Résolution 10m — Revisite ~5 jours sur l'Afrique de l'Ouest.

Variables d'environnement requises (Railway) :
    SENTINEL_CLIENT_ID      → Client ID OAuth2 CDSE
    SENTINEL_CLIENT_SECRET  → Client Secret OAuth2 CDSE

Inscription gratuite : https://identity.dataspace.copernicus.eu/auth/realms/CDSE/
Fallback automatique si les credentials ne sont pas configurés.
"""
import os
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Union, Optional

logger = logging.getLogger("agrivision.ndvi")

# ── Constantes Copernicus Data Space ─────────────────────────────────────────
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# Cache token en mémoire (évite de re-fetcher à chaque appel)
_token_cache: Dict[str, Union[str, float]] = {"token": None, "expires_at": 0}


def _get_access_token() -> Optional[str]:
    """Obtient un token OAuth2 CDSE avec cache en mémoire."""
    import time
    import urllib.request
    import urllib.parse
    import json

    client_id     = os.getenv("SENTINEL_CLIENT_ID")
    client_secret = os.getenv("SENTINEL_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    # Token encore valide ?
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

        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 600)

        _token_cache["token"] = token
        _token_cache["expires_at"] = time.time() + expires_in
        logger.info("Token CDSE obtenu, expire dans %ss", expires_in)
        return token

    except Exception as e:
        logger.warning("Échec obtention token CDSE : %s", e)
        return None


def _fetch_ndvi_cdse(latitude: float, longitude: float, token: str) -> Optional[float]:
    """
    Appelle l'API Sentinel Hub Process pour calculer le NDVI moyen
    sur une zone de 500m autour des coordonnées.
    Retourne le NDVI moyen ou None en cas d'erreur.
    """
    import urllib.request
    import json

    # Bounding box ~500m autour du point (approximation)
    delta = 0.005  # ~500m en degrés
    bbox = [
        longitude - delta,
        latitude  - delta,
        longitude + delta,
        latitude  + delta,
    ]

    # Date range : 30 derniers jours pour maximiser les chances d'avoir une image
    date_to   = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Evalscript Sentinel-2 L2A : calcule NDVI pixel par pixel, retourne la moyenne
    evalscript = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL"], units: "DN" }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  // Exclure nuages (SCL 8,9,10) et eau (SCL 6)
  if ([6,8,9,10].includes(sample.SCL)) return [-9999];
  var ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 0.0001);
  return [ndvi];
}
"""

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {"from": date_from, "to": date_to},
                    "maxCloudCoverage": 30,
                    "mosaickingOrder": "leastCC"  # image la moins nuageuse
                }
            }]
        },
        "output": {
            "width": 10, "height": 10,
            "responses": [{"identifier": "default", "format": {"type": "application/json"}}]
        },
        "evalscript": evalscript
    }

    try:
        import json as json_mod
        data = json_mod.dumps(payload).encode()
        req = urllib.request.Request(CDSE_PROCESS_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json_mod.loads(resp.read())

        # Extraire les pixels valides (exclure -9999)
        pixels = []
        if isinstance(result, list):
            for row in result:
                if isinstance(row, list):
                    pixels.extend([v for v in row if v != -9999])
                elif isinstance(row, (int, float)) and row != -9999:
                    pixels.append(row)

        if not pixels:
            logger.warning("Aucun pixel valide retourné (couverture nuageuse ?).")
            return None

        ndvi_mean = sum(pixels) / len(pixels)
        ndvi_clamped = max(-1.0, min(1.0, round(ndvi_mean, 3)))
        logger.info("NDVI Sentinel-2 calculé: %.3f (lat=%.4f, lon=%.4f)",
                    ndvi_clamped, latitude, longitude)
        return ndvi_clamped

    except Exception as e:
        logger.warning("Erreur appel API Sentinel Hub : %s", e)
        return None


def _ndvi_stub(latitude: float, longitude: float) -> float:
    """
    Fallback déterministe basé sur les coordonnées.
    Retourne toujours la même valeur pour les mêmes coordonnées (reproductible).
    """
    seed = int(abs(latitude * 1000 + longitude * 100)) % 1000
    random.seed(seed)
    return round(random.uniform(0.35, 0.85), 2)


def _status_from_ndvi(ndvi: float) -> dict:
    """Dérive le statut, l'interprétation et la recommandation depuis le NDVI."""
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
            "recommendation": "Végétation en état critique. Intervention urgente requise — possible maladie ou sécheresse sévère.",
        }


def get_ndvi(latitude: float, longitude: float) -> Dict[str, Union[float, str]]:
    """
    Point d'entrée principal du service NDVI.

    Comportement :
    1. Si SENTINEL_CLIENT_ID + SENTINEL_CLIENT_SECRET sont configurés
       → appel réel à l'API Copernicus Data Space (Sentinel-2 L2A)
    2. Sinon → fallback stub déterministe (même valeur pour mêmes coordonnées)
    """
    ndvi: Optional[float] = None
    source = "sentinel-2"

    # Tentative API réelle
    token = _get_access_token()
    if token:
        ndvi = _fetch_ndvi_cdse(latitude, longitude, token)

    # Fallback si pas de credentials ou erreur API
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
