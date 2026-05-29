from app.db.models import Cooperative, Producer
from app.importers.farmforce_excel import parse_farmforce_excel
from tests.conftest import TestingSessionLocal


def _seed_producer():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop FarmForce", country="CI")
        producer = Producer(
            cooperative=coop,
            nom_complet="Yao FarmForce",
            code_yeyasso="PR-001",
            localite="Yeyasso",
            is_active=True,
        )
        db.add_all([coop, producer])
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
    })

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
    })
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
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }).json()
    aid = created["id"]
    assert created["profit_cfa"] == 100000

    updated = client.put(f"/farmforce/assessments/{aid}", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 200, "unit_price_cfa": 1000}],
        "household_expense_items": [{"category": "Sante", "amount_cfa": 50000}],
    })
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["id"] == aid                # meme enregistrement
    assert body["profit_cfa"] == 200000     # recalcule
    assert body["net_income_cfa"] == 150000 # 200000 - 50000

    # Pas de doublon : toujours 1 seul livret pour ce producteur.
    listing = client.get(f"/farmforce/assessments?producer_id={producer_id}").json()
    assert len(listing) == 1


def test_farmforce_living_income_verdict(client):
    """Le verdict revenu vital compare le revenu net au seuil de reference."""
    producer_id = _seed_producer()
    # Revenu net eleve -> atteint
    high = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 5000, "unit_price_cfa": 1000}],
    }).json()
    assert high["living_income_benchmark_cfa"] is not None
    assert high["living_income_status"] == "atteint"  # 5 000 000 > seuil
    assert high["living_income_gap_cfa"] > 0

    # Revenu net faible -> ecart
    low = client.post("/farmforce/assessments", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
    }).json()
    assert low["living_income_status"] == "ecart"  # 100 000 < seuil
    assert low["living_income_gap_cfa"] < 0


def test_farmforce_livret_pdf_download(client):
    producer_id = _seed_producer()
    created = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 100, "unit_price_cfa": 1000}],
        "household_expense_items": [{"category": "Alimentation", "amount_cfa": 20000}],
    }).json()
    r = client.get(f"/farmforce/assessments/{created['id']}/livret.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "Livret_" in r.headers.get("content-disposition", "")


def test_farmforce_livret_pdf_not_found(client):
    r = client.get("/farmforce/assessments/99999/livret.pdf")
    assert r.status_code == 404


def test_farmforce_update_not_found(client):
    producer_id = _seed_producer()
    r = client.put("/farmforce/assessments/99999", json={
        "producer_id": producer_id, "campaign_label": "2025-2026",
    })
    assert r.status_code == 404


def test_farmforce_summary_and_list(client):
    producer_id = _seed_producer()
    response = client.post("/farmforce/assessments", json={
        "producer_id": producer_id,
        "campaign_label": "2025-2026",
        "revenue_items": [{"product": "Cacao", "quantity": 10, "unit_price_cfa": 1000}],
        "cost_items": [{"product": "Machette", "cost_cfa": 2000}],
        "family_labor_items": [{"producer_days": 4}],
    })
    assert response.status_code == 200

    summary = client.get("/farmforce/summary")
    assert summary.status_code == 200
    assert summary.json()["assessments"] == 1
    assert summary.json()["profit_cfa"] == 8000

    listing = client.get(f"/farmforce/assessments?producer_id={producer_id}")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_parse_client_farmforce_excel_template():
    parsed = parse_farmforce_excel(
        "docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx",
        filename="digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx",
    )

    assert parsed.errors == []
    assert parsed.cooperative_name == "YEYASSO"
    assert parsed.summary["total_revenue_cfa"] == 0
    assert "producer_id" in parsed.as_payload()


def test_import_farmforce_excel_endpoint_creates_assessment(client):
    producer_id = _seed_producer()

    with open("docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx", "rb") as fh:
        response = client.post(
            f"/farmforce/import/excel?producer_id={producer_id}",
            files={"file": ("farmforce.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert data["assessment"]["producer_id"] == producer_id
