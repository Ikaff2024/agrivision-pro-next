import time


def analyze_leaf_image(image_path: str) -> dict:
    """
    Simule l'inférence d'un modèle de détection de maladies foliaires (VGG/ResNet).
    À remplacer par un vrai modèle ML en production.
    """
    time.sleep(0.5)  # Simulation temps d'inférence

    return {
        "disease": "Black Pod Disease",
        "confidence": 0.78,
        "severity": "MEDIUM",
        "recommendation": "Inspecter les cabosses et appliquer un fongicide à base de cuivre.",
    }
