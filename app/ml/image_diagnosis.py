import httpx
import base64
import logging

logger = logging.getLogger("agrivision")

# ── URL du modèle déployé sur Hugging Face ────────────────────────────────────
HF_SPACE_URL  = "https://ikaff2026-agrivision-plant-disease.hf.space"
API_ENDPOINT  = f"{HF_SPACE_URL}/run/predict"

# Timeout généreux — le Space HF peut être froid au démarrage
REQUEST_TIMEOUT = 60.0


def analyze_leaf_image(image_path: str) -> dict:
    """
    Appelle le modèle EfficientNet-B0 déployé sur Hugging Face Space (Gradio 4.x).
    Retourne : disease, confidence, severity, recommendation.
    Fallback si le service est indisponible.
    """
    try:
        # Lire et encoder l'image en base64
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Déterminer le type MIME
        mime = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime = "image/png"
        elif image_path.lower().endswith(".webp"):
            mime = "image/webp"

        # ── Payload Gradio 4.x : base64 data URI directement dans data[] ──────
        payload = {
            "data": [f"data:{mime};base64,{image_b64}"]
        }

        response = httpx.post(
            API_ENDPOINT,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        result = response.json()

        # La réponse Gradio est dans data[0..3]
        data = result.get("data", [])
        if len(data) >= 4:
            disease        = data[0] or "Inconnue"
            severity_label = data[1] or "Modérée"
            confidence_str = data[2] or "0%"
            recommendation = data[3] or ""

            # Convertir sévérité FR → code interne
            severity_map = {
                "Saine":    "LOW",
                "Modérée":  "MEDIUM",
                "Critique": "HIGH",
            }
            severity = severity_map.get(severity_label, "MEDIUM")

            # Convertir confiance "88.8%" → float 0.888
            try:
                confidence = float(confidence_str.replace("%", "")) / 100
            except ValueError:
                confidence = 0.0

            logger.info("ML inference OK — %s (%.0f%%)", disease, confidence * 100)
            return {
                "disease":        disease,
                "confidence":     round(confidence, 4),
                "severity":       severity,
                "recommendation": recommendation,
                "source":         "huggingface"
            }

        logger.warning("ML inference — réponse inattendue : %s", data)

    except httpx.TimeoutException:
        logger.warning("ML inference timeout — fallback activé")
    except httpx.HTTPStatusError as e:
        logger.warning("ML inference HTTP error %s — fallback activé", e.response.status_code)
    except Exception as e:
        logger.warning("ML inference erreur inattendue : %s — fallback activé", e)

    # ── Fallback si HF Space indisponible ─────────────────────────────────────
    return {
        "disease":        "Analyse indisponible",
        "confidence":     0.0,
        "severity":       "MEDIUM",
        "recommendation": "Service d'analyse temporairement indisponible. Réessayez dans quelques instants.",
        "source":         "fallback"
    }
