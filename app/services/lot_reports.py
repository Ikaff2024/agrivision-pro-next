"""
Generation PDF du passeport de tracabilite d'un lot (charte AgriVision Pro).

Aligne sur les autres rapports (DDS, Livret, Fiches SSRTE) : WeasyPrint + fallback
PDF natif sans dependance Cairo (Windows/CI), via l'environnement Jinja2 partage.
"""
from __future__ import annotations

import datetime

from app.services.reports import _jinja_env, _pdf_escape, slugify


def _fmt_dt(value) -> str:
    """Formate un horodatage (datetime ou ISO str) en 'JJ/MM/AAAA HH:MM'."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, str):
            value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)[:16]


def build_lot_passport_context(passport: dict) -> dict:
    """Construit le contexte Jinja2 pour le template passeport de lot."""
    lot = passport.get("lot", {}) or {}
    summary = passport.get("summary", {}) or {}
    cert = passport.get("certification") or {}
    wh = passport.get("warehouse") or {}
    movements = [
        {
            "movement_type": m.get("movement_type"),
            "quantity_kg": m.get("quantity_kg") or 0,
            "reference": m.get("reference"),
            "date": _fmt_dt(m.get("created_at")),
        }
        for m in (passport.get("movements") or [])
    ]
    return {
        "generation_date": datetime.date.today().isoformat(),
        "code": passport.get("code") or lot.get("code") or "—",
        "status": lot.get("status") or "—",
        "season": lot.get("season") or "—",
        "certification": cert.get("code") if cert else None,
        "warehouse": wh.get("name") if wh else None,
        "exporter": lot.get("exporter") or None,
        "external_ref": lot.get("external_ref") or None,   # n° de connaissement / lot export
        "total_weight_kg": summary.get("total_weight_kg", 0),
        "bag_count": summary.get("bag_count", 0),
        "harvests": summary.get("harvests", 0),
        "producers": summary.get("producers", 0),
        "plantations": summary.get("plantations", 0),
        "eudr_compliance_rate_pct": summary.get("eudr_compliance_rate_pct", 0),
        "eudr_compliant_plantations": summary.get("eudr_compliant_plantations", 0),
        "eudr_total_plantations": summary.get("eudr_total_plantations", 0),
        "blocked_producers": summary.get("blocked_producers", 0),
        "composition": passport.get("composition", []) or [],
        "movements": movements,
    }


def generate_lot_passport_pdf(context: dict) -> bytes:
    """Genere le PDF du passeport via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("lot_passport_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_fallback_pdf(context)


def _generate_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native (tests / Windows sans Cairo)."""
    lines = [
        "AgriVision Pro - Passeport de tracabilite (lot)",
        f"Lot : {_pdf_escape(context['code'])}",
        f"Statut : {_pdf_escape(context['status'])}",
        f"Poids total : {context.get('total_weight_kg')} kg ({context.get('bag_count')} sacs)",
        f"Exportateur : {_pdf_escape(context.get('exporter') or '-')}",
        f"N connaissement : {_pdf_escape(context.get('external_ref') or '-')}",
        f"Producteurs : {context.get('producers')} - Plantations : {context.get('plantations')}",
        f"Conformite EUDR : {context.get('eudr_compliance_rate_pct')}%",
        f"Producteurs bloques : {context.get('blocked_producers')}",
        f"Date : {context['generation_date']}",
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


def lot_passport_filename(lot) -> str:
    """Nom de fichier PDF normalise."""
    code = getattr(lot, "code", None) or "lot"
    date_str = datetime.date.today().isoformat()
    return f"Passeport_{slugify(code)}_{date_str}.pdf"
