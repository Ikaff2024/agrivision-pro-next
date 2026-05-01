"""
tests/test_anti_detractor.py — Sprint R1d : tests des garde-fous Anti-Detracteur.

Couvre :
  - Validation Pydantic du champ hectares lors de la creation de plantation
  - Helper _interpret_ndvi : seuils et messages
  - Endpoints satellite : presence des champs ndvi_label, confidence, warning_message
"""
import pytest


# ─── Tests : validation hectares dans PlantationCreate ────────────────────────
class TestHectaresValidation:
    """
    Le champ 'hectares' doit imposer 0.25 < hectares <= 500 si fourni.
    Si non fourni (None), c'est accepte (champ optionnel).
    """

    def test_hectares_too_small_rejected(self, client, auth_headers):
        """Une plantation avec hectares=0.0025 (un toit !) doit etre rejetee."""
        r = client.post("/plantations", json={
            "name": "Plantation Toit",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 0.0025,
        }, headers=auth_headers)
        assert r.status_code == 422, \
            f"Plantation 0.0025 ha doit etre rejetee, got {r.status_code} : {r.text}"

    def test_hectares_just_under_threshold_rejected(self, client, auth_headers):
        """0.24 ha doit etre refuse (en dessous du seuil 0.25)."""
        r = client.post("/plantations", json={
            "name": "Plantation Borderline",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 0.24,
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_hectares_at_threshold_accepted(self, client, auth_headers):
        """0.25 ha exactement... est-ce gt=0.25 ou ge=0.25 ?"""
        # Avec gt=0.25, exactement 0.25 doit etre rejete
        r = client.post("/plantations", json={
            "name": "Plantation Threshold",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 0.25,
        }, headers=auth_headers)
        assert r.status_code == 422, "gt=0.25 implique que 0.25 exactement est refuse"

    def test_hectares_normal_value_accepted(self, client, auth_headers):
        """Une plantation de 3.5 ha (taille typique) doit passer."""
        r = client.post("/plantations", json={
            "name": "Plantation Normale",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 3.5,
        }, headers=auth_headers)
        assert r.status_code == 200, \
            f"Plantation 3.5 ha doit etre acceptee, got {r.status_code} : {r.text}"

    def test_hectares_too_large_rejected(self, client, auth_headers):
        """Au-dessus de 500 ha c'est suspect (faute de frappe ou test malicieux)."""
        r = client.post("/plantations", json={
            "name": "Plantation Geante",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 1000,
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_hectares_at_max_accepted(self, client, auth_headers):
        """500 ha doit etre accepte (le=500 inclut la borne)."""
        r = client.post("/plantations", json={
            "name": "Plantation Max",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            "hectares": 500,
        }, headers=auth_headers)
        assert r.status_code == 200

    def test_hectares_optional_none_accepted(self, client, auth_headers):
        """Si le champ n'est pas fourni, la plantation doit etre acceptee."""
        r = client.post("/plantations", json={
            "name": "Plantation Sans Surface",
            "owner_name": "Test",
            "country": "Côte d'Ivoire",
            # pas de hectares
        }, headers=auth_headers)
        assert r.status_code == 200


# ─── Tests : helper _interpret_ndvi ───────────────────────────────────────────
class TestInterpretNdvi:
    """Verifie que le helper renvoie les bonnes interpretations selon le seuil."""

    def test_critical_low_below_threshold(self):
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.10)
        assert result["status"] == "CRITICAL_LOW"
        assert result["confidence"] == "low"
        assert result["message"] is not None
        assert "0.10" in result["message"] or "0,10" in result["message"]

    def test_critical_low_at_boundary(self):
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.29)
        assert result["confidence"] == "low"

    def test_stressed_above_critical(self):
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.40)
        assert result["status"] == "STRESSED"
        assert result["confidence"] == "high"
        assert result["message"] is None

    def test_moderate(self):
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.60)
        assert result["status"] == "MODERATE"
        assert result["confidence"] == "high"

    def test_healthy(self):
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.85)
        assert result["status"] == "HEALTHY"
        assert result["confidence"] == "high"

    def test_critical_yeo_house_case(self):
        """
        Reproduit le cas reel : la maison de YEO (la "Plantation GB") avec NDVI 0.30.
        Note : 0.30 est >= 0.30 donc selon la logique stricte ndvi < 0.30,
        c'est en STRESSED. On valide le comportement attendu.
        """
        from app.api.routes import _interpret_ndvi
        result = _interpret_ndvi(0.30)
        # 0.30 n'est PAS < 0.30, donc c'est STRESSED (pas CRITICAL_LOW)
        assert result["status"] == "STRESSED", (
            "Avec ndvi < 0.30, exactement 0.30 doit etre STRESSED. "
            "Si on veut inclure 0.30, modifier en ndvi <= 0.30."
        )


# ─── Tests : endpoints satellite enrichis ─────────────────────────────────────
class TestSatelliteEndpointsEnriched:
    """Les endpoints satellite doivent renvoyer les nouveaux champs R1d."""

    def test_plantation_satellite_returns_new_fields(self, client, auth_headers, plantation_id):
        # plantation_id (fixture) a lat=5.78, lon=-6.59 (Soubre)
        r = client.get(
            f"/plantations/{plantation_id}/satellite",
            headers=auth_headers,
        )
        assert r.status_code == 200, f"Reponse: {r.text}"
        data = r.json()
        # Champs originaux toujours presents
        assert "ndvi" in data
        assert "vegetation_status" in data
        # Nouveaux champs R1d
        assert "ndvi_label" in data
        assert "confidence" in data
        assert data["confidence"] in ("low", "high")
        assert "warning_message" in data
        # Si confidence=low, message obligatoire ; sinon None
        if data["confidence"] == "low":
            assert data["warning_message"] is not None
        else:
            assert data["warning_message"] is None

    def test_satellite_ndvi_simple_returns_new_fields(self, client, auth_headers):
        """L'endpoint /satellite/ndvi (sans plantation) doit aussi etre enrichi."""
        r = client.get(
            "/satellite/ndvi",
            params={"latitude": 5.78, "longitude": -6.59},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "ndvi_label" in data
        assert "confidence" in data
        assert "warning_message" in data
