"""
Plans d'abonnement & feature-gating (catalogue central).

UN SEUL endroit a editer pour ajuster le decoupage commercial :
- CATEGORY_OF : a quelle categorie appartient chaque module (id de menu).
- PLAN_CATEGORIES : quelles categories sont incluses dans chaque plan.

Principe non-cassant : le plan par defaut d'une cooperative est 'enterprise'
(toutes categories), donc rien n'est restreint tant qu'un plan inferieur n'est
pas explicitement assigne.
"""
from __future__ import annotations

# Categories fonctionnelles
CATEGORIES = ["core", "compliance", "commercial", "premium"]

CATEGORY_LABELS = {
    "core": "Cœur agronomique",
    "compliance": "Conformité & durabilité",
    "commercial": "Commercial & traçabilité",
    "premium": "Premium / avancé",
}

# Module (id de lien de menu) -> categorie
CATEGORY_OF = {
    # Cœur agronomique
    "dashboard": "core",
    "assistant": "core",   # Assistant IA « mes données » — inclus pour tous les plans
    "plantations": "core",
    "producers": "core",
    "diagnostic": "core",
    "map": "core",
    # Jumeau de parcelle — vue coop « parcelles à risque » (descriptif). Core pour
    # l'instant ; passer en "premium" lors du tier commercial « Intelligence » (Phase 3).
    "twin-risk": "core",
    "agroforestry": "core",
    "harvests": "core",
    "guide": "core",
    # Conformité & durabilité
    "eudr": "compliance",
    "cacaoguard": "compliance",
    "ssrte": "compliance",
    "children": "compliance",
    "risk-assessment": "compliance",
    "monitoring": "compliance",
    "remediation": "compliance",
    "complaints": "compliance",
    "training": "compliance",
    "compliance": "compliance",
    "reports-cacaoguard": "compliance",
    "direction": "compliance",
    # Commercial & traçabilité
    "purchases": "commercial",
    "lots": "commercial",
    "certification": "commercial",
    # Premium / avancé
    "satellite": "premium",
    "farmforce": "premium",
    # Veille Marché : décision produit — incluse dans TOUS les plans (catégorie core).
    "veille": "core",
}

# Plan -> categories incluses
PLAN_CATEGORIES = {
    "starter":    {"core"},
    "compliance": {"core", "compliance"},
    "pro":        {"core", "compliance", "commercial"},
    "enterprise": {"core", "compliance", "commercial", "premium"},
}

PLAN_LABELS = {
    "starter": "Starter",
    "compliance": "Conformité",
    "pro": "Pro / Exportateur",
    "enterprise": "Entreprise",
}

DEFAULT_PLAN = "enterprise"

# Modules toujours accessibles (jamais bloques, ex. admin gere ailleurs).
ALWAYS_ALLOWED = {"admin"}


def normalize_plan(plan: str | None) -> str:
    """Retourne un plan valide (defaut enterprise si inconnu/None)."""
    return plan if plan in PLAN_CATEGORIES else DEFAULT_PLAN


def plan_categories(plan: str | None) -> set[str]:
    return set(PLAN_CATEGORIES[normalize_plan(plan)])


def allowed_modules(plan: str | None) -> list[str]:
    """Liste des ids de modules accessibles pour un plan donne."""
    cats = plan_categories(plan)
    mods = [m for m, c in CATEGORY_OF.items() if c in cats]
    return sorted(set(mods) | ALWAYS_ALLOWED)


def has_module(plan: str | None, module_id: str) -> bool:
    if module_id in ALWAYS_ALLOWED:
        return True
    cat = CATEGORY_OF.get(module_id)
    return cat is not None and cat in plan_categories(plan)


def has_feature(plan: str | None, category: str) -> bool:
    return category in plan_categories(plan)


def plan_overview(plan: str | None) -> dict:
    """Vue complete pour /me/features (front + diagnostic)."""
    p = normalize_plan(plan)
    cats = sorted(plan_categories(p))
    return {
        "plan": p,
        "plan_label": PLAN_LABELS.get(p, p),
        "categories": cats,
        "category_labels": {c: CATEGORY_LABELS[c] for c in CATEGORIES},
        "modules": allowed_modules(p),
        "all_plans": {
            name: {
                "label": PLAN_LABELS.get(name, name),
                "categories": sorted(c),
            }
            for name, c in PLAN_CATEGORIES.items()
        },
    }
