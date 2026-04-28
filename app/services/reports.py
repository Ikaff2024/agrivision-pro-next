"""
app/services/reports.py — Génération de rapports PDF de plantations.

Combine Jinja2 (templating HTML) et WeasyPrint (HTML→PDF) pour produire
un rapport multi-pages avec design AgriVision Pro.

Architecture :
    1. build_plantation_context(db, plantation) → dict pour le template
    2. generate_plantation_pdf(context) → bytes du PDF final
    3. report_filename(plantation) → nom de fichier slugifié

L'import de WeasyPrint est différé dans generate_plantation_pdf() pour ne
pas casser l'import du module en environnement de test où les libs
système (Cairo/Pango) ne sont pas installées.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.db.models import (
    Plantation,
    Diagnostic,
    Harvest,
    AgroforestryRecord,
    Cooperative,
    PlantationBoundary,
)


# ─── Setup Jinja2 ─────────────────────────────────────────────────────────────
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ─── Helpers de formatage ─────────────────────────────────────────────────────
def slugify(text: str) -> str:
    """Convertit un texte en slug ASCII safe pour nom de fichier."""
    if not text:
        return "plantation"
    accents_map = str.maketrans(
        "àâäéèêëîïôöùûüÿçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ",
        "aaaeeeeiioouuuycAAAEEEEIIOOUUUC",
    )
    text = text.translate(accents_map)
    text = re.sub(r"[^\w\s-]", "", text).strip()
    text = re.sub(r"[-\s]+", "_", text)
    return text or "plantation"


def fmt_date(d: Optional[datetime]) -> str:
    """Date au format français jj/mm/aaaa."""
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y")


def fmt_number(n: Optional[float], decimals: int = 0, suffix: str = "") -> str:
    """Nombre avec séparateur de milliers FR (espace fine insécable)."""
    if n is None:
        return "—"
    if decimals == 0:
        formatted = f"{int(n):,}".replace(",", "\u202f")
    else:
        formatted = f"{n:,.{decimals}f}".replace(",", "\u202f").replace(".", ",")
    return formatted + suffix


def get_score_color(score: Optional[float]) -> str:
    """Couleur HEX selon le score global agronomique (0–100)."""
    if score is None:
        return "#9ca3af"  # gris neutre
    if score >= 75:
        return "#16a34a"  # vert
    if score >= 50:
        return "#f59e0b"  # orange
    return "#dc2626"  # rouge


def get_risk_label(risk: Optional[str]) -> str:
    """Convertit un risk_level technique en label utilisateur FR."""
    mapping = {
        "low": "Faible",
        "medium": "Modéré",
        "high": "Élevé",
        "critical": "Critique",
    }
    return mapping.get((risk or "").lower(), risk or "—")


# ─── Construction du contexte ─────────────────────────────────────────────────
def build_plantation_context(db: Session, plantation: Plantation) -> dict:
    """
    Construit le contexte Jinja2 pour le template de rapport.
    Récupère et agrège toutes les données associées à la plantation.

    Args:
        db: Session SQLAlchemy active
        plantation: instance Plantation déjà récupérée et autorisée

    Returns:
        dict prêt à passer à template.render(**context)
    """
    # ─── Diagnostic le plus récent ────────────────────────────────────────────
    last_diagnostic = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation.id)
        .order_by(Diagnostic.created_at.desc())
        .first()
    )

    # ─── Récoltes ────────────────────────────────────────────────────────────
    harvests = (
        db.query(Harvest)
        .filter(Harvest.plantation_id == plantation.id)
        .order_by(Harvest.harvest_date.desc())
        .all()
    )
    last_harvests = harvests[:5]

    current_year = datetime.now().year
    total_kg_all_time = sum(h.quantity_kg for h in harvests)
    total_kg_current_year = sum(
        h.quantity_kg for h in harvests
        if h.harvest_date and h.harvest_date.year == current_year
    )

    # Potentiel annuel : 0,5 kg/plant (formule métier AgriVision)
    potential_kg = (plantation.plant_count or 0) * 0.5
    yield_pct = (
        round(total_kg_current_year / potential_kg * 100, 1)
        if potential_kg > 0 else 0.0
    )

    # ─── Agroforesterie ───────────────────────────────────────────────────────
    agro_records = (
        db.query(AgroforestryRecord)
        .filter(AgroforestryRecord.plantation_id == plantation.id)
        .all()
    )
    total_trees_per_ha = sum((r.count_per_hectare or 0) for r in agro_records)
    species_count = len(agro_records)

    # Stock carbone simplifié : 0,05 tCO2/ha/an par arbre/ha (FAO/IPCC simplifié)
    carbon_stock_tco2_ha = round(total_trees_per_ha * 0.05, 2)

    # ─── Boundary (délimitation) ──────────────────────────────────────────────
    boundary = (
        db.query(PlantationBoundary)
        .filter(PlantationBoundary.plantation_id == plantation.id)
        .first()
    )

    # ─── Coopérative ──────────────────────────────────────────────────────────
    cooperative = None
    if plantation.cooperative_id:
        cooperative = (
            db.query(Cooperative)
            .filter(Cooperative.id == plantation.cooperative_id)
            .first()
        )

    # ─── Densité plants/ha + conformité CCC ──────────────────────────────────
    density: Optional[float] = None
    density_compliance = "—"
    density_compliance_color = "#9ca3af"
    if plantation.plant_count and plantation.hectares and plantation.hectares > 0:
        density = round(plantation.plant_count / plantation.hectares, 0)
        if 1000 <= density <= 1400:
            density_compliance = "Conforme aux standards CCC (1000–1400 plants/ha)"
            density_compliance_color = "#16a34a"
        elif density < 1000:
            density_compliance = "Sous-densité (CCC recommande 1000–1400 plants/ha)"
            density_compliance_color = "#f59e0b"
        else:
            density_compliance = "Sur-densité (CCC recommande 1000–1400 plants/ha)"
            density_compliance_color = "#f59e0b"

    # ─── Recommandations (même logique que /diagnostics/{id}/recommendations) ───
    # Le moteur ne stocke pas les module_results en DB ; on reconstitue les
    # inputs depuis le diagnostic et on rappelle build_recommendations() avec
    # la signature exacte qu'il attend.
    recommendations = []
    if last_diagnostic:
        try:
            from app.recommendations import build_recommendations
            recommendations = build_recommendations(
                module_results=[],
                inputs={
                    "humidity_pct":           last_diagnostic.humidity_pct,
                    "rainfall_mm_month":      last_diagnostic.rainfall_mm_month,
                    "avg_temp_c":             last_diagnostic.avg_temp_c,
                    "shade_tree_density_pct": last_diagnostic.shade_tree_density_pct,
                    "plantation_age_years":   last_diagnostic.plantation_age_years,
                },
                global_score=last_diagnostic.global_score or 0.0,
                global_risk=(last_diagnostic.global_risk_level or "LOW").upper(),
            ) or []
        except Exception as exc:
            # On loggue l'erreur au lieu de l'avaler silencieusement
            import logging
            logging.getLogger("agrivision").warning(
                "Echec chargement recommandations pour plantation %s : %s",
                plantation.id, exc,
            )
            recommendations = []

    return {
        # Entités principales
        "plantation": plantation,
        "cooperative": cooperative,
        "diagnostic": last_diagnostic,
        "harvests": last_harvests,
        "all_harvests_count": len(harvests),
        "agro_records": agro_records,
        "boundary": boundary,
        "recommendations": recommendations,
        # Métriques calculées
        "total_kg_all_time": total_kg_all_time,
        "total_kg_current_year": total_kg_current_year,
        "potential_kg": potential_kg,
        "yield_pct": yield_pct,
        "current_year": current_year,
        "density": density,
        "density_compliance": density_compliance,
        "density_compliance_color": density_compliance_color,
        "species_count": species_count,
        "total_trees_per_ha": total_trees_per_ha,
        "carbon_stock_tco2_ha": carbon_stock_tco2_ha,
        # Méta
        "generated_at": datetime.now(),
        # Helpers passés au template
        "fmt_date": fmt_date,
        "fmt_number": fmt_number,
        "score_color": get_score_color(
            last_diagnostic.global_score if last_diagnostic else None
        ),
        "risk_label": get_risk_label(
            last_diagnostic.global_risk_level if last_diagnostic else None
        ),
    }


# ─── Génération PDF ───────────────────────────────────────────────────────────
def generate_plantation_pdf(context: dict) -> bytes:
    """
    Génère le PDF du rapport de plantation.

    Import différé de WeasyPrint pour ne pas casser l'import du module
    en environnement de test où Cairo/Pango ne sont pas installés.

    Args:
        context: dict construit par build_plantation_context()

    Returns:
        bytes du PDF généré
    """
    from weasyprint import HTML  # import différé

    template = _jinja_env.get_template("plantation_report.html")
    html_content = template.render(**context)

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes


def report_filename(plantation: Plantation) -> str:
    """Nom de fichier propre : Rapport_Plantation_<slug>_<YYYY-MM-DD>.pdf"""
    slug = slugify(plantation.name)
    today = datetime.now().strftime("%Y-%m-%d")
    return f"Rapport_Plantation_{slug}_{today}.pdf"
