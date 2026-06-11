"""
Generation PDF du Livret de suivi de la plantation (FarmForce / DD farm records).

Reutilise l'environnement Jinja2 + WeasyPrint de app/services/reports.py, avec
un fallback PDF minimal sans dependance native (Windows/CI sans Cairo/Pango),
identique au pattern du DDS EUDR (app/services/eudr_reports.py).
"""
from __future__ import annotations

import datetime
import os
from typing import Optional

from app.db.models import FarmForceAssessment
from app.services.reports import _jinja_env, _pdf_escape, slugify


# Living Income Benchmark (revenu vital de reference) — CFA/menage/an.
# Defaut aligne sur l'ordre de grandeur Living Income Community of Practice
# pour la cacaoculture en Cote d'Ivoire. Surchargeable par variable
# d'environnement pour s'adapter a la source/annee de la cooperative.
LIVING_INCOME_BENCHMARK_CFA = float(os.getenv("LIVING_INCOME_BENCHMARK_CFA", "2360000"))


def living_income_assessment(net_income_cfa) -> dict:
    """Verdict revenu vital : compare le revenu net au seuil de reference.

    Calcule a la lecture (jamais stocke) pour rester ajustable si le seuil change.
    Retourne benchmark, ecart, pourcentage et statut (atteint | ecart).
    """
    bench = LIVING_INCOME_BENCHMARK_CFA
    net = _num(net_income_cfa)
    if not bench or bench <= 0:
        return {
            "living_income_benchmark_cfa": None,
            "living_income_gap_cfa": None,
            "living_income_pct": None,
            "living_income_status": None,
        }
    return {
        "living_income_benchmark_cfa": bench,
        "living_income_gap_cfa": round(net - bench, 2),
        "living_income_pct": round(net / bench * 100, 1),
        "living_income_status": "atteint" if net >= bench else "ecart",
    }


def _num(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _money(value) -> str:
    """Formate un montant CFA avec separateur de milliers (espace insecable)."""
    return f"{int(round(_num(value))):,}".replace(",", " ")


def build_farmforce_context(assessment: FarmForceAssessment) -> dict:
    """Construit le contexte Jinja2 pour le template Livret."""
    producer_name = assessment.producer.nom_complet if assessment.producer else "Producteur"
    coop = assessment.producer.cooperative if assessment.producer else None
    li = living_income_assessment(assessment.net_income_cfa)
    return {
        "generation_date": datetime.date.today().isoformat(),
        "producer_name": producer_name,
        "coop_logo": (coop.logo_data if coop else None),
        "coop_name": (coop.name if coop else None),
        "coop_logo_size": ((coop.logo_size if coop else None) or "md"),
        "coop_logo_plaque": (bool(coop.logo_plaque) if coop else True),
        "campaign_label": assessment.campaign_label,
        "localite": assessment.localite,
        "pr_code": assessment.pr_code,
        "household_members": assessment.household_members or [],
        "parcels": assessment.parcels or [],
        "revenue_items": assessment.revenue_items or [],
        "cost_items": assessment.cost_items or [],
        "family_labor_items": assessment.family_labor_items or [],
        "hired_labor_items": assessment.hired_labor_items or [],
        "food_security_items": assessment.food_security_items or [],
        "household_expense_items": assessment.household_expense_items or [],
        "notes": assessment.notes,
        "total_revenue_cfa": _money(assessment.total_revenue_cfa),
        "total_cost_cfa": _money(assessment.total_cost_cfa),
        "profit_cfa": _money(assessment.profit_cfa),
        "total_household_expenses_cfa": _money(assessment.total_household_expenses_cfa),
        "net_income_cfa": _money(assessment.net_income_cfa),
        "net_income_raw": _num(assessment.net_income_cfa),
        "family_labor_days": _money(assessment.family_labor_days),
        "hired_labor_days": _money(assessment.hired_labor_days),
        "return_per_family_day_cfa": (
            _money(assessment.return_per_family_day_cfa)
            if assessment.return_per_family_day_cfa is not None else None
        ),
        "living_income_benchmark_cfa": _money(li["living_income_benchmark_cfa"]) if li["living_income_benchmark_cfa"] else None,
        "living_income_gap_cfa": _money(li["living_income_gap_cfa"]) if li["living_income_gap_cfa"] is not None else None,
        "living_income_gap_negative": (li["living_income_gap_cfa"] or 0) < 0,
        "living_income_pct": li["living_income_pct"],
        "living_income_status": li["living_income_status"],
    }


def generate_farmforce_pdf(context: dict) -> bytes:
    """Genere le PDF Livret via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("farmforce_livret_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_farmforce_fallback_pdf(context)


def _generate_farmforce_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native (tests / Windows sans Cairo)."""
    lines = [
        "Livret de suivi de la plantation (FarmForce)",
        f"Producteur : {_pdf_escape(context['producer_name'])}",
        f"Campagne : {_pdf_escape(context['campaign_label'])}",
        f"Localite : {_pdf_escape(context.get('localite') or '-')}",
        f"Date : {context['generation_date']}",
        "",
        f"Rentrees : {_pdf_escape(context['total_revenue_cfa'])} CFA",
        f"Couts : {_pdf_escape(context['total_cost_cfa'])} CFA",
        f"Profit : {_pdf_escape(context['profit_cfa'])} CFA",
        f"Depenses menage : {_pdf_escape(context['total_household_expenses_cfa'])} CFA",
        f"Revenu net disponible : {_pdf_escape(context['net_income_cfa'])} CFA",
    ]
    content_stream_lines = [b"BT", b"/F1 14 Tf", b"50 800 Td"]
    for i, line in enumerate(lines):
        content_stream_lines.append(b"(" + line.encode("latin-1", "replace") + b") Tj")
        if i < len(lines) - 1:
            content_stream_lines.append(b"0 -16 Td")
    content_stream_lines.append(b"ET")
    content_stream = b"\n".join(content_stream_lines)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n" + content_stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    pdf += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return pdf


def farmforce_filename(assessment: FarmForceAssessment) -> str:
    """Nom de fichier Livret PDF normalise."""
    producer = assessment.producer.nom_complet if assessment.producer else "producteur"
    return f"Livret_{slugify(producer)}_{assessment.campaign_label}.pdf"
