"""Tests — télédétection avancée (provider abstraction, fallback simulation)."""
from app.satellite.provider import (
    get_deforestation_signal,
    get_indices,
    get_timeseries,
    provider_status,
)


def _register_login(client, email, password, role="agronomist", coop="Coop Sat"):
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


# ── Provider (unitaire, sans réseau : pas de clés en test => simulation) ──────

def test_provider_indices_are_deterministic():
    a = get_indices(7.41, -7.55)
    b = get_indices(7.41, -7.55)
    assert a["ndvi"] == b["ndvi"]
    assert 0.0 <= a["ndvi"] <= 1.0
    assert "ndmi" in a and "moisture_status" in a
    assert a["source"] == "simulation"


def test_provider_timeseries_length_and_shape():
    ts = get_timeseries(7.41, -7.55, index="ndvi", months=12)
    assert ts["index"] == "ndvi"
    assert len(ts["series"]) == 12
    assert all("period" in pt and "value" in pt for pt in ts["series"])
    # déterministe
    assert ts["series"] == get_timeseries(7.41, -7.55, index="ndvi", months=12)["series"]


def test_provider_timeseries_clamps_months():
    assert len(get_timeseries(1, 1, months=999)["series"]) == 36
    assert len(get_timeseries(1, 1, months=0)["series"]) == 1


def test_provider_deforestation_default_safe():
    sig = get_deforestation_signal(7.41, -7.55)
    assert sig["loss_detected"] is False
    assert sig["source"] == "simulation"
    assert sig["scope"] == "buffer_1km"


def test_provider_deforestation_geometry_scope():
    from app.satellite.provider import get_deforestation_for_geometry
    geom = {"type": "Polygon", "coordinates": [[[-7.36, 5.84], [-7.34, 5.84], [-7.34, 5.86], [-7.36, 5.86], [-7.36, 5.84]]]}
    sig = get_deforestation_for_geometry(geom)
    assert sig["scope"] == "parcel"
    assert sig["loss_detected"] is False  # simulation sans clé


def test_provider_status_unconfigured_in_test():
    st = provider_status()
    assert st["vegetation_configured"] is False
    assert st["deforestation_configured"] is False


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_satellite_endpoints_require_auth(client):
    assert client.get("/satellite/indices?latitude=7.4&longitude=-7.5").status_code == 401
    assert client.get("/satellite/timeseries?latitude=7.4&longitude=-7.5").status_code == 401


def test_satellite_indices_and_timeseries_endpoints(client):
    h = _register_login(client, "sat@test.ci", "pass1234")
    r = client.get("/satellite/indices?latitude=7.4&longitude=-7.5", headers=h)
    assert r.status_code == 200, r.text
    assert "ndvi" in r.json() and "ndmi" in r.json()

    r2 = client.get("/satellite/timeseries?latitude=7.4&longitude=-7.5&index=ndmi&months=6", headers=h)
    assert r2.status_code == 200
    assert r2.json()["index"] == "ndmi"
    assert len(r2.json()["series"]) == 6


def test_satellite_plantation_advanced(client):
    h = _register_login(client, "sat2@test.ci", "pass1234", coop="Coop Sat 2")
    created = client.post("/plantations", json={
        "name": "Parcelle Sat", "owner_name": "Yao Sat",
        "country": "Côte d'Ivoire", "region": "Yeyasso", "hectares": 3.0,
        "latitude": 7.41, "longitude": -7.55,
    }, headers=h).json()
    pid = created["id"]
    r = client.get(f"/satellite/plantations/{pid}/advanced?months=12", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["plantation_id"] == pid
    assert "indices" in data and "ndvi_timeseries" in data and "deforestation" in data
    assert len(data["ndvi_timeseries"]["series"]) == 12
    # Sans délimitation : déforestation calculée sur la zone ~1 km (buffer)
    assert data["has_boundary"] is False
    assert data["deforestation"]["scope"] == "buffer_1km"

    # Avec délimitation : déforestation calculée sur le polygone exact de la parcelle
    geojson = '{"type":"Polygon","coordinates":[[[-7.56,7.40],[-7.54,7.40],[-7.54,7.42],[-7.56,7.42],[-7.56,7.40]]]}'
    br = client.post(f"/plantations/{pid}/boundary", json={"geojson": geojson, "method": "manual"}, headers=h)
    assert br.status_code in (200, 201), br.text
    r2 = client.get(f"/satellite/plantations/{pid}/advanced", headers=h)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["has_boundary"] is True
    assert d2["deforestation"]["scope"] == "parcel"
