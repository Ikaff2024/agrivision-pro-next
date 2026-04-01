"""
recommendations.py — Génère des recommandations terrain actionnables
à partir des résultats du moteur CacaoEngine.

Chaque recommandation est concrète, immédiatement applicable par un
technicien agricole en Côte d'Ivoire.
"""
from typing import List, Dict, Any


# ── Types ─────────────────────────────────────────────────────────────────────

PRIORITY_HIGH   = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW    = "low"

CATEGORY_MALADIE      = "Risque maladie"
CATEGORY_IRRIGATION   = "Irrigation & eau"
CATEGORY_OMBRAGE      = "Ombrage"
CATEGORY_PLANTATION   = "Gestion plantation"
CATEGORY_SURVEILLANCE = "Surveillance"


def build_recommendations(
    module_results: List[Dict[str, Any]],
    inputs: Dict[str, Any],
    global_score: float,
    global_risk: str,
) -> List[Dict[str, Any]]:
    """
    Génère une liste de recommandations actionnables triées par priorité.

    Args:
        module_results: liste des résultats par module (score, module_name, reasons)
        inputs: paramètres d'entrée du diagnostic (humidity, rainfall, temp, age, shade)
        global_score: score global (0-100)
        global_risk: "LOW" | "MEDIUM" | "HIGH"

    Returns:
        Liste de dicts { priority, category, title, action, icon }
    """
    recs = []
    modules = {m["module_name"]: m for m in module_results}

    humidity = inputs.get("humidity_pct")
    rainfall = inputs.get("rainfall_mm_month")
    temp     = inputs.get("avg_temp_c")
    shade    = inputs.get("shade_tree_density_pct")
    age      = inputs.get("plantation_age_years")

    # ── Module : Risque maladie ───────────────────────────────────────────────
    dm = modules.get("disease_risk", {})
    dm_score = dm.get("score", 0)

    if dm_score >= 70:
        recs.append({
            "priority": PRIORITY_HIGH,
            "category": CATEGORY_MALADIE,
            "icon": "🚨",
            "title": "Traitement fongicide urgent",
            "action": (
                "Appliquer un traitement au cuivre (bouillie bordelaise 1%) ou un fongicide "
                "homologué sur les cabosses et le tronc. Intervenir dans les 48h. "
                "Inspecter toutes les cabosses visibles pour détecter la pourriture brune (Phytophthora)."
            ),
        })
    elif dm_score >= 40:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_MALADIE,
            "icon": "⚠️",
            "title": "Surveillance renforcée des maladies",
            "action": (
                "Inspecter la plantation deux fois par semaine. "
                "Retirer et enterrer les cabosses malades immédiatement. "
                "Envisager un traitement préventif au cuivre si les pluies persistent."
            ),
        })

    # ── Humidité élevée ───────────────────────────────────────────────────────
    if humidity is not None and humidity >= 85:
        recs.append({
            "priority": PRIORITY_HIGH,
            "category": CATEGORY_MALADIE,
            "icon": "💧",
            "title": "Humidité critique — aérer la plantation",
            "action": (
                f"Humidité à {humidity}% — conditions idéales pour Phytophthora et Botryodiplodia. "
                "Effectuer une taille sanitaire pour améliorer la circulation d'air. "
                "Éviter tout arrosage supplémentaire."
            ),
        })
    elif humidity is not None and humidity >= 75:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_MALADIE,
            "icon": "💧",
            "title": "Humidité élevée — ventilation recommandée",
            "action": (
                f"Humidité à {humidity}% — risque fongique en hausse. "
                "Tailler les branches basses et les gourmands pour améliorer l'aération."
            ),
        })

    # ── Pluviométrie ──────────────────────────────────────────────────────────
    rm = modules.get("rainfall_balance", {})
    rm_score = rm.get("score", 0)

    if rainfall is not None and rainfall < 60:
        recs.append({
            "priority": PRIORITY_HIGH,
            "category": CATEGORY_IRRIGATION,
            "icon": "🚿",
            "title": "Stress hydrique — irrigation nécessaire",
            "action": (
                f"Pluviométrie à {rainfall} mm/mois — en dessous du seuil optimal (80 mm). "
                "Irriguer 2 fois par semaine si possible, en privilégiant le pied des arbres. "
                "Appliquer un paillage pour conserver l'humidité du sol."
            ),
        })
    elif rainfall is not None and rainfall >= 250:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_IRRIGATION,
            "icon": "🌧️",
            "title": "Excès de pluie — drainage à vérifier",
            "action": (
                f"Pluviométrie à {rainfall} mm/mois — risque d'asphyxie racinaire. "
                "Vérifier que les canaux de drainage sont dégagés. "
                "Contrôler l'état des racines sur quelques arbres."
            ),
        })

    # ── Température ───────────────────────────────────────────────────────────
    if temp is not None and temp >= 30:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_OMBRAGE,
            "icon": "🌡️",
            "title": "Stress thermique — renforcer l'ombrage",
            "action": (
                f"Température à {temp}°C — au-dessus du seuil optimal pour le cacao (28°C). "
                "Planter des bananiers ou légumineuses entre les cacaoyers si l'ombrage est insuffisant. "
                "Éviter les travaux lourds aux heures chaudes (11h-15h)."
            ),
        })

    # ── Ombrage ───────────────────────────────────────────────────────────────
    sm = modules.get("shade_balance", {})
    sm_score = sm.get("score", 0)

    if shade is not None and shade < 15:
        recs.append({
            "priority": PRIORITY_HIGH,
            "category": CATEGORY_OMBRAGE,
            "icon": "🌳",
            "title": "Ombrage insuffisant — planter en urgence",
            "action": (
                f"Densité d'ombrage à {shade}% — trop faible (optimal : 20-50%). "
                "Planter des arbres d'ombrage à croissance rapide (Gliricidia, bananiers). "
                "Le manque d'ombrage augmente le stress thermique et réduit les rendements de 30%."
            ),
        })
    elif shade is not None and shade > 70:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_OMBRAGE,
            "icon": "✂️",
            "title": "Ombrage excessif — élagage nécessaire",
            "action": (
                f"Densité d'ombrage à {shade}% — trop dense (optimal : 20-50%). "
                "Éclaircir progressivement les arbres d'ombrage. "
                "Un ombrage excessif favorise l'humidité et les maladies fongiques."
            ),
        })
    elif shade is not None and 15 <= shade < 20:
        recs.append({
            "priority": PRIORITY_LOW,
            "category": CATEGORY_OMBRAGE,
            "icon": "🌿",
            "title": "Ombrage légèrement insuffisant",
            "action": (
                f"Densité à {shade}% — légèrement en dessous de l'optimal. "
                "Envisager la plantation de 2-3 arbres d'ombrage par hectare cette saison."
            ),
        })

    # ── Âge de la plantation ──────────────────────────────────────────────────
    am = modules.get("plantation_age", {})
    am_score = am.get("score", 0)

    if age is not None and age < 3:
        recs.append({
            "priority": PRIORITY_LOW,
            "category": CATEGORY_PLANTATION,
            "icon": "🌱",
            "title": "Jeune plantation — soins intensifs",
            "action": (
                f"Plantation de {age} an(s) — stade juvénile critique. "
                "Fertiliser avec NPK 15-15-15 (2 fois/an). "
                "Désherber manuellement tous les mois. "
                "Protéger des ravageurs avec un suivi hebdomadaire."
            ),
        })
    elif age is not None and age > 30:
        recs.append({
            "priority": PRIORITY_MEDIUM,
            "category": CATEGORY_PLANTATION,
            "icon": "🔄",
            "title": "Plantation âgée — envisager le renouvellement",
            "action": (
                f"Plantation de {age} ans — les rendements diminuent après 25 ans. "
                "Évaluer le potentiel de greffage sur des porte-greffes tolérants. "
                "Planifier un programme de replantation progressive (25% par an)."
            ),
        })

    # ── Recommandation générale selon le risque global ────────────────────────
    if global_risk == "LOW" and not recs:
        recs.append({
            "priority": PRIORITY_LOW,
            "category": CATEGORY_SURVEILLANCE,
            "icon": "✅",
            "title": "Plantation en bonne santé",
            "action": (
                "Conditions optimales — maintenir les pratiques actuelles. "
                "Effectuer un diagnostic de routine dans 4 semaines. "
                "Continuer le programme de fertilisation et d'entretien habituel."
            ),
        })
    elif global_risk == "HIGH" and len(recs) < 2:
        recs.append({
            "priority": PRIORITY_HIGH,
            "category": CATEGORY_SURVEILLANCE,
            "icon": "🔍",
            "title": "Inspection terrain immédiate requise",
            "action": (
                "Score de risque élevé — une visite terrain dans les 72h est indispensable. "
                "Vérifier l'état des cabosses, des feuilles et du sol. "
                "Documenter les anomalies observées et contacter un agronome si nécessaire."
            ),
        })

    # ── Trier : HIGH → MEDIUM → LOW ──────────────────────────────────────────
    priority_order = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))

    return recs
