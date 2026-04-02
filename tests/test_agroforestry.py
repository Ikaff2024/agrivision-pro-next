"""
Tests d'intégration — module Agroforesterie
Couvre : bibliothèque espèces, inventaire, métriques, suppression, bilan coopérative,
         contrôle d'accès, isolation coopérative.
"""

import pytest

# ─── Payloads de référence ─────────────────────────────────────────────────────

BANANIER = {
    "species_name": "Musa spp.",
    "local_name": "Bananier",
    "layer": "understory",
    "count_per_hectare": 20.0,
    "avg_age_years": 5.0,
    "notes": "Test",
}

GLIRICIDI = {
    "species_name": "Gliricidia sepium",
    "local_name": "Gliricidi",
    "layer": "intermediate",
    "count_per_hectare": 15.0,
    "avg_age_years": 8.0,
}

MANGUIER = {
    "species_name": "Mangifera indica",
    "local_name": "Manguier",
    "layer": "superior",
    "count_per_hectare": 10.0,
    "avg_age_years": 12.0,
}


# ─── Fixture : token agronome dans la même coop ───────────────────────────────

@pytest.fixture
def agro_headers(client, auth_headers):
    """Agronome dans la même coopérative que l'admin fixture."""
    client.post("/auth/register", json={
        "email": "agro@agro.ci",
        "password": "pass123",
        "role": "agronomist",
        "cooperative_name": "Coop Test Fixture",
        "country": "Côte d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "agro@agro.ci", "password": "pass123"
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tech_headers(client, auth_headers):
    """Technicien dans la même coopérative."""
    client.post("/auth/register", json={
        "email": "tech@agro.ci",
        "password": "pass123",
        "role": "technician",
        "cooperative_name": "Coop Test Fixture",
        "country": "Côte d'Ivoire",
    })
    token = client.post("/auth/login", json={
        "email": "tech@agro.ci", "password": "pass123"
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def record_id(client, auth_headers, plantation_id):
    """Crée un enregistrement agroforestier et retourne son ID."""
    res = client.post(
        f"/plantations/{plantation_id}/agroforestry",
        json=BANANIER,
        headers=auth_headers,
    )
    assert res.status_code == 201, f"Fixture record_id échouée: {res.text}"
    return res.json()["id"]


# ════════════════════════════════════════════════════════════════════════════════
# 1. Bibliothèque d'espèces
# ════════════════════════════════════════════════════════════════════════════════

class TestSpeciesLibrary:

    def test_returns_list(self, client, auth_headers):
        res = client.get("/species-library", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_not_empty(self, client, auth_headers):
        res = client.get("/species-library", headers=auth_headers)
        assert len(res.json()) >= 10

    def test_required_fields_present(self, client, auth_headers):
        res = client.get("/species-library", headers=auth_headers)
        for species in res.json():
            assert "name" in species
            assert "local" in species
            assert "layer" in species
            assert "carbon_factor" in species
            assert "shade_factor" in species
            assert "category" in species

    def test_carbon_factors_positive(self, client, auth_headers):
        res = client.get("/species-library", headers=auth_headers)
        for species in res.json():
            assert species["carbon_factor"] > 0, (
                f"{species['name']}: carbon_factor doit être > 0"
            )

    def test_shade_factors_between_0_and_1(self, client, auth_headers):
        res = client.get("/species-library", headers=auth_headers)
        for species in res.json():
            assert 0 < species["shade_factor"] <= 1.0, (
                f"{species['name']}: shade_factor hors bornes"
            )

    def test_requires_auth(self, client):
        res = client.get("/species-library")
        assert res.status_code == 401


# ════════════════════════════════════════════════════════════════════════════════
# 2. Ajout d'espèces (POST)
# ════════════════════════════════════════════════════════════════════════════════

class TestAddAgroforestryRecord:

    def test_add_success_returns_201(self, client, auth_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER,
            headers=auth_headers,
        )
        assert res.status_code == 201

    def test_add_returns_id(self, client, auth_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER,
            headers=auth_headers,
        )
        assert "id" in res.json()
        assert isinstance(res.json()["id"], int)

    def test_agronomist_can_add(self, client, agro_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=GLIRICIDI,
            headers=agro_headers,
        )
        assert res.status_code == 201

    def test_technician_cannot_add_403(self, client, tech_headers, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER,
            headers=tech_headers,
        )
        assert res.status_code == 403

    def test_requires_auth(self, client, plantation_id):
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER,
        )
        assert res.status_code == 401

    def test_unknown_plantation_returns_404(self, client, auth_headers):
        res = client.post(
            "/plantations/99999/agroforestry",
            json=BANANIER,
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_minimal_payload_no_optional_fields(self, client, auth_headers, plantation_id):
        """Seuls species_name et count_per_hectare sont obligatoires."""
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json={"species_name": "Acacia sp.", "count_per_hectare": 5.0},
            headers=auth_headers,
        )
        assert res.status_code == 201

    def test_negative_density_rejected(self, client, auth_headers, plantation_id):
        bad = {**BANANIER, "count_per_hectare": -5.0}
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=bad,
            headers=auth_headers,
        )
        # FastAPI retourne 422 pour violation de contrainte Pydantic
        assert res.status_code in (400, 422)

    def test_zero_density_rejected(self, client, auth_headers, plantation_id):
        bad = {**BANANIER, "count_per_hectare": 0.0}
        res = client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=bad,
            headers=auth_headers,
        )
        assert res.status_code in (400, 422)


# ════════════════════════════════════════════════════════════════════════════════
# 3. Consultation de l'inventaire (GET)
# ════════════════════════════════════════════════════════════════════════════════

class TestGetInventory:

    def test_empty_inventory_returns_200(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["records"] == []

    def test_empty_metrics_all_zero(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        m = res.json()["metrics"]
        assert m["shade_score"] == 0
        assert m["diversity_score"] == 0
        assert m["carbon_stock_tco2_ha"] == 0.0
        assert m["conformity_score"] == 0
        assert m["species_count"] == 0

    def test_response_structure(self, client, auth_headers, plantation_id):
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        data = res.json()
        assert "plantation_id" in data
        assert "plantation_name" in data
        assert "records" in data
        assert "metrics" in data

    def test_metrics_keys_present(self, client, auth_headers, plantation_id, record_id):
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        m = res.json()["metrics"]
        required_keys = {
            "shade_score", "diversity_score", "carbon_stock_tco2_ha",
            "carbon_score", "conformity_score", "total_trees_per_ha", "species_count"
        }
        assert required_keys.issubset(set(m.keys()))

    def test_record_appears_after_add(self, client, auth_headers, plantation_id):
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER,
            headers=auth_headers,
        )
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        records = res.json()["records"]
        assert len(records) == 1
        assert records[0]["species_name"] == "Musa spp."
        assert records[0]["count_per_hectare"] == 20.0

    def test_multiple_species_all_returned(self, client, auth_headers, plantation_id):
        for species in [BANANIER, GLIRICIDI, MANGUIER]:
            client.post(
                f"/plantations/{plantation_id}/agroforestry",
                json=species,
                headers=auth_headers,
            )
        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        )
        assert len(res.json()["records"]) == 3

    def test_unknown_plantation_returns_404(self, client, auth_headers):
        res = client.get(
            "/plantations/99999/agroforestry",
            headers=auth_headers,
        )
        assert res.status_code == 404

    def test_requires_auth(self, client, plantation_id):
        res = client.get(f"/plantations/{plantation_id}/agroforestry")
        assert res.status_code == 401


# ════════════════════════════════════════════════════════════════════════════════
# 4. Calcul des métriques
# ════════════════════════════════════════════════════════════════════════════════

class TestMetricsCalculation:

    def test_shade_score_increases_with_density(self, client, auth_headers, plantation_id):
        """Plus la densité est élevée, plus le score ombrage est élevé."""
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json={**GLIRICIDI, "count_per_hectare": 5.0},
            headers=auth_headers,
        )
        res_low = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["shade_score"]

        # Nouvelle plantation avec densité élevée
        res2 = client.post("/plantations", json={
            "name": "P Dense", "owner_name": "Test", "country": "CI"
        }, headers=auth_headers)
        pid2 = res2.json()["id"]
        client.post(
            f"/plantations/{pid2}/agroforestry",
            json={**GLIRICIDI, "count_per_hectare": 40.0},
            headers=auth_headers,
        )
        res_high = client.get(
            f"/plantations/{pid2}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["shade_score"]

        assert res_high > res_low

    def test_diversity_score_increases_with_species_count(
        self, client, auth_headers, plantation_id
    ):
        """Plus d'espèces → score diversité plus élevé."""
        # 1 espèce
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER, headers=auth_headers,
        )
        score_1 = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["diversity_score"]

        # 2 espèces
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=GLIRICIDI, headers=auth_headers,
        )
        score_2 = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["diversity_score"]

        assert score_2 > score_1

    def test_carbon_stock_positive_after_add(self, client, auth_headers, plantation_id):
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=MANGUIER, headers=auth_headers,
        )
        m = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]
        assert m["carbon_stock_tco2_ha"] > 0.0

    def test_total_trees_matches_sum_of_densities(self, client, auth_headers, plantation_id):
        for species in [BANANIER, GLIRICIDI]:
            client.post(
                f"/plantations/{plantation_id}/agroforestry",
                json=species, headers=auth_headers,
            )
        m = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]
        expected = BANANIER["count_per_hectare"] + GLIRICIDI["count_per_hectare"]
        assert m["total_trees_per_ha"] == pytest.approx(expected, abs=0.1)

    def test_scores_between_0_and_100(self, client, auth_headers, plantation_id):
        """Toutes les métriques doivent être dans [0, 100]."""
        for species in [BANANIER, GLIRICIDI, MANGUIER]:
            client.post(
                f"/plantations/{plantation_id}/agroforestry",
                json=species, headers=auth_headers,
            )
        m = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]

        for key in ["shade_score", "diversity_score", "carbon_score", "conformity_score"]:
            assert 0 <= m[key] <= 100, f"{key}={m[key]} hors bornes [0, 100]"

    def test_conformity_is_weighted_combination(self, client, auth_headers, plantation_id):
        """
        Conformité = ombrage×0.4 + diversité×0.3 + carbone×0.3.
        Vérifie que le score est cohérent (non nul si les composantes sont non nulles).
        """
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json={**GLIRICIDI, "count_per_hectare": 30.0},
            headers=auth_headers,
        )
        m = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]

        # Si ombrage > 0, le score de conformité doit être > 0
        assert m["shade_score"] > 0
        assert m["conformity_score"] > 0

    def test_older_trees_produce_more_carbon(self, client, auth_headers, plantation_id):
        """Un arbre plus vieux doit générer plus de carbone (age_factor)."""
        pid_young = plantation_id
        client.post(
            f"/plantations/{pid_young}/agroforestry",
            json={**MANGUIER, "avg_age_years": 2.0},
            headers=auth_headers,
        )
        carbon_young = client.get(
            f"/plantations/{pid_young}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["carbon_stock_tco2_ha"]

        # Nouvelle plantation avec arbres âgés
        pid_old = client.post("/plantations", json={
            "name": "P Old", "owner_name": "Test", "country": "CI"
        }, headers=auth_headers).json()["id"]
        client.post(
            f"/plantations/{pid_old}/agroforestry",
            json={**MANGUIER, "avg_age_years": 25.0},
            headers=auth_headers,
        )
        carbon_old = client.get(
            f"/plantations/{pid_old}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]["carbon_stock_tco2_ha"]

        assert carbon_old > carbon_young


# ════════════════════════════════════════════════════════════════════════════════
# 5. Suppression d'enregistrement (DELETE)
# ════════════════════════════════════════════════════════════════════════════════

class TestDeleteAgroforestryRecord:

    def test_delete_success(self, client, auth_headers, plantation_id, record_id):
        res = client.delete(
            f"/agroforestry/{record_id}",
            headers=auth_headers,
        )
        assert res.status_code == 200

    def test_delete_removes_from_inventory(
        self, client, auth_headers, plantation_id, record_id
    ):
        client.delete(f"/agroforestry/{record_id}", headers=auth_headers)
        records = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["records"]
        assert all(r["id"] != record_id for r in records)

    def test_delete_resets_metrics_to_zero(
        self, client, auth_headers, plantation_id, record_id
    ):
        """Supprimer le seul enregistrement → métriques reviennent à 0."""
        client.delete(f"/agroforestry/{record_id}", headers=auth_headers)
        m = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=auth_headers,
        ).json()["metrics"]
        assert m["conformity_score"] == 0
        assert m["species_count"] == 0

    def test_delete_nonexistent_record_returns_404(self, client, auth_headers):
        res = client.delete("/agroforestry/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_agronomist_can_delete(
        self, client, agro_headers, plantation_id, record_id
    ):
        res = client.delete(f"/agroforestry/{record_id}", headers=agro_headers)
        assert res.status_code == 200

    def test_technician_cannot_delete(
        self, client, tech_headers, plantation_id, record_id
    ):
        res = client.delete(f"/agroforestry/{record_id}", headers=tech_headers)
        assert res.status_code == 403

    def test_requires_auth(self, client, record_id):
        res = client.delete(f"/agroforestry/{record_id}")
        assert res.status_code == 401


# ════════════════════════════════════════════════════════════════════════════════
# 6. Bilan coopérative (GET /agroforestry/summary)
# ════════════════════════════════════════════════════════════════════════════════

class TestAgroforestrySummary:

    def test_returns_200(self, client, auth_headers):
        res = client.get("/agroforestry/summary", headers=auth_headers)
        assert res.status_code == 200

    def test_required_fields_present(self, client, auth_headers):
        res = client.get("/agroforestry/summary", headers=auth_headers)
        data = res.json()
        required = {
            "total_carbon_tco2", "total_trees_estimated",
            "avg_conformity_score", "plantations_with_inventory",
            "total_plantations", "unique_species_count"
        }
        assert required.issubset(set(data.keys()))

    def test_empty_cooperative_all_zeros(self, client, auth_headers):
        res = client.get("/agroforestry/summary", headers=auth_headers)
        data = res.json()
        assert data["plantations_with_inventory"] == 0
        assert data["total_carbon_tco2"] == 0.0
        assert data["unique_species_count"] == 0

    def test_summary_counts_inventoried_plantations(
        self, client, auth_headers, plantation_id
    ):
        # Avant inventaire
        before = client.get(
            "/agroforestry/summary", headers=auth_headers
        ).json()["plantations_with_inventory"]

        # Ajouter un inventaire
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER, headers=auth_headers,
        )

        after = client.get(
            "/agroforestry/summary", headers=auth_headers
        ).json()["plantations_with_inventory"]

        assert after == before + 1

    def test_summary_carbon_increases_after_add(
        self, client, auth_headers, plantation_id
    ):
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=MANGUIER, headers=auth_headers,
        )
        data = client.get(
            "/agroforestry/summary", headers=auth_headers
        ).json()
        assert data["total_carbon_tco2"] > 0.0

    def test_summary_counts_unique_species(
        self, client, auth_headers, plantation_id
    ):
        for species in [BANANIER, GLIRICIDI]:
            client.post(
                f"/plantations/{plantation_id}/agroforestry",
                json=species, headers=auth_headers,
            )
        data = client.get(
            "/agroforestry/summary", headers=auth_headers
        ).json()
        assert data["unique_species_count"] == 2

    def test_summary_requires_auth(self, client):
        res = client.get("/agroforestry/summary")
        assert res.status_code == 401


# ════════════════════════════════════════════════════════════════════════════════
# 7. Isolation entre coopératives
# ════════════════════════════════════════════════════════════════════════════════

class TestAgroforestryCooperativeIsolation:

    def test_coop_b_cannot_see_coop_a_inventory(self, client, auth_headers, plantation_id):
        """Coop A ajoute un inventaire, Coop B ne peut pas y accéder."""
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=BANANIER, headers=auth_headers,
        )

        # Coop B
        client.post("/auth/register", json={
            "email": "admin_b2@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop Isolée B", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_b2@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        res = client.get(
            f"/plantations/{plantation_id}/agroforestry",
            headers=headers_b,
        )
        assert res.status_code == 404

    def test_coop_b_summary_excludes_coop_a_data(
        self, client, auth_headers, plantation_id
    ):
        """Le bilan Coop B ne comptabilise pas les arbres de Coop A."""
        client.post(
            f"/plantations/{plantation_id}/agroforestry",
            json=MANGUIER, headers=auth_headers,
        )

        # Coop B vide
        client.post("/auth/register", json={
            "email": "admin_c@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop Isolée C", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_c@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        summary_b = client.get(
            "/agroforestry/summary", headers=headers_b
        ).json()
        assert summary_b["total_carbon_tco2"] == 0.0
        assert summary_b["plantations_with_inventory"] == 0

    def test_coop_b_cannot_delete_coop_a_record(
        self, client, auth_headers, plantation_id, record_id
    ):
        """Coop B ne peut pas supprimer un enregistrement appartenant à Coop A."""
        client.post("/auth/register", json={
            "email": "admin_d@iso.ci", "password": "pass123",
            "role": "admin", "cooperative_name": "Coop Isolée D", "country": "CI"
        })
        token_b = client.post("/auth/login", json={
            "email": "admin_d@iso.ci", "password": "pass123"
        }).json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        res = client.delete(
            f"/agroforestry/{record_id}",
            headers=headers_b,
        )
        assert res.status_code == 404
