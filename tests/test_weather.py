"""Tests — météo agricole (GET /weather/current). Open-Meteo est mocké (pas de réseau)."""
import app.api.weather_routes as wr


def _auth(client, email="weather@test.ci"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": "Coop Weather " + email, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_weather_ok(client, monkeypatch):
    async def _fake(lat, lon):
        return {"temperature_c": 26.5, "humidity_pct": 82, "rainfall_mm_month": 140.0,
                "source": "open-meteo", "latitude": lat, "longitude": lon}
    monkeypatch.setattr(wr, "get_weather", _fake)
    r = client.get("/weather/current?latitude=5.78&longitude=-6.59", headers=_auth(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["temperature_c"] == 26.5
    assert body["humidity_pct"] == 82
    assert body["rainfall_mm_month"] == 140.0
    assert body["source"] == "open-meteo"


def test_weather_unavailable_returns_503(client, monkeypatch):
    async def _none(lat, lon):
        return None
    monkeypatch.setattr(wr, "get_weather", _none)
    r = client.get("/weather/current?latitude=5.78&longitude=-6.59", headers=_auth(client, "weather.none@test.ci"))
    assert r.status_code == 503


def test_weather_requires_auth(client):
    assert client.get("/weather/current?latitude=5.78&longitude=-6.59").status_code == 401


def test_weather_validates_coords(client):
    h = _auth(client, "weather.val@test.ci")
    assert client.get("/weather/current", headers=h).status_code == 422            # params manquants
    assert client.get("/weather/current?latitude=200&longitude=0", headers=h).status_code == 422  # hors bornes


# ── Parsing Open-Meteo : temps réel (diagnostic) + moyennes 30 j (jumeau) ──────

from app.services.weather import _parse_open_meteo  # noqa: E402


def test_parse_real_time_and_30d_means():
    d = {
        "current": {"temperature_2m": 29.0, "relative_humidity_2m": 77},
        "daily": {
            "precipitation_sum": [5, 10, 0, 3],          # cumul = 18
            "temperature_2m_mean": [22, 24, 23, 23],     # moyenne = 23.0
        },
        "hourly": {"relative_humidity_2m": [90, 96, 100, 94]},  # moyenne = 95.0
    }
    out = _parse_open_meteo(d)
    assert out["temperature_c"] == 29.0 and out["humidity_pct"] == 77   # temps réel conservé
    assert out["rainfall_mm_month"] == 18.0                              # cumul 30 j
    assert out["temp_mean_30d"] == 23.0                                  # moyenne 30 j
    assert out["humidity_mean_30d"] == 95.0


def test_parse_handles_missing_means():
    d = {"current": {"temperature_2m": 28.0, "relative_humidity_2m": 80},
         "daily": {"precipitation_sum": [1, 2]}}
    out = _parse_open_meteo(d)
    assert out["temperature_c"] == 28.0 and out["rainfall_mm_month"] == 3.0
    assert out["temp_mean_30d"] is None and out["humidity_mean_30d"] is None


def test_parse_empty_returns_none():
    assert _parse_open_meteo({}) is None
