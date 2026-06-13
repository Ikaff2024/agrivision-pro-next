"""
Generation du Due Diligence Statement (DDS) EUDR au format PDF.

Reutilise l'environnement Jinja2 + WeasyPrint de app/services/reports.py.
Fallback PDF minimal sans dependance native en cas d'absence de WeasyPrint
(utile pour les tests Windows/CI sans Cairo/Pango).

Endpoint API : voir app/api/eudr_routes.py (GET /plantations/{id}/eudr-dds.pdf).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Inspection, Plantation, PlantationBoundary
from app.eudr.scoring import compute_eudr_score
from app.services.reports import (
    _jinja_env,
    _pdf_escape,
    slugify,
)


def _safe_isoformat(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _resolve_active_block_reason(plantation: Plantation, db: Session) -> tuple[bool, Optional[str]]:
    """Retourne (has_active_block, reason_label) pour le producteur de la plantation."""
    if plantation.producer_id is None:
        return False, None
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
    except ImportError:
        return False, None
    active = (
        db.query(TraceabilityBlock)
        .filter(
            TraceabilityBlock.producer_id == plantation.producer_id,
            TraceabilityBlock.status == BlockStatus.ACTIVE,
        )
        .first()
    )
    if active is None:
        return False, None
    reason = active.block_reason.value if active.block_reason else "non_specifie"
    return True, reason


def _resolve_last_inspection_date(plantation: Plantation, db: Session) -> Optional[str]:
    last = (
        db.query(Inspection)
        .filter(Inspection.plantation_id == plantation.id, Inspection.date.isnot(None))
        .order_by(Inspection.date.desc())
        .first()
    )
    if last and last.date:
        return last.date.date().isoformat()
    return None


def build_dds_context(plantation: Plantation, db: Session, operator_name: Optional[str] = None) -> dict:
    """Construit le contexte Jinja2 pour le template DDS."""
    score = compute_eudr_score(plantation, db)
    boundary: Optional[PlantationBoundary] = plantation.boundary
    has_block, block_reason = _resolve_active_block_reason(plantation, db)
    last_inspection = _resolve_last_inspection_date(plantation, db)

    # DDS reference : DDS-{ANNEE}-{PLANTATION_ID padded 4}
    today = datetime.date.today()
    dds_reference = f"DDS-{today.year}-{plantation.id:04d}"

    # Cooperative & producer
    coop_name = None
    if plantation.cooperative_id:
        coop = plantation.cooperative
        if coop:
            coop_name = coop.name
    producer_code = None
    if plantation.producer_id and plantation.producer:
        producer_code = plantation.producer.code_yeyasso

    return {
        "dds_reference": dds_reference,
        "generation_date": today.isoformat(),
        "methodology_version": score.methodology_version,
        "operator_name": operator_name or coop_name or plantation.owner_name or "Operateur AgriVision Pro",
        "plantation": plantation,
        "geo_hectares": boundary.area_hectares if boundary else None,
        "score": score.score,
        "max_score": score.max_score,
        "status": score.status,
        "rules": [r.to_dict() for r in score.rules],
        "polygon_geojson": boundary.geojson if boundary else None,
        "polygon_method": boundary.method if boundary else None,
        "points_count": boundary.points_count if boundary else None,
        "cooperative_name": coop_name,
        "coop_name": coop_name,
        "coop_logo": (plantation.cooperative.logo_data if plantation.cooperative else None),
        "coop_logo_size": ((plantation.cooperative.logo_size if plantation.cooperative else None) or "md"),
        "coop_logo_plaque": (bool(plantation.cooperative.logo_plaque) if plantation.cooperative else True),
        "producer_code": producer_code,
        "last_inspection_date": last_inspection,
        "has_active_block": has_block,
        "active_block_reason": block_reason,
    }


def generate_dds_pdf(context: dict) -> bytes:
    """Genere le PDF DDS via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("eudr_dds_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_dds_fallback_pdf(context)


def _generate_dds_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native, pour tests/Windows sans Cairo.

    Format PDF 1.4 a la main avec quelques lignes de texte. Suffisant pour
    valider via tests que le pipeline genere bien du PDF, meme si la mise en
    forme riche n'est pas la.
    """
    plantation = context["plantation"]
    lines = [
        "EUDR Due Diligence Statement",
        f"Reference : {_pdf_escape(context['dds_reference'])}",
        f"Plantation : {_pdf_escape(plantation.name)}",
        f"Producteur : {_pdf_escape(plantation.owner_name or '-')}",
        f"Score : {context['score']}/{context['max_score']} - {context['status']}",
        f"Date : {context['generation_date']}",
        f"Operateur : {_pdf_escape(context['operator_name'])}",
        "",
        "Regles :",
    ]
    for rule in context.get("rules", []):
        symbol = "[OK]" if rule.get("passed") else "[FAIL]"
        lines.append(f"  {symbol} {_pdf_escape(rule.get('label', '?'))}")

    # Construction PDF minimal (1 page, Helvetica 11pt)
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


def dds_filename(plantation: Plantation) -> str:
    """Nom de fichier DDS PDF normalise."""
    return f"DDS_{slugify(plantation.name)}_{datetime.date.today().isoformat()}.pdf"
