"""Seuil de revenu vital editable par la coopérative (admin)."""
import base64
import json

from app.services.farmforce_reports import living_income_assessment, LIVING_INCOME_BENCHMARK_CFA


def _admin(client, email, coop="Coop LI"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
    return {"Authorization": "Bearer " + tok}, payload.get("coop_id")


# ── Logique du verdict ───────────────────────────────────────────────────────
def test_living_income_uses_custom_benchmark():
    # Seuil coop bas -> atteint ; seuil coop haut -> ecart.
    assert living_income_assessment(1_000_000, 500_000)["living_income_status"] == "atteint"
    assert living_income_assessment(1_000_000, 2_000_000)["living_income_status"] == "ecart"
    # None ou 0 -> defaut serveur.
    assert living_income_assessment(1_000_000, None)["living_income_benchmark_cfa"] == LIVING_INCOME_BENCHMARK_CFA
    assert living_income_assessment(1_000_000, 0)["living_income_benchmark_cfa"] == LIVING_INCOME_BENCHMARK_CFA


# ── Réglage via le profil coopérative (admin) ────────────────────────────────
def test_profile_benchmark_crud(client):
    h, coop_id = _admin(client, "li.crud@test.ci", "Coop LI CRUD")
    assert coop_id is not None
    # Par defaut : null
    r0 = client.get(f"/cooperatives/{coop_id}/profile", headers=h)
    assert r0.status_code == 200 and r0.json()["living_income_benchmark_cfa"] is None
    # Definir un seuil
    r1 = client.patch(f"/cooperatives/{coop_id}/profile", json={"living_income_benchmark_cfa": 1_800_000}, headers=h)
    assert r1.status_code == 200 and r1.json()["living_income_benchmark_cfa"] == 1_800_000
    # 0 -> revient au defaut (null)
    r2 = client.patch(f"/cooperatives/{coop_id}/profile", json={"living_income_benchmark_cfa": 0}, headers=h)
    assert r2.status_code == 200 and r2.json()["living_income_benchmark_cfa"] is None
    # negatif -> 400
    r3 = client.patch(f"/cooperatives/{coop_id}/profile", json={"living_income_benchmark_cfa": -5}, headers=h)
    assert r3.status_code == 400


def test_profile_benchmark_scoped(client):
    ha, coop_a = _admin(client, "li.a@test.ci", "Coop LI A")
    hb, _ = _admin(client, "li.b@test.ci", "Coop LI B")
    # B ne peut pas modifier le profil de A.
    r = client.patch(f"/cooperatives/{coop_a}/profile", json={"living_income_benchmark_cfa": 999}, headers=hb)
    assert r.status_code in (403, 404)
