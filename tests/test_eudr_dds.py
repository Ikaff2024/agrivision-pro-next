"""Tests pour la generation DDS PDF EUDR-01c."""
import json
import sys
import types
from datetime import datetime, timedelta

import pytest

from app.auth.auth_service import create_access_token
from app.db.models import (
    Cooperative,
    DeforestationCheck,
    Inspection,
    Plantation,
    PlantationBoundary,
    Producer,
    User,
)
from app.services.eudr_reports import (
    build_dds_context,
    dds_filename,
    generate_dds_pdf,
)
from tests.conftest import TestingSessionLocal


VALID_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[[-6.59, 5.78], [-6.58, 5.78], [-6.58, 5.79], [-6.59, 5.79], [-6.59, 5.78]]],
})


@pytest.fixture
def mock_weasyprint(monkeypatch):
    """Mock WeasyPrint pour ne pas dependre de Cairo/Pango en CI."""
    class MockHTML:
        last_html = ""
        def __init__(self, string="", **kwargs):
            self.string = string
            MockHTML.last_html = string
        def write_pdf(self):
            return b"%PDF-1.4\n%mock-eudr-dds-pdf\n%%EOF"
    fake = types.ModuleType("weasyprint")
    fake.HTML = MockHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake)
    return MockHTML


def _seed(role="admin", with_polygon=True, with_inspection=True, with_deforestation=True):
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop DDS", country="CI"); db.add(coop); db.flush()
        user = User(email=f"{role}.dds@test.ci", password_hash="x", role=role, cooperative_id=coop.id)
        producer = Producer(cooperative_id=coop.id, nom_complet="Yeo Issa", code_yeyasso="YEY-0001", is_active=True)
        db.add_all([user, producer]); db.flush()
        p = Plantation(
            name="Parcelle Test DDS", owner_name="Yeo Issa", country="CI", region="Soubre",
            latitude=5.785, longitude=-6.585, hectares=1.0,
            cooperative_id=coop.id, producer_id=producer.id,
        )
        db.add(p); db.flush()
        if with_polygon:
            db.add(PlantationBoundary(
                plantation_id=p.id, geojson=VALID_POLYGON, area_hectares=1.05,
                points_count=5, method="manual",
            ))
        if with_inspection:
            db.add(Inspection(plantation_id=p.id, type="EXTERNE",
                              date=datetime.utcnow() - timedelta(days=45)))
        if with_deforestation:
            db.add(DeforestationCheck(plantation_id=p.id, verdict="clear",
                                      source="manual", check_date=datetime.utcnow()))
        db.commit()
        return p.id, {"Authorization": "Bearer " + create_access_token({
            "sub": user.email, "role": user.role, "coop_id": user.cooperative_id,
        })}
    finally:
        db.close()


# ----------------------------------------------------------------------------
# build_dds_context
# ----------------------------------------------------------------------------

def test_build_dds_context_has_required_fields(client):
    pid, _ = _seed()
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        ctx = build_dds_context(p, db)
        assert "dds_reference" in ctx
        assert ctx["dds_reference"].startswith("DDS-")
        assert ctx["plantation"].id == pid
        assert ctx["score"] == 6  # plantation parfaite (6 regles avec EUDR-01b)
        assert ctx["status"] == "conforme"
        assert len(ctx["rules"]) == 6
        assert ctx["cooperative_name"] == "Coop DDS"
        assert ctx["producer_code"] == "YEY-0001"
        assert ctx["polygon_geojson"] is not None
        assert ctx["last_inspection_date"] is not None
    finally:
        db.close()


def test_build_dds_context_with_custom_operator(client):
    pid, _ = _seed()
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        ctx = build_dds_context(p, db, operator_name="Exportateur SACO SA")
        assert ctx["operator_name"] == "Exportateur SACO SA"
    finally:
        db.close()


def test_build_dds_context_without_polygon(client):
    pid, _ = _seed(with_polygon=False)
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        ctx = build_dds_context(p, db)
        assert ctx["polygon_geojson"] is None
        assert ctx["status"] in ("a_verifier", "non_conforme")
    finally:
        db.close()


# ----------------------------------------------------------------------------
# PDF generation (avec mock WeasyPrint)
# ----------------------------------------------------------------------------

def test_generate_pdf_with_weasyprint(client, mock_weasyprint):
    pid, _ = _seed()
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        ctx = build_dds_context(p, db)
        pdf = generate_dds_pdf(ctx)
        assert pdf.startswith(b"%PDF-")
        # Verifie que le template a bien rendu certains champs
        html = mock_weasyprint.last_html
        assert "Parcelle Test DDS" in html
        assert ctx["dds_reference"] in html
        assert "CONFORME" in html  # statut conforme attendu
        assert "Coop DDS" in html
        assert "YEY-0001" in html
    finally:
        db.close()


def test_generate_pdf_fallback_without_weasyprint(client, monkeypatch):
    """Sans weasyprint, on a un PDF minimal qui commence par %PDF-."""
    pid, _ = _seed()
    # Force ImportError sur weasyprint
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    db = TestingSessionLocal()
    try:
        p = db.query(Plantation).filter(Plantation.id == pid).first()
        ctx = build_dds_context(p, db)
        pdf = generate_dds_pdf(ctx)
        assert pdf.startswith(b"%PDF-")
        assert b"EUDR Due Diligence Statement" in pdf
        assert b"%%EOF" in pdf
    finally:
        db.close()


def test_dds_filename_format(client):
    db = TestingSessionLocal()
    try:
        p = Plantation(name="Cote d'Ivoire Parcelle 42", owner_name="X", country="CI")
        db.add(p); db.commit(); db.refresh(p)
        name = dds_filename(p)
        assert name.startswith("DDS_")
        assert name.endswith(".pdf")
        assert "Cote" in name or "cote" in name.lower()
    finally:
        db.close()


# ----------------------------------------------------------------------------
# Endpoint /plantations/{id}/eudr-dds.pdf
# ----------------------------------------------------------------------------

def test_eudr_dds_endpoint_admin(client, mock_weasyprint):
    pid, auth = _seed("admin")
    r = client.get(f"/plantations/{pid}/eudr-dds.pdf", headers=auth)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert ".pdf" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF-")


def test_eudr_dds_endpoint_with_operator_param(client, mock_weasyprint):
    pid, auth = _seed("admin")
    r = client.get(f"/plantations/{pid}/eudr-dds.pdf?operator=SACO%20SA", headers=auth)
    assert r.status_code == 200
    assert "SACO SA" in mock_weasyprint.last_html


def test_eudr_dds_endpoint_agronomist_allowed(client, mock_weasyprint):
    pid, auth = _seed("agronomist")
    r = client.get(f"/plantations/{pid}/eudr-dds.pdf", headers=auth)
    assert r.status_code == 200


def test_eudr_dds_endpoint_technician_forbidden(client, mock_weasyprint):
    pid, auth = _seed("technician")
    r = client.get(f"/plantations/{pid}/eudr-dds.pdf", headers=auth)
    assert r.status_code == 403


def test_eudr_dds_endpoint_unknown_plantation(client, mock_weasyprint):
    pid, auth = _seed("admin")
    r = client.get("/plantations/99999/eudr-dds.pdf", headers=auth)
    assert r.status_code == 404


def test_eudr_dds_endpoint_requires_auth(client, mock_weasyprint):
    pid, _ = _seed("admin")
    r = client.get(f"/plantations/{pid}/eudr-dds.pdf")
    assert r.status_code == 401
