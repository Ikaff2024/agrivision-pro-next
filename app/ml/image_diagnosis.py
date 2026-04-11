import logging

logger = logging.getLogger("agrivision")

HF_SPACE_URL = "https://ikaff2026-agrivision-plant-disease.hf.space"


def analyze_leaf_image(image_path: str) -> dict:
    """
    Appelle le modèle EfficientNet-B0 sur Hugging Face Space via gradio_client.
    Compatible Gradio 4.x et 5.x.
    Retourne : disease, confidence, severity, recommendation, source.
    """
    try:
        from gradio_client import Client, handle_file

        client = Client(HF_SPACE_URL, verbose=False)
        result = client.predict(
            image=handle_file(image_path),
            api_name="/predict"
        )

        # result est un tuple : (disease, severity_fr, confidence_str, recommendation)
        if isinstance(result, (list, tuple)) and len(result) >= 4:
            disease        = result[0] or "Inconnue"
            severity_label = result[1] or "Modérée"
            confidence_str = result[2] or "0%"
            recommendation = result[3] or ""
        else:
            raise ValueError(f"Format de réponse inattendu : {result}")

        # Sévérité FR -> code interne
        severity_map = {
            "Saine":    "LOW",
            "Modérée":  "MEDIUM",
            "Critique": "HIGH",
        }
        severity = severity_map.get(severity_label, "MEDIUM")

        # Confiance "88.8%" -> float 0.888
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

    except ImportError:
        logger.error("gradio_client non installe — ajouter dans requirements.txt")
    except Exception as e:
        logger.warning("ML inference erreur : %s — fallback active", e)

    return {
        "disease":        "Analyse indisponible",
        "confidence":     0.0,
        "severity":       "MEDIUM",
        "recommendation": "Service d'analyse temporairement indisponible. Reessayez dans quelques instants.",
        "source":         "fallback",
    }
