"""
tests/test_agroforestry_report.py — Tests de l'endpoint /agroforestry/report.pdf

Le bilan agroforestier passe d'une impression navigateur (window.print) à un
PDF brandé généré côté serveur (WeasyPrint), cohérent avec nos autres états.

Stratégie : on mock WeasyPrint via sys.modules pour ne pas requérir Cairo/Pango
sur la machine de dev (Windows), comme dans test_reports.py.
"""
import sys
import types
import pytest


# ─── Mock global de WeasyPrint ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_weasyprint(monkeypatch):
    class MockHTML:
        def __init__(self, string="", **kwargs):
            self.string = string
            MockHTML.last_html = string

        def write_pdf(self):
            return b"%PDF-1.4\n%fake-pdf-for-tests\n1 0 obj\n<<>>\nendobj\n%%EOF"

    MockHTML.last_html = ""

    fake_module = types.ModuleType("weasyprint")
    fake_module.HTML = MockHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_module)
    yield MockHTML


def _add_species(client, headers, plantation_id, species, density, age=5):
    r = client.post(
        f"/plantations/{plantation_id}/agroforestry",
        json={"species_name": species, "count_per_hectare": density, "avg_age_years": age},
        headers=headers,
    )
    assert r.status_code == 201, f"Ajout espèce échoué: {r.text}"


class TestAgroforestryReportPdf:

    def test_report_is_pdf(self, client, auth_headers, plantation_id):
        """L'endpoint renvoie bien un PDF brandé téléchargeable."""
        _add_species(client, auth_headers, plantation_id, "Gliricidia sepium", 30)
        _add_species(client, auth_headers, plantation_id, "Milicia excelsa", 12)

        r = client.get("/agroforestry/report.pdf", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
        cd = r.headers.get("content-disposition", "")
        assert "Bilan_Agroforestier" in cd
        assert ".pdf" in cd

    def test_report_html_has_brand_and_title(
        self, client, auth_headers, plantation_id, mock_weasyprint
    ):
        """Le HTML rendu contient le nom de la coopérative et le titre du bilan."""
        _add_species(client, auth_headers, plantation_id, "Mangifera indica", 20)

        r = client.get("/agroforestry/report.pdf", headers=auth_headers)
        assert r.status_code == 200
        html = mock_weasyprint.last_html
        assert "Bilan agroforestier" in html
        assert "Coop Test Fixture" in html
        # L'espèce inventoriée et sa strate doivent apparaître dans le détail
        assert "Mangifera indica" in html

    def test_report_empty_inventory_does_not_crash(
        self, client, auth_headers, plantation_id, mock_weasyprint
    ):
        """Une coopérative sans inventaire ne fait pas crasher la génération."""
        r = client.get("/agroforestry/report.pdf", headers=auth_headers)
        assert r.status_code == 200, f"Inventaire vide ne doit pas crasher: {r.text}"
        html = mock_weasyprint.last_html
        assert "Aucune espèce inventoriée" in html

    def test_unauthenticated_rejected(self, client):
        r = client.get("/agroforestry/report.pdf")
        assert r.status_code in (401, 403)
