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


def coop_brand(db: Session, cooperative_id: Optional[int]) -> dict:
    """Logo (data-URI) + nom de la coopérative pour l'en-tête des PDF.

    Renvoie toujours les deux clés (None si absent) → les templates retombent
    sur l'identité AgriVision Pro par défaut.
    """
    base = {"coop_logo": None, "coop_name": None, "coop_logo_size": "md", "coop_logo_plaque": True}
    if not cooperative_id:
        return base
    coop = db.query(Cooperative).filter(Cooperative.id == cooperative_id).first()
    if not coop:
        return base
    return {
        "coop_logo": coop.logo_data or None,
        "coop_name": coop.name or None,
        "coop_logo_size": coop.logo_size or "md",
        "coop_logo_plaque": bool(coop.logo_plaque),
    }


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

    # ─── NDVI : si lat/lon disponibles, calculer pour le garde-fou Anti-Detracteur
    ndvi_warning = None
    try:
        if plantation.latitude is not None and plantation.longitude is not None:
            from app.ndvi_service import get_ndvi
            from app.api.routes import _interpret_ndvi
            ndvi_result = get_ndvi(plantation.latitude, plantation.longitude)
            interpretation = _interpret_ndvi(ndvi_result["ndvi"])
            if interpretation["confidence"] == "low":
                ndvi_warning = {
                    "ndvi": ndvi_result["ndvi"],
                    "message": interpretation["message"],
                }
    except Exception as exc:
        import logging
        logging.getLogger("agrivision").warning(
            "Echec calcul NDVI pour rapport plantation %s : %s",
            plantation.id, exc,
        )

    return {
        # Entités principales
        "plantation": plantation,
        "cooperative": cooperative,
        "coop_logo": (cooperative.logo_data if cooperative else None),
        "coop_name": (cooperative.name if cooperative else None),
        "coop_logo_size": ((cooperative.logo_size if cooperative else None) or "md"),
        "coop_logo_plaque": (bool(cooperative.logo_plaque) if cooperative else True),
        "diagnostic": last_diagnostic,
        "harvests": last_harvests,
        "all_harvests_count": len(harvests),
        "agro_records": agro_records,
        "boundary": boundary,
        "recommendations": recommendations,
        "ndvi_warning": ndvi_warning,
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


def generate_cacaoguard_pdf(context: dict) -> bytes:
    """
    Genere le PDF officiel CacaoGuard.

    Le contexte est le rapport de due diligence deja agrege par l'API
    compliance. WeasyPrint reste importe au moment de l'appel pour garder
    les tests et environnements Windows legers.
    """
    template = _jinja_env.get_template("cacaoguard_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_cacaoguard_fallback_pdf(context)


def _pdf_escape(text: object) -> str:
    value = str(text if text is not None else "")
    value = value.encode("latin-1", "replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _generate_cacaoguard_fallback_pdf(context: dict) -> bytes:
    """
    PDF minimal sans dependance native.

    Utile sur Windows local quand WeasyPrint est installe mais que Cairo/Pango
    ne le sont pas. Le rendu premium reste fourni par WeasyPrint quand il est
    disponible.
    """
    report = context.get("report", {})
    coverage = report.get("coverage", {})
    indicators = report.get("indicators", {})
    lines = [
        "AgriVision Pro / CacaoGuard",
        "Rapport officiel de due diligence travail des enfants",
        f"Type: {report.get('report_type', 'CacaoGuard due diligence')}",
        f"Producteurs: {coverage.get('producers', 0)}",
        f"Plantations: {coverage.get('plantations', 0)}",
        f"Enfants suivis: {coverage.get('children', 0)}",
        f"Enfants en travail ferme: {indicators.get('children_working', 0)}",
        f"Scolarisation: {indicators.get('school_enrollment_rate', 0)}%",
        f"Visites completees: {indicators.get('monitoring_visits_completed', 0)}",
        f"Visites avec photos: {indicators.get('monitoring_visits_with_photos', 0)}",
        f"Consentements: {indicators.get('monitoring_visits_with_consent', 0)}",
        f"Sessions formation: {indicators.get('training_sessions_completed', 0)}",
        f"Participants formes: {indicators.get('training_participants', 0)}",
        f"Fiches A SSRTE: {indicators.get('ssrte_community_profiles', 0)}",
        f"F1 menage SSRTE: {indicators.get('ssrte_household_profiles', 0)}",
        f"Fiches C SSRTE: {indicators.get('ssrte_plantation_visits', 0)}",
        f"Suspicions SSRTE: {indicators.get('ssrte_suspected_child_labor_visits', 0)}",
        f"Comptes FarmForce: {indicators.get('farmforce_assessments', 0)}",
        f"Profit net FarmForce: {indicators.get('farmforce_total_profit_cfa', 0)} CFA",
        f"Marges negatives FarmForce: {indicators.get('farmforce_negative_profit_assessments', 0)}",
        f"Plans actifs: {indicators.get('active_remediation_plans', 0)}",
        f"Blocages tracabilite: {indicators.get('active_traceability_blocks', 0)}",
        "",
        "Ce PDF minimal est genere sans WeasyPrint. Installer Cairo/Pango",
        "active la version graphique complete du rapport.",
    ]
    stream_lines = ["BT", "/F1 12 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(lines):
        prefix = "" if index == 0 else "T* "
        stream_lines.append(f"{prefix}({_pdf_escape(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF".encode("ascii")
    )
    return bytes(pdf)


def report_filename(plantation: Plantation) -> str:
    """Nom de fichier propre : Rapport_Plantation_<slug>_<YYYY-MM-DD>.pdf"""
    slug = slugify(plantation.name)
    today = datetime.now().strftime("%Y-%m-%d")
    return f"Rapport_Plantation_{slug}_{today}.pdf"


def cacaoguard_report_filename() -> str:
    """Nom de fichier propre pour le rapport due diligence CacaoGuard."""
    today = datetime.now().strftime("%Y-%m-%d")
    return f"Rapport_CacaoGuard_Due_Diligence_{today}.pdf"
