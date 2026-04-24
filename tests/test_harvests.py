"""
Tests d'integration --- module Recoltes (Harvests).
Couvre : compute_season, creation, listing, filtres, stats agregees,
         modification, suppression, controle d'acces, isolation cooperative.
"""

import pytest
from datetime import datetime

from app.api.routes import compute_season


# ------ Payloads de reference ------------------------------------------------

HARVEST_BONNE = {
    "harvest_date": "2026-01-15T08:00:00",
    "quantity_kg": 850.5,
    "quality": "Bonne",
    "price_per_kg_fcfa": 1200.0,
    "notes": "Recolte grande saison",
    "is_historical": False,
}

HARVEST_MOYENNE = {
    "harvest_date": "2025-05-10T09:00:00",
    "quantity_kg": 320.0,
    "quality": "Moyenne",
    "price_per_kg_fcfa": 950.0,
    "is_historical": False,
}

HARVEST_DEFAUTS = {
    "harvest_date": "2024-11-20T07:30:00",
    "quantity_kg": 180.0,
    "quality": "Defauts",
    "is_historical": True,
}


# ------ Fixtures supplementaires ---------------------------------------------

@pytest.fixture
def agro_headers(client, auth_headers):
    """Agronome dans la meme cooperative que l'admin fixture."""
    client.post("/auth/register", json={
        "email": "agro_h@harvest.ci",
        "password": "pass123",
        "role": "agronomist",
        "cooperative_name": "Coop Test Fixture",
        "country": "Cote d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "agro_h@harvest.ci", "password": "pass123"
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tech_headers(client, auth_headers):
    """Technicien dans la meme cooperative."""
    client.post("/auth/register", json={
        "email": "tech_h@harvest.ci",
        "password": "pass123",
        "role": "technician",
        "cooperative_name": "Coop Test Fixture",
        "country": "Cote d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "tech_h@harvest.ci", "password": "pass123"
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def harvest_id(client, auth_headers, plantation_id):
    """Cree une recolte et retourne son ID."""
    res = client.post(
        f"/plantations/{plantation_id}/harvests",
        json=HARVEST_BONNE,
        headers=auth_headers,
    )
    assert res.status_code == 201, f"Fixture harvest_id echouee: {res.text}"
    return res.json()["id"]


# ============================================================================
# 1. compute_season --- tests unitaires (pas besoin de DB)
# ============================================================================

class TestComputeSeason:

    @pytest.mark.parametrize("month", [10, 11, 12, 1])
    def test_grande_saison(self, month):
        d = datetime(2026, month, 15)
        assert compute_season(d) == "grande"

    @pytest.mark.parametrize("month", [4, 5, 6])
    def test_petite_saison(self, month):
        d = datetime(2026, month, 15)
        assert compute_season(d) == "petite"

    @pytest.mark.parametrize("month", [2, 3, 7, 8, 9])
    def test_intersaison(self, month):
        d = datetime(2026, month, 15)
        assert compute_season(d) == "intersaison"

    def test_none_returns_intersaison(self):
        assert compute_season(None) == "intersaison"

    def test_accepts_int_month(self):
        """compute_season accepte aussi un entier en cas de besoin."""
        assert compute_season(10) == "grande"
        assert compute_season(5) == "petite"
        assert compute_season(3) == "intersaison"


# ============================================================================
# 2. POST /plantations/{id}/harvests --- creation
# ============================================================================

class TestCreateHarvest:

    def test_create_success_returns_201(self, client, auth_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
            headers=auth_headers,
        )
        assert res.status_code == 201

    def test_create_returns_id_and_data(self, client, auth_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
            headers=auth_headers,
        )
        data = res.json()
        assert "id" in data
        assert data["quantity_kg"] == 850.5
        assert data["quality"] == "Bonne"

    def test_create_computes_season_automatically(self, client, auth_headers, plantation_id):
        """Une recolte en janvier doit avoir season='grande'."""
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,  # date = 2026-01-15
            headers=auth_headers,
        )
        assert res.json()["season"] == "grande"

    def test_create_petite_season(self, client, auth_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_MOYENNE,  # date = 2025-05-10
            headers=auth_headers,
        )
        assert res.json()["season"] == "petite"

    def test_agronomist_can_create(self, client, agro_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
            headers=agro_headers,
        )
        assert res.status_code == 201

    def test_technician_cannot_create_403(self, client, tech_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
            headers=tech_headers,
        )
        assert res.status_code == 403

    def test_requires_auth(self, client, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
        )
        assert res.status_code == 401

    def test_unknown_plantation_returns_404(self, client, auth_headers):
        res = client.post(
            "/plantations/99999/harvests",
            json=HARVEST_BONNE,
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_invalid_quality_rejected(self, client, auth_headers, plantation_id):
        bad = {**HARVEST_BONNE, "quality": "Excellente"}  # pas dans VALID_QUALITIES
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=bad,
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_zero_quantity_rejected(self, client, auth_headers, plantation_id):
        bad = {**HARVEST_BONNE, "quantity_kg": 0.0}
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=bad,
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_negative_quantity_rejected(self, client, auth_headers, plantation_id):
        bad = {**HARVEST_BONNE, "quantity_kg": -10.0}
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=bad,
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_negative_price_rejected(self, client, auth_headers, plantation_id):
        bad = {**HARVEST_BONNE, "price_per_kg_fcfa": -100.0}
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=bad,
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_minimal_payload(self, client, auth_headers, plantation_id):
        """Seuls harvest_date, quantity_kg et quality sont obligatoires."""
        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json={
                "harvest_date": "2026-01-15T08:00:00",
                "quantity_kg": 100.0,
                "quality": "Bonne",
            },
            headers=auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["price_per_kg_fcfa"] is None
        assert data["notes"] is None
        assert data["is_historical"] is False


# ============================================================================
# 3. GET /plantations/{id}/harvests --- listing
# ============================================================================

class TestListHarvests:

    def test_empty_list_returns_200(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/harvests",
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json() == []

    def test_list_returns_created_harvest(self, client, auth_headers, plantation_id, harvest_id):
        res = client.get(
            f"/plantations/{plantation_id}/harvests",
            headers=auth_headers,
        )
        data = res.json()
        assert len(data) == 1
        assert data[0]["id"] == harvest_id

    def test_list_sorted_by_date_desc(self, client, auth_headers, plantation_id):
        # Cree 3 recoltes a des dates differentes
        for h in [HARVEST_DEFAUTS, HARVEST_BONNE, HARVEST_MOYENNE]:
            client.post(
                f"/plantations/{plantation_id}/harvests",
                json=h, headers=auth_headers,
            )
        res = client.get(
            f"/plantations/{plantation_id}/harvests",
            headers=auth_headers,
        )
        dates = [h["harvest_date"] for h in res.json()]
        # Tri decroissant : 2026-01 > 2025-05 > 2024-11
        assert dates == sorted(dates, reverse=True)

    def test_filter_by_year(self, client, auth_headers, plantation_id):
        for h in [HARVEST_BONNE, HARVEST_MOYENNE, HARVEST_DEFAUTS]:
            client.post(
                f"/plantations/{plantation_id}/harvests",
                json=h, headers=auth_headers,
            )
        res = client.get(
            f"/plantations/{plantation_id}/harvests?year=2025",
            headers=auth_headers,
        )
        data = res.json()
        assert len(data) == 1
        assert data[0]["quantity_kg"] == 320.0

    def test_filter_by_season(self, client, auth_headers, plantation_id):
        for h in [HARVEST_BONNE, HARVEST_MOYENNE]:
            client.post(
                f"/plantations/{plantation_id}/harvests",
                json=h, headers=auth_headers,
            )
        res = client.get(
            f"/plantations/{plantation_id}/harvests?season=petite",
            headers=auth_headers,
        )
        data = res.json()
        assert len(data) == 1
        assert data[0]["season"] == "petite"

    def test_invalid_season_rejected(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/harvests?season=automne",
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_requires_auth(self, client, plantation_id):
        res = client.get(f"/plantations/{plantation_id}/harvests")
        assert res.status_code == 401

    def test_unknown_plantation_returns_404(self, client, auth_headers):
        res = client.get(
            "/plantations/99999/harvests",
            headers=auth_headers,
        )
        assert res.status_code == 404


# ============================================================================
# 4. GET /plantations/{id}/harvests/stats --- statistiques agregees
# ============================================================================

class TestHarvestStats:

    def test_empty_stats_all_zeros(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/harvests/stats",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_kg_all_time"] == 0
        assert data["count_total"] == 0
        assert data["by_year"] == []

    def test_stats_total_correct(self, client, auth_headers, plantation_id):
        for h in [HARVEST_BONNE, HARVEST_MOYENNE, HARVEST_DEFAUTS]:
            client.post(
                f"/plantations/{plantation_id}/harvests",
                json=h, headers=auth_headers,
            )
        res = client.get(
            f"/plantations/{plantation_id}/harvests/stats",
            headers=auth_headers,
        )
        data = res.json()
        # 850.5 + 320 + 180 = 1350.5
        assert data["total_kg_all_time"] == 1350.5
        assert data["count_total"] == 3

    def test_stats_by_year_sorted_desc(self, client, auth_headers, plantation_id):
        for h in [HARVEST_BONNE, HARVEST_MOYENNE, HARVEST_DEFAUTS]:
            client.post(
                f"/plantations/{plantation_id}/harvests",
                json=h, headers=auth_headers,
            )
        data = client.get(
            f"/plantations/{plantation_id}/harvests/stats",
            headers=auth_headers,
        ).json()
        years = [item["year"] for item in data["by_year"]]
        assert years == [2026, 2025, 2024]

    def test_stats_by_season_for_current_year(self, client, auth_headers, plantation_id):
        # HARVEST_BONNE : 2026-01 -> grande
        client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE, headers=auth_headers,
        )
        data = client.get(
            f"/plantations/{plantation_id}/harvests/stats",
            headers=auth_headers,
        ).json()
        assert data["by_season"]["grande"] == 850.5
        assert data["by_season"]["petite"] == 0
        assert data["by_season"]["intersaison"] == 0

    def test_requires_auth(self, client, plantation_id):
        res = client.get(f"/plantations/{plantation_id}/harvests/stats")
        assert res.status_code == 401

    def test_unknown_plantation_returns_404(self, client, auth_headers):
        res = client.get(
            "/plantations/99999/harvests/stats",
            headers=auth_headers,
        )
        assert res.status_code == 404


# ============================================================================
# 5. PUT /harvests/{id} --- modification
# ============================================================================

class TestUpdateHarvest:

    def test_update_quantity_success(self, client, auth_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quantity_kg": 999.0},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["quantity_kg"] == 999.0

    def test_update_quality_success(self, client, auth_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quality": "Moyenne"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["quality"] == "Moyenne"

    def test_update_date_recomputes_season(self, client, auth_headers, harvest_id):
        """Modifier la date doit recalculer automatiquement la saison."""
        # harvest_id est en janvier (grande). On le passe en mai (petite).
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"harvest_date": "2026-05-15T08:00:00"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["season"] == "petite"

    def test_update_partial_does_not_overwrite_others(self, client, auth_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"notes": "Mise a jour"},
            headers=auth_headers,
        )
        # quantity_kg reste a 850.5
        assert res.json()["quantity_kg"] == 850.5
        assert res.json()["notes"] == "Mise a jour"

    def test_agronomist_can_update(self, client, auth_headers, agro_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quantity_kg": 500.0},
            headers=agro_headers,
        )
        assert res.status_code == 200

    def test_technician_cannot_update_403(self, client, auth_headers, tech_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quantity_kg": 500.0},
            headers=tech_headers,
        )
        assert res.status_code == 403

    def test_update_invalid_quality_rejected(self, client, auth_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quality": "Inconnue"},
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_update_negative_quantity_rejected(self, client, auth_headers, harvest_id):
        res = client.put(
            f"/harvests/{harvest_id}",
            json={"quantity_kg": -1.0},
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_update_unknown_returns_404(self, client, auth_headers):
        res = client.put(
            "/harvests/99999",
            json={"quantity_kg": 100.0},
            headers=auth_headers,
        )
        assert res.status_code == 404


# ============================================================================
# 6. DELETE /harvests/{id} --- suppression
# ============================================================================

class TestDeleteHarvest:

    def test_admin_can_delete(self, client, auth_headers, harvest_id):
        res = client.delete(
            f"/harvests/{harvest_id}",
            headers=auth_headers,
        )
        assert res.status_code == 200

    def test_delete_removes_from_list(self, client, auth_headers, plantation_id, harvest_id):
        client.delete(f"/harvests/{harvest_id}", headers=auth_headers)
        res = client.get(
            f"/plantations/{plantation_id}/harvests",
            headers=auth_headers,
        )
        assert res.json() == []

    def test_agronomist_cannot_delete_403(self, client, auth_headers, agro_headers, harvest_id):
        """Seul l'admin peut supprimer."""
        res = client.delete(
            f"/harvests/{harvest_id}",
            headers=agro_headers,
        )
        assert res.status_code == 403

    def test_technician_cannot_delete_403(self, client, auth_headers, tech_headers, harvest_id):
        res = client.delete(
            f"/harvests/{harvest_id}",
            headers=tech_headers,
        )
        assert res.status_code == 403

    def test_delete_unknown_returns_404(self, client, auth_headers):
        res = client.delete("/harvests/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_requires_auth(self, client, harvest_id):
        res = client.delete(f"/harvests/{harvest_id}")
        assert res.status_code == 401


# ============================================================================
# 7. Isolation entre cooperatives
# ============================================================================

class TestHarvestCooperativeIsolation:

    def test_coop_b_cannot_see_coop_a_harvests(self, client, auth_headers, plantation_id, harvest_id):
        """Coop B ne peut pas voir les recoltes de Coop A."""
        client.post("/auth/register", json={
            "email": "admin_h_b@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop H Isolee B", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_h_b@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        res = client.get(
            f"/plantations/{plantation_id}/harvests",
            headers=headers_b,
        )
        assert res.status_code == 404

    def test_coop_b_cannot_create_in_coop_a_plantation(self, client, auth_headers, plantation_id):
        """Coop B ne peut pas creer une recolte dans une plantation de Coop A."""
        client.post("/auth/register", json={
            "email": "admin_h_c@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop H Isolee C", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_h_c@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        res = client.post(
            f"/plantations/{plantation_id}/harvests",
            json=HARVEST_BONNE,
            headers=headers_b,
        )
        assert res.status_code == 404

    def test_coop_b_cannot_delete_coop_a_harvest(self, client, auth_headers, harvest_id):
        """Coop B ne peut pas supprimer une recolte de Coop A."""
        client.post("/auth/register", json={
            "email": "admin_h_d@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop H Isolee D", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_h_d@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        res = client.delete(
            f"/harvests/{harvest_id}",
            headers=headers_b,
        )
        assert res.status_code == 404
