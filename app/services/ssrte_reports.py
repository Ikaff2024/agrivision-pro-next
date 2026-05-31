"""
Generation PDF de la Fiche SSRTE B / F1 (profilage de menage).

Reutilise l'environnement Jinja2 + WeasyPrint de app/services/reports.py, avec
fallback PDF minimal sans dependance native (Windows/CI sans Cairo/Pango),
aligne sur le design du rapport plantation (comme DDS et Livret).
"""
from __future__ import annotations

import datetime
from typing import Optional

from app.db.models_social import (
    SsrteCommunityProfile,
    SsrteHouseholdProfile,
    SsrtePlantationVisit,
)
from app.services.reports import _jinja_env, _pdf_escape, slugify


# Libelles lisibles des indicateurs de services (cles techniques -> FR).
_SERVICE_LABELS = {
    "road_access": "Route praticable toute l'annee",
    "electricity": "Electricite",
    "water_point": "Point d'eau potable",
    "mobile_network": "Reseau mobile",
    "internet": "Internet mobile",
    "health_structure": "Structure sanitaire",
    "daily_labor": "Offre de travail journalier",
    "agri_inputs": "Offre d'intrants agricoles",
    "child_labor_orgs": "Organisations anti-travail des enfants",
    "kindergarten": "Jardin d'enfants",
    "primary_school": "Ecole primaire",
    "secondary_school": "Ecole secondaire",
    "school_canteen": "Cantine scolaire",
    "latrines": "Latrines (ecole)",
}


def _producer_name(profile: SsrteHouseholdProfile) -> str:
    return profile.producer.nom_complet if profile.producer else "Producteur"


def build_ficheb_context(profile: SsrteHouseholdProfile) -> dict:
    """Construit le contexte Jinja2 pour le template Fiche B."""
    risk_level = profile.risk_level.value if profile.risk_level else "none"
    return {
        "generation_date": datetime.date.today().isoformat(),
        "producer_name": _producer_name(profile),
        "interview_date": profile.interview_date.isoformat() if profile.interview_date else "—",
        "interviewer_name": profile.interviewer_name or "—",
        "household_size": profile.household_size,
        "children_count": profile.children_count,
        "school_age_children_count": profile.school_age_children_count,
        "enrolled_children_count": profile.enrolled_children_count,
        "household_members": profile.household_members or [],
        "vulnerabilities": profile.vulnerabilities or [],
        "child_work_declarations": profile.child_work_declarations or [],
        "school_constraints": profile.school_constraints or [],
        "farm_info": profile.farm_info or {},
        "risk_score": float(profile.risk_score or 0),
        "risk_level": risk_level,
        "consent_given": bool(profile.consent_given),
        "notes": profile.notes,
    }


def generate_ficheb_pdf(context: dict) -> bytes:
    """Genere le PDF Fiche B via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("ssrte_ficheb_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_ficheb_fallback_pdf(context)


def _generate_ficheb_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native (tests / Windows sans Cairo)."""
    lines = [
        "SSRTE Fiche B - Profilage de menage",
        f"Producteur : {_pdf_escape(context['producer_name'])}",
        f"Date entretien : {_pdf_escape(context['interview_date'])}",
        f"Agent : {_pdf_escape(context['interviewer_name'])}",
        f"Taille menage : {context.get('household_size') or '-'}",
        f"Membres listes : {len(context.get('household_members') or [])}",
        f"Parcelles cacao : {(context.get('farm_info') or {}).get('cocoa_parcels', '-')}",
        f"Niveau de risque : {_pdf_escape(context['risk_level'])} ({context['risk_score']})",
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


def ficheb_filename(profile: SsrteHouseholdProfile) -> str:
    """Nom de fichier Fiche B PDF normalise."""
    producer = profile.producer.nom_complet if profile.producer else "producteur"
    date_str = profile.interview_date.isoformat() if profile.interview_date else datetime.date.today().isoformat()
    return f"FicheB_{slugify(producer)}_{date_str}.pdf"


# ---------------------------------------------------------------------------
# Fiche C : visite de plantation
# ---------------------------------------------------------------------------

def build_fichec_context(visit: SsrtePlantationVisit) -> dict:
    """Construit le contexte Jinja2 pour le template Fiche C."""
    plantation_name = visit.plantation.name if visit.plantation else "Plantation"
    producer_name = visit.producer.nom_complet if visit.producer else "—"
    return {
        "generation_date": datetime.date.today().isoformat(),
        "plantation_name": plantation_name,
        "producer_name": producer_name,
        "visit_date": visit.visit_date.isoformat() if visit.visit_date else "—",
        "interviewer_name": visit.interviewer_name or "—",
        "gps_location": visit.gps_location or "—",
        "checklist_data": visit.checklist_data or {},
        "children_observed": visit.children_observed or [],
        "adults_observed": visit.adults_observed or [],
        "workers_present": visit.workers_present or [],
        "dangerous_tasks_observed": visit.dangerous_tasks_observed or [],
        "suspected_child_labor": bool(visit.suspected_child_labor),
        "immediate_actions_taken": visit.immediate_actions_taken,
        "photos": visit.photos or [],
        "consent_given": bool(visit.consent_given),
        "producer_signature": (visit.producer_signature_data or {}).get("signed_by") if visit.producer_signature_data else None,
        "assessor_signature": (visit.assessor_signature_data or {}).get("signed_by") if visit.assessor_signature_data else None,
        "notes": visit.notes,
    }


def generate_fichec_pdf(context: dict) -> bytes:
    """Genere le PDF Fiche C via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("ssrte_fichec_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_fichec_fallback_pdf(context)


def _generate_fichec_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native (tests / Windows sans Cairo)."""
    lines = [
        "SSRTE Fiche C - Visite de plantation",
        f"Plantation : {_pdf_escape(context['plantation_name'])}",
        f"Producteur : {_pdf_escape(context['producer_name'])}",
        f"Date visite : {_pdf_escape(context['visit_date'])}",
        f"Agent : {_pdf_escape(context['interviewer_name'])}",
        f"Enfants observes : {len(context.get('children_observed') or [])}",
        f"Adultes observes : {len(context.get('adults_observed') or [])}",
        f"Travailleurs presents : {len(context.get('workers_present') or [])}",
        f"Suspicion travail enfant : {'OUI' if context['suspected_child_labor'] else 'Non'}",
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


def fichec_filename(visit: SsrtePlantationVisit) -> str:
    """Nom de fichier Fiche C PDF normalise."""
    plantation = visit.plantation.name if visit.plantation else "plantation"
    date_str = visit.visit_date.isoformat() if visit.visit_date else datetime.date.today().isoformat()
    return f"FicheC_{slugify(plantation)}_{date_str}.pdf"


# ---------------------------------------------------------------------------
# Fiche A : profil localite
# ---------------------------------------------------------------------------

def build_fichea_context(profile: SsrteCommunityProfile) -> dict:
    """Construit le contexte Jinja2 pour le template Fiche A."""
    services = profile.services_available or {}
    present = [_SERVICE_LABELS[k] for k, v in services.items() if k in _SERVICE_LABELS and v]
    absent = [_SERVICE_LABELS[k] for k, v in services.items() if k in _SERVICE_LABELS and not v]
    members = profile.committee_members or []
    member_names = [m.get("name") if isinstance(m, dict) else str(m) for m in members]
    return {
        "generation_date": datetime.date.today().isoformat(),
        "locality": profile.locality,
        "section": profile.section or "—",
        "interview_date": profile.interview_date.isoformat() if profile.interview_date else "—",
        "respondent_name": profile.respondent_name or "—",
        "respondent_role": profile.respondent_role or "—",
        "population": services.get("population"),
        "locality_type": services.get("locality_type") or "—",
        "school_available": bool(profile.school_available),
        "nearest_school_distance_km": (
            float(profile.nearest_school_distance_km)
            if profile.nearest_school_distance_km is not None else None
        ),
        "has_committee": bool(profile.has_child_protection_committee),
        "committee_members": [n for n in member_names if n],
        "services_present": present,
        "services_absent": absent,
        "schools": profile.schools or [],
        "risks_identified": profile.risks_identified or [],
        "notes": profile.notes,
    }


def generate_fichea_pdf(context: dict) -> bytes:
    """Genere le PDF Fiche A via WeasyPrint avec fallback minimal."""
    template = _jinja_env.get_template("ssrte_fichea_report.html")
    html_content = template.render(**context)
    try:
        from weasyprint import HTML  # import differe
        return HTML(string=html_content).write_pdf()
    except (ImportError, OSError):
        return _generate_fichea_fallback_pdf(context)


def _generate_fichea_fallback_pdf(context: dict) -> bytes:
    """PDF minimal sans dependance native (tests / Windows sans Cairo)."""
    lines = [
        "SSRTE Fiche A - Profil localite",
        f"Localite : {_pdf_escape(context['locality'])}",
        f"Section : {_pdf_escape(context['section'])}",
        f"Date visite : {_pdf_escape(context['interview_date'])}",
        f"Population : {context.get('population') or '-'}",
        f"Ecole disponible : {'Oui' if context['school_available'] else 'Non'}",
        f"Comite protection enfant : {'Oui' if context['has_committee'] else 'Non'}",
        f"Ecoles recensees : {len(context.get('schools') or [])}",
        f"Services presents : {len(context.get('services_present') or [])}",
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


def fichea_filename(profile: SsrteCommunityProfile) -> str:
    """Nom de fichier Fiche A PDF normalise."""
    date_str = profile.interview_date.isoformat() if profile.interview_date else datetime.date.today().isoformat()
    return f"FicheA_{slugify(profile.locality or 'localite')}_{date_str}.pdf"
