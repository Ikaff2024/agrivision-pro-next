import httpx
import logging

logger = logging.getLogger("agrivision")

HF_SPACE_URL    = "https://ikaff2026-agrivision-plant-disease.hf.space"
API_ENDPOINT    = f"{HF_SPACE_URL}/api/predict"
REQUEST_TIMEOUT = 60.0


def analyze_leaf_image(image_path: str) -> dict:
    """
    Appelle le modèle EfficientNet-B0 via l'endpoint FastAPI direct du Space HF.
    POST /api/predict — bypass complet de la queue Gradio 5.x.
    """
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        mime = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime = "image/png"
        elif image_path.lower().endswith(".webp"):
            mime = "image/webp"

        response = httpx.post(
            API_ENDPOINT,
            files={"file": ("image.jpg", image_bytes, mime)},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise ValueError(f"Erreur Space HF : {result['error']}")

        disease        = result.get("disease", "Inconnue")
        severity_label = result.get("severity", "Modérée")
        confidence_str = result.get("confidence", "0%")
        recommendation = result.get("recommendation", "")

        severity_map = {"Saine": "LOW", "Modérée": "MEDIUM", "Critique": "HIGH"}
        severity = severity_map.get(severity_label, "MEDIUM")

        try:
            confidence = float(str(confidence_str).replace("%", "").strip()) / 100
        except (ValueError, AttributeError):
            confidence = 0.0

        logger.info("ML inference OK — %s (%.0f%%)", disease, confidence * 100)
        return {
            "disease":        disease,
            "confidence":     round(confidence, 4),
            "severity":       severity,
            "recommendation": recommendation,
            "source":         "huggingface",
        }

    # Un Space HF gratuit se met en veille et renvoie 503 / timeout au réveil
    # (démarrage à froid) : on le dit clairement pour inviter à réessayer.
    except httpx.TimeoutException:
        logger.warning("ML timeout (Space probablement en cours de démarrage)")
        return _fallback("Le modèle d'analyse démarre (Space en veille). Réessayez dans ~30 secondes.")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        logger.warning("ML HTTP %s — %s", code, e.response.text[:300])
        if code in (503, 502, 504):
            return _fallback("Le modèle d'analyse démarre (Space en veille). Réessayez dans ~30 secondes.")
        return _fallback("Service d'analyse d'image momentanément indisponible. Réessayez plus tard.")
    except Exception as e:  # noqa: BLE001
        logger.warning("ML erreur : %s", e)
        return _fallback("Service d'analyse d'image momentanément indisponible. Réessayez plus tard.")


def _fallback(reason: str) -> dict:
    return {
        "disease":        "Analyse indisponible",
        "confidence":     0.0,
        "severity":       "MEDIUM",
        "recommendation": reason,
        "source":         "fallback",
    }
