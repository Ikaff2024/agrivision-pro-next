"""Tests d'intégration — moteur diagnostique."""

from tests.conftest import create_member_headers

VALID_INPUTS = {
    "country": "Côte d'Ivoire",
    "region": "Soubré",
    "rainfall_mm_month": 120.0,
    "humidity_pct": 70.0,
    "avg_temp_c": 27.0,
    "plantation_age_years": 12.0,
    "shade_tree_density_pct": 35.0,
}


def test_diagnostic_success(client, auth_headers, plantation_id):
    res = client.post(
        f"/cacao/diagnostic?plantation_id={plantation_id}",
        json=VALID_INPUTS,
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "global_score" in data
    assert data["global_risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert len(data["module_results"]) == 4


def test_diagnostic_saves_to_db(client, auth_headers, plantation_id):
    client.post(
        f"/cacao/diagnostic?plantation_id={plantation_id}",
        json=VALID_INPUTS,
        headers=auth_headers,
    )
    history = client.get(
        f"/plantations/{plantation_id}/history", headers=auth_headers
    )
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_diagnostic_unknown_plantation(client, auth_headers):
    res = client.post(
        "/cacao/diagnostic?plantation_id=99999",
        json=VALID_INPUTS,
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_diagnostic_requires_agronomist_or_admin(client, auth_headers, plantation_id):
    tech = create_member_headers(client, auth_headers, "tech@test.ci", "technician")
    res = client.post(
        f"/cacao/diagnostic?plantation_id={plantation_id}",
        json=VALID_INPUTS,
        headers=tech,
    )
    assert res.status_code == 403


def test_diagnostic_invalid_inputs(client, auth_headers, plantation_id):
    # humidity_pct hors bornes (>100)
    bad = {**VALID_INPUTS, "humidity_pct": 150.0}
    res = client.post(
        f"/cacao/diagnostic?plantation_id={plantation_id}",
        json=bad,
        headers=auth_headers,
    )
    assert res.status_code == 422
