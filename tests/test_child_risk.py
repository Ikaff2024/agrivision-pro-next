"""Jumeau Palier 2 — indicateur précoce EXPLICABLE de risque de travail d'enfant.

Vérifie le scoring déterministe, l'explicabilité (facteurs), les endpoints, le
cloisonnement coopérative et l'habilitation. Aide à l'enquête, jamais un verdict.
"""
from app.services.child_risk import _evaluate
from tests.conftest import create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _producer(client, headers, nom):
    r = client.post("/producers", json={"nom_complet": nom, "type_producteur": "membre"}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _child(client, headers, pid, **over):
    payload = {
        "producer_id": pid, "first_name": "Enf", "last_name": "Test",
        "date_of_birth": "2014-01-01", "gender": "M", "school_status": "enrolled",
        "is_working_on_farm": False, "work_frequency": "never",
    }
    payload.update(over)
    r = client.post("/children", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── Scoring déterministe (pur, sans DB) ──────────────────────────────────────

def test_evaluate_deterministic_and_capped():
    ev = _evaluate({
        "dangerous_children": 1, "working_regular_children": 1,
        "out_of_school_children": 1, "child_complaints": 1,
        "has_children": True, "recent_assessment": True, "has_living_income": True,
    })
    # 40 + 30 + 20 + 25 = 115 → plafonné à 100, niveau élevé.
    assert ev["score"] == 100
    assert ev["level"] == "eleve"
    codes = {f["code"] for f in ev["factors"]}
    assert {"dangerous_task", "working_regular", "out_of_school", "child_complaint"} <= codes
    # Facteurs triés par sévérité (high d'abord) et chacun a un libellé.
    assert ev["factors"][0]["severity"] == "high"
    assert all(f["label"] for f in ev["factors"])


def test_evaluate_empty_is_low():
    ev = _evaluate({"has_children": True, "recent_assessment": True, "has_living_income": True})
    assert ev["score"] == 0 and ev["level"] == "faible"
    assert ev["factors"] == []


def test_evaluate_data_completeness_drives_reco():
    ev = _evaluate({"has_children": False, "recent_assessment": False, "has_living_income": False})
    assert ev["data_completeness"] == 0.0
    assert "incomplètes" in ev["recommendation"].lower() or "recensement" in ev["recommendation"].lower()


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_high_risk_household_is_flagged_with_factors(client):
    h = _admin(client, "cr.high@test.ci", "Coop CR High")
    pid = _producer(client, h, "Ménage Risque")
    _child(client, h, pid, school_status="never_enrolled", is_working_on_farm=True,
           work_frequency="daily", dangerous_tasks_performed=["machete_use"])

    # Vue fiche : niveau élevé + facteurs explicites + disclaimer présent.
    r = client.get(f"/producers/{pid}/child-risk", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "eleve"
    assert any(f["code"] == "dangerous_task" for f in d["factors"])
    assert "enquête" in d["disclaimer"].lower()
    # Recommandation présente : soit « priorité d'enquête », soit « déjà suivi »
    # (un enfant à haut risque déclenche automatiquement la remédiation CacaoGuard).
    assert d["recommendation"]

    # Vue coop : le ménage apparaît dans la liste priorisée.
    rl = client.get("/twin/child-risk/at-risk", headers=h).json()
    assert rl["flagged_count"] >= 1
    assert any(hh["producer_id"] == pid and hh["level"] == "eleve" for hh in rl["households"])


def test_low_risk_household_not_flagged(client):
    h = _admin(client, "cr.low@test.ci", "Coop CR Low")
    pid = _producer(client, h, "Ménage Sain")
    _child(client, h, pid, school_status="enrolled", is_working_on_farm=False)

    r = client.get(f"/producers/{pid}/child-risk", headers=h).json()
    assert r["level"] == "faible"
    # Non listé dans les priorités d'enquête (on ne liste que moyen/élevé).
    rl = client.get("/twin/child-risk/at-risk", headers=h).json()
    assert all(hh["producer_id"] != pid for hh in rl["households"])
    assert rl["by_level"]["faible"] >= 1


def test_child_risk_cooperative_scoped(client):
    ha = _admin(client, "cr.a@test.ci", "Coop CR A")
    hb = _admin(client, "cr.b@test.ci", "Coop CR B")
    pid_a = _producer(client, ha, "SECRET Ménage A")
    _child(client, ha, pid_a, school_status="never_enrolled", is_working_on_farm=True, work_frequency="daily")

    # B ne voit pas le ménage de A dans sa liste…
    rl_b = client.get("/twin/child-risk/at-risk", headers=hb).json()
    assert all(hh["producer_id"] != pid_a for hh in rl_b["households"])
    # …ni via la fiche (403 autre coopérative).
    assert client.get(f"/producers/{pid_a}/child-risk", headers=hb).status_code == 403


def test_child_risk_role_allows_field_agent(client):
    h = _admin(client, "cr.role@test.ci", "Coop CR Role")
    h_tech = create_member_headers(client, h, "cr.tech@test.ci", "technician")
    # Un agent de terrain (technicien) peut consulter (rôle de protection).
    assert client.get("/twin/child-risk/at-risk", headers=h_tech).status_code == 200


def test_child_risk_requires_auth(client):
    assert client.get("/twin/child-risk/at-risk").status_code == 401
    assert client.get("/producers/1/child-risk").status_code == 401
