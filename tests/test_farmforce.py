import pytest

from app.db.models import Cooperative, Producer, User
from app.auth.auth_service import create_access_token
from app.importers.farmforce_excel import parse_farmforce_excel
from tests.conftest import TestingSessionLocal
from tests.fixtures.generate_farmforce_workbook import (
    COOPERATIVE_NAME,
    LOCALITE,
    PRODUCER_CODE,
    PRODUCER_NAME,
    PR_CODE,
    TOTAL_COST,
    TOTAL_HOUSEHOLD_EXPENSES,
    TOTAL_REVENUE,
    build_farmforce_workbook,
)


def _admin_headers(email="farmforce.admin@test.ci"):
    """En-têtes d'auth de l'admin de 'Coop FarmForce' (créé si absent).

    Le livret (revenus du ménage) est une donnée sensible : tous les endpoints
    FarmForce exigent désormais une authentification + cloisonnement coopérative.
    """
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            coop = db.query(Cooperative).filter(Cooperative.name == "Coop FarmForce").first()
            if not coop:
                coop = Cooperative(name="Coop FarmForce", country="CI")
                db.add(coop)
                db.flush()
            user = User(email=email, password_hash="x", role="admin",
                        cooperative=coop, is_active=True)
            db.add(user)
            db.commit()
        return {"Authorization": "Bearer " + create_access_token({
            "sub": user.email, "role": user.role, "coop_id": user.cooperative_id,
        })}
    finally:
        db.close()


def _seed_producer():
    """Crée un producteur dans 'Coop FarmForce' (même coop que _admin_headers)."""
    db = TestingSessionLocal()
    try:
        coop = db.query(Cooperative).filter(Cooperative.name == "Coop FarmForce").first()
        if not coop:
            coop = Cooperative(name="Coop FarmForce", country="CI")
            db.add(coop)
            db.flush()
        producer = Producer(
            cooperative=coop,
            nom_complet="Yao FarmForce",
            code_yeyasso="PR-001",
            localite="Zone-Test",
            is_active=True,
        )
        db.add(producer)
        db.commit()
        return producer.id
    finally:
        db.close()


def test_create_farmforce_assessment_calculates_profit(client):
    producer_id = _seed_producer()

    response = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "household_members": [
            {"name": "Yao FarmForce", "age": 45, "gender": "M", "role": "Producteur"},
        ],
        "parcels": [
            {"parcel": "P1", "crop": "Cacao", "surface_ha": 2.5, "age_years": 12},
        ],
        "revenue_items": [
            {"month": "Octobre", "product": "Cacao", "quantity": 1000, "unit_price_cfa": 1000},
            {"month": "Janvier", "product": "Cafe", "quantity": 100, "unit_price_cfa": 800},
        ],
        "cost_items": [
            {"category": "Intrant", "product": "Engrais", "cost_cfa": 120000},
        ],
        "family_labor_items": [
            {"month": "Octobre", "producer_days": 10, "spouse_days": 5, "other_family_days": 5},
        ],
        "hired_labor_items": [
            {"month": "Octobre", "workers": 2, "days_per_worker": 4, "daily_wage_cfa": 3000},
        ],
    }, headers=_admin_headers())

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["producer_name"] == "Yao FarmForce"
    assert data["total_revenue_cfa"] == 1080000
    assert data["total_cost_cfa"] == 144000
    assert data["profit_cfa"] == 936000
    assert data["family_labor_days"] == 20
    assert data["hired_labor_days"] == 8
    assert data["return_per_family_day_cfa"] == 46800


def test_farmforce_net_income_subtracts_household_expenses(client):
    producer_id = _seed_producer()
    response = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 1000, "unit_price_cfa": 1000}],
        "cost_items": [{"product": "Engrais", "cost_cfa": 200000}],
        "food_security_items": [{"product": "Manioc", "market_value_cfa": 50000}],
        "household_expense_items": [
            {"category": "Alimentation", "amount_cfa": 300000},
            {"category": "Education", "amount_cfa": 100000},
        ],
    }, headers=_admin_headers())
    assert response.status_code == 200, response.text
    data = response.json()
    # revenu = 1 000 000 (cacao) + 50 000 (vivrier) = 1 050 000
    assert data["total_revenue_cfa"] == 1050000
    assert data["total_cost_cfa"] == 200000
    assert data["profit_cfa"] == 850000
    assert data["total_household_expenses_cfa"] == 400000
    assert data["net_income_cfa"] == 450000  # 850000 - 400000


def test_farmforce_update_assessment(client):
    producer_id = _seed_producer()
    h = _admin_headers()
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }, headers=h).json()
    aid = created["id"]
    assert created["profit_cfa"] == 100000

    updated = client.put(f"/farmforce/assessments/{aid}", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 200, "unit_price_cfa": 1000}],
        "household_expense_items": [{"category": "Sante", "amount_cfa": 50000}],
    }, headers=h)
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["id"] == aid                # meme enregistrement
    assert body["profit_cfa"] == 200000     # recalcule
    assert body["net_income_cfa"] == 150000 # 200000 - 50000

    # Pas de doublon : toujours 1 seul livret pour ce producteur.
    listing = client.get(f"/farmforce/assessments?producer_id={producer_id}", headers=h).json()
    assert len(listing) == 1


def test_farmforce_living_income_verdict(client):
    """Le verdict revenu vital compare le revenu net au seuil de reference."""
    producer_id = _seed_producer()
    h = _admin_headers()
    # Revenu net eleve -> atteint
    high = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 5000, "unit_price_cfa": 1000}],
    }, headers=h).json()
    assert high["living_income_benchmark_cfa"] is not None
    assert high["living_income_status"] == "atteint"  # 5 000 000 > seuil
    assert high["living_income_gap_cfa"] > 0

    # Revenu net faible -> ecart
    low = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }, headers=h).json()
    assert low["living_income_status"] == "ecart"  # 100 000 < seuil
    assert low["living_income_gap_cfa"] < 0


def test_farmforce_livret_pdf_download(client):
    producer_id = _seed_producer()
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
        "household_expense_items": [{"category": "Alimentation", "amount_cfa": 20000}],
    }, headers=_admin_headers()).json()
    r = client.get(f"/farmforce/assessments/{created['id']}/livret.pdf", headers=_admin_headers())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "Livret_" in r.headers.get("content-disposition", "")


def test_farmforce_livret_pdf_not_found(client):
    r = client.get("/farmforce/assessments/99999/livret.pdf", headers=_admin_headers())
    assert r.status_code == 404


def test_farmforce_livret_requires_auth_and_coop_isolation(client):
    """Cloisonnement : le livret (revenus du ménage) exige une auth valide et reste invisible aux autres coops."""
    producer_id = _seed_producer()  # Coop FarmForce
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }, headers=_admin_headers()).json()
    url = f"/farmforce/assessments/{created['id']}/livret.pdf"

    # Sans authentification → refusé
    assert client.get(url).status_code in (401, 403)

    # Authentifié sur une AUTRE coopérative → invisible (404)
    db = TestingSessionLocal()
    try:
        other = Cooperative(name="Autre Coop FF", country="CI")
        other_user = User(email="autre.ff@test.ci", password_hash="x",
                          role="admin", cooperative=other, is_active=True)
        db.add_all([other, other_user])
        db.commit()
        other_headers = {"Authorization": "Bearer " + create_access_token({
            "sub": other_user.email, "role": other_user.role, "coop_id": other_user.cooperative_id,
        })}
    finally:
        db.close()
    assert client.get(url, headers=other_headers).status_code == 404

    # L'admin de la coopérative propriétaire → accès OK
    assert client.get(url, headers=_admin_headers()).status_code == 200


def test_farmforce_assessments_require_auth(client):
    """Sans jeton, AUCUNE donnée de livret ne fuite (ni liste, ni résumé, ni détail)."""
    producer_id = _seed_producer()
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }, headers=_admin_headers()).json()

    assert client.get("/farmforce/assessments").status_code in (401, 403)
    assert client.get("/farmforce/summary").status_code in (401, 403)
    assert client.get(f"/farmforce/assessments/{created['id']}").status_code in (401, 403)
    assert client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
    }).status_code in (401, 403)


def test_farmforce_cross_coop_create_rejected(client):
    """Un utilisateur ne peut pas créer de livret pour le producteur d'une autre coop."""
    producer_id = _seed_producer()  # Coop FarmForce
    # Admin d'une autre coopérative
    db = TestingSessionLocal()
    try:
        other = Cooperative(name="Autre Coop Create", country="CI")
        ou = User(email="autre.create@test.ci", password_hash="x",
                  role="admin", cooperative=other, is_active=True)
        db.add_all([other, ou])
        db.commit()
        other_headers = {"Authorization": "Bearer " + create_access_token({
            "sub": ou.email, "role": ou.role, "coop_id": ou.cooperative_id,
        })}
    finally:
        db.close()
    r = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }, headers=other_headers)
    assert r.status_code == 404


def test_farmforce_update_not_found(client):
    producer_id = _seed_producer()
    r = client.put("/farmforce/assessments/99999", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
    }, headers=_admin_headers())
    assert r.status_code == 404


def test_farmforce_summary_and_list(client):
    producer_id = _seed_producer()
    h = _admin_headers()
    response = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 10, "unit_price_cfa": 1000}],
        "cost_items": [{"product": "Machette", "cost_cfa": 2000}],
        "family_labor_items": [{"producer_days": 4}],
    }, headers=h)
    assert response.status_code == 200

    summary = client.get("/farmforce/summary", headers=h)
    assert summary.status_code == 200
    assert summary.json()["assessments"] == 1
    assert summary.json()["profit_cfa"] == 8000

    listing = client.get(f"/farmforce/assessments?producer_id={producer_id}", headers=h)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


@pytest.fixture(scope="module")
def farmforce_workbook(tmp_path_factory):
    """Classeur FarmForce synthetique, genere hors du depot.

    Remplace le classeur client qui etait versionne. Contrairement a lui — un
    gabarit vide — cette fixture est RENSEIGNEE, ce qui permet de verifier que
    le parseur extrait reellement chaque feuille.
    """
    target = tmp_path_factory.mktemp("farmforce")
    return build_farmforce_workbook(target)


def test_parse_farmforce_excel_reads_every_sheet(farmforce_workbook):
    """Compatibilite du parseur avec la structure FarmForce Fairtrade.

    Verifie les SEPT feuilles du format, pas seulement l'ouverture du fichier.
    """
    parsed = parse_farmforce_excel(str(farmforce_workbook), filename=farmforce_workbook.name)

    assert parsed.errors == []
    assert parsed.warnings == []

    # 1.profil — identification et parcelles
    assert parsed.cooperative_name == COOPERATIVE_NAME
    assert parsed.producer_name == PRODUCER_NAME
    assert parsed.producer_code == PRODUCER_CODE
    assert parsed.localite == LOCALITE
    assert parsed.campaign_label == "2025-2026"
    assert len(parsed.parcels) == 2
    assert parsed.parcels[0]["crop"] == "Cacao"
    assert parsed.parcels[0]["surface_ha"] == 2.5

    # 1.profil — composition du menage (travaillants + non travaillants)
    assert len(parsed.household_members) == 3
    assert sum(1 for m in parsed.household_members if m["works_on_farm"]) == 2

    # 2.entrees — revenus mensuels cacao + cafe + autres
    products = {item["product"] for item in parsed.revenue_items}
    assert {"Cacao", "Cafe"} <= products
    assert len(parsed.revenue_items) == 5

    # 3.couts / 4.main d'oeuvre / 5.depenses
    assert len(parsed.cost_items) == 3
    assert len(parsed.family_labor_items) == 2
    assert len(parsed.hired_labor_items) == 2
    assert {e["category"] for e in parsed.household_expenses} == {
        "alimentation", "education", "sante", "autres"
    }

    # consent signatures — tracabilite du consentement
    assert len(parsed.consent_records) == 1
    assert parsed.consent_records[0]["fairtrade_international"] is True
    assert parsed.consent_records[0]["spo"] is False

    # 6.resultats — agregats
    assert parsed.summary["total_revenue_cfa"] == TOTAL_REVENUE
    assert parsed.summary["total_cost_cfa"] == TOTAL_COST
    assert parsed.summary["household_expenses_cfa"] == TOTAL_HOUSEHOLD_EXPENSES

    # payload d'import
    payload = parsed.as_payload()
    assert "producer_id" in payload
    assert payload["pr_code"] == PR_CODE


def test_import_farmforce_excel_endpoint_creates_assessment(client, farmforce_workbook):
    producer_id = _seed_producer()

    with open(farmforce_workbook, "rb") as fh:
        response = client.post(
            f"/farmforce/import/excel?producer_id={producer_id}",
            files={"file": ("farmforce.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=_admin_headers(),
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert data["assessment"]["producer_id"] == producer_id
    # L'import doit remonter le contenu, pas seulement creer une coquille vide.
    assert data["assessment"]["total_revenue_cfa"] > 0


def _ff_auth(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_farmforce_summary_is_cooperative_scoped(client):
    """Le summary FarmForce ne doit agreger que la coop de l'utilisateur."""
    ha = _ff_auth(client, "ff.scopeA@test.ci", "FF Scope A")
    hb = _ff_auth(client, "ff.scopeB@test.ci", "FF Scope B")
    pa = client.post("/plantations", json={
        "name": "FFA", "owner_name": "FF Owner", "country": "CI", "hectares": 2,
    }, headers=ha).json()
    # Cree une evaluation FarmForce pour la coop A
    client.post("/farmforce/assessments", json={
        "producer_id": pa["producer_id"], "campaign_label": "2025-2026",
        "revenue_items": [{"label": "cacao", "amount_cfa": 500000}],
    }, headers=ha)

    sa = client.get("/farmforce/summary", headers=ha).json()
    assert sa["assessments"] >= 1
    # Coop B ne voit pas les evaluations de A
    sb = client.get("/farmforce/summary", headers=hb).json()
    assert sb["assessments"] == 0
    assert client.get("/farmforce/assessments", headers=hb).json() == []
