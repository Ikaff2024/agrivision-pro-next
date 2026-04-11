import httpx
import logging

logger = logging.getLogger("agrivision")

HF_SPACE_URL     = "https://ikaff2026-agrivision-plant-disease.hf.space"
UPLOAD_ENDPOINT  = f"{HF_SPACE_URL}/gradio_api/upload"
PREDICT_ENDPOINT = f"{HF_SPACE_URL}/gradio_api/run/predict"
REQUEST_TIMEOUT  = 60.0


def analyze_leaf_image(image_path: str) -> dict:
    """
    Appelle le modèle EfficientNet-B0 sur Hugging Face Space.
    Protocole Gradio 5.x : upload -> predict avec path + url construite.
    """
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        mime = "image/jpeg"
        if image_path.lower().endswith(".png"):
            mime = "image/png"
        elif image_path.lower().endswith(".webp"):
            mime = "image/webp"

        # ── Étape 1 : Upload ──────────────────────────────────────────────────
        upload_response = httpx.post(
            UPLOAD_ENDPOINT,
            files={"files": ("image.jpg", image_bytes, mime)},
            timeout=REQUEST_TIMEOUT,
        )
        upload_response.raise_for_status()
        uploaded_paths = upload_response.json()

        if not uploaded_paths or not isinstance(uploaded_paths, list):
            raise ValueError(f"Upload échoué : {uploaded_paths}")

        uploaded_path = uploaded_paths[0]

        # ── Gradio 5.x : construire l'URL depuis le path uploadé ─────────────
        file_url = f"{HF_SPACE_URL}/gradio_api/file={uploaded_path}"
        logger.info("ML upload OK — url: %s", file_url)

        # ── Étape 2 : Predict ─────────────────────────────────────────────────
        payload = {
            "data": [
                {
                    "path":      uploaded_path,
                    "url":       file_url,
                    "orig_name": "image.jpg",
                    "mime_type": mime,
                    "size":      len(image_bytes),
                    "is_stream": False,
                    "meta":      {"_type": "gradio.FileData"},
                }
            ]
        }

        predict_response = httpx.post(
            PREDICT_ENDPOINT,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        predict_response.raise_for_status()
        result = predict_response.json()

        data = result.get("data", [])
        if len(data) >= 4:
            disease        = data[0] or "Inconnue"
            severity_label = data[1] or "Modérée"
            confidence_str = data[2] or "0%"
            recommendation = data[3] or ""

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

        raise ValueError(f"Réponse predict inattendue : {data}")

    except httpx.TimeoutException:
        logger.warning("ML inference timeout")
    except httpx.HTTPStatusError as e:
        logger.warning("ML HTTP error %s — body: %s", e.response.status_code, e.response.text[:300])
    except Exception as e:
        logger.warning("ML inference erreur : %s — fallback activé", e)

    return {
        "disease":        "Analyse indisponible",
        "confidence":     0.0,
        "severity":       "MEDIUM",
        "recommendation": "Service d'analyse temporairement indisponible. Réessayez dans quelques instants.",
        "source":         "fallback",
    }
