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
