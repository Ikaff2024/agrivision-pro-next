"""
tests/test_reports.py — Tests d'intégration de l'endpoint /plantations/{id}/report.pdf

Stratégie : on mock WeasyPrint via sys.modules pour ne pas requérir
l'installation de Cairo/Pango sur la machine de dev (Windows). Le vrai
rendu PDF est validé en environnement Railway (Linux + libs système).

Stratégie fixtures (alignée sur la logique métier d'AgriVision) :
  - Le 1er user d'une coopérative est TOUJOURS auto-promu "admin" (fondateur)
  - Pour créer un user agronomist/technician dans la MÊME coop que le admin
    de fixture, on register sur la coop EXISTANTE avec un rôle non-admin
    (ce que la logique métier autorise)
  - Le rôle "viewer" n'existe pas dans VALID_ROLES, donc pas testé ici
"""
import sys
import types
import pytest


# ─── Mock global de WeasyPrint ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_weasyprint(monkeypatch):
    """
    Injecte un faux module 'weasyprint' avant tout import.
    Le module reports.py importe 'from weasyprint import HTML' à l'intérieur
    de generate_plantation_pdf(), donc il suffit que sys.modules['weasyprint']
    existe au moment de l'appel.
    """
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


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _login(client, email, password="testpass123"):
    """Login et retourne les headers Authorization."""
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login échoué pour {email}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(client, email, role, coop_name, password="testpass123"):
    """
    Register conforme à la logique métier :
    - Si la coop n'existe pas → l'user est auto-promu admin (peu importe le rôle demandé)
    - Si la coop existe → le rôle demandé est respecté (sauf "admin" → 403)
    """
    r = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "role": role,
        "cooperative_name": coop_name,
        "country": "Côte d'Ivoire",
    })
    assert r.status_code == 201, f"Register {email} ({role}) échoué: {r.text}"
    return r.json()


# ─── Fixtures users de la même coopérative ────────────────────────────────────
@pytest.fixture
def agronomist_in_same_coop(client, auth_headers):
    """
    Crée un agronomist dans la coopérative "Coop Test Fixture" (créée par auth_headers).
    auth_headers est demandé pour s'assurer que la coop existe AVANT le register.
    """
    _register(client, "agro@fixture.ci", "agronomist", "Coop Test Fixture")
    return _login(client, "agro@fixture.ci")


@pytest.fixture
def technician_in_same_coop(client, auth_headers):
    """Technicien dans la même coop que le admin de fixture."""
    _register(client, "tech@fixture.ci", "technician", "Coop Test Fixture")
    return _login(client, "tech@fixture.ci")


@pytest.fixture
def admin_other_coop(client):
    """
    Admin d'une coopérative DIFFÉRENTE (auto-promu fondateur).
    Pas de dépendance à auth_headers : on crée une coop toute neuve.
    """
    _register(client, "other_admin@fixture.ci", "admin", "Autre Coop Independante")
    return _login(client, "other_admin@fixture.ci")


# ─── Tests ────────────────────────────────────────────────────────────────────
class TestReportPdfGeneration:

    def test_admin_can_generate_report(self, client, auth_headers, plantation_id):
        """Un admin de la coopérative peut générer le PDF."""
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=auth_headers,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF"), "Le contenu doit etre un PDF binaire"
        assert b"%%EOF" in r.content
        cd = r.headers.get("content-disposition", "")
        assert "Rapport_Plantation" in cd
        assert ".pdf" in cd

    def test_agronomist_can_generate_report(
        self, client, agronomist_in_same_coop, plantation_id
    ):
        """Un agronomist de la même coop peut générer le PDF."""
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=agronomist_in_same_coop,
        )
        assert r.status_code == 200, f"Agronomist devrait pouvoir generer: {r.text}"
        assert r.content.startswith(b"%PDF")

    def test_technician_forbidden(
        self, client, technician_in_same_coop, plantation_id
    ):
        """Un technician ne peut PAS générer le PDF (rôle insuffisant)."""
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=technician_in_same_coop,
        )
        assert r.status_code == 403, f"Technician devrait etre 403, got {r.status_code}"

    def test_admin_other_coop_cannot_access(
        self, client, admin_other_coop, plantation_id
    ):
        """Un admin d'une AUTRE coop ne doit pas accéder (multi-tenant)."""
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=admin_other_coop,
        )
        # 404 pour ne pas leak l'existence de la plantation
        assert r.status_code in (403, 404), \
            f"Cross-coop devrait etre 403 ou 404, got {r.status_code}"

    def test_plantation_not_found(self, client, auth_headers):
        """Plantation inexistante → 404."""
        r = client.get(
            "/plantations/999999/report.pdf",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_unauthenticated_request_rejected(self, client, plantation_id):
        """Sans token → 401 ou 403."""
        r = client.get(f"/plantations/{plantation_id}/report.pdf")
        assert r.status_code in (401, 403)

    def test_report_renders_plantation_name_in_html(
        self, client, auth_headers, plantation_id, mock_weasyprint
    ):
        """Le HTML rendu doit contenir le nom de la plantation et le branding."""
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=auth_headers,
        )
        assert r.status_code == 200
        html = mock_weasyprint.last_html
        assert "Plantation Test Fixture" in html, \
            "Le HTML genere doit contenir le nom de la plantation"
        assert "AgriVision Pro" in html, "Le HTML doit contenir le branding"

    def test_report_handles_plantation_without_diagnostic(
        self, client, auth_headers, plantation_id, mock_weasyprint
    ):
        """
        Robustesse : une plantation sans diagnostic ne doit PAS faire crasher
        la génération. Le PDF doit s'afficher avec un état 'aucun diagnostic'.
        """
        r = client.get(
            f"/plantations/{plantation_id}/report.pdf",
            headers=auth_headers,
        )
        assert r.status_code == 200, \
            f"Plantation sans diagnostic ne doit pas crasher: {r.text}"
        html = mock_weasyprint.last_html
        assert "Aucun diagnostic" in html or "—" in html
