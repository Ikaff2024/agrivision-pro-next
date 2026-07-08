"""Interprétation IA par module (Aya) + suggestions de formation.

Le LLM est moqué (pas d'appel réseau). On vérifie : accès direction, module
inconnu -> 400, cache (2e appel = cached), suggestions de formation.
"""
import app.services.llm_client as llmc
from tests.conftest import create_member_headers


def _admin(client, email, coop="Coop AI"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_interpret_requires_auth(client):
    assert client.post("/ai/interpret", json={"module": "eudr"}).status_code == 401


def test_interpret_unknown_module(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "x", "model": "m"})
    h = _admin(client, "ai.unknown@test.ci", "Coop AI U")
    r = client.post("/ai/interpret", json={"module": "banane"}, headers=h)
    assert r.status_code == 400


def test_interpret_ok_and_cached(client, monkeypatch):
    calls = {"n": 0}
    def _chat(db, prompt, **kw):
        calls["n"] += 1
        return {"text": "**En bref** : tout va bien.", "model": "m", "input_tokens": 5, "output_tokens": 7}
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "ai.ok@test.ci", "Coop AI OK")
    r1 = client.post("/ai/interpret", json={"module": "eudr"}, headers=h)
    assert r1.status_code == 200, r1.text
    assert "En bref" in r1.json()["text"]
    assert r1.json()["cached"] is False
    # 2e appel identique -> servi par le cache (pas de nouvel appel LLM).
    r2 = client.post("/ai/interpret", json={"module": "eudr"}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert calls["n"] == 1


def test_interpret_reserved_to_management(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "x", "model": "m"})
    h_admin = _admin(client, "ai.founder@test.ci", "Coop AI Role")
    h_tech = create_member_headers(client, h_admin, "ai.tech@test.ci", "technician")
    r = client.post("/ai/interpret", json={"module": "eudr"}, headers=h_tech)
    assert r.status_code == 403


def test_interpret_agroforestry_injects_module_data(client, monkeypatch):
    """Régression : l'interprétation agroforesterie doit inclure les données du
    module (sinon Aya répond « pas de données » alors que la page en est pleine)."""
    captured = {}
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: (captured.update(prompt=p) or {"text": "ok", "model": "m"}))
    h = _admin(client, "ai.agro@test.ci", "Coop AI Agro")
    r = client.post("/ai/interpret", json={"module": "agroforestry"}, headers=h)
    assert r.status_code == 200, r.text
    # Le prompt doit contenir la section de données propres au module.
    assert "module_detail" in captured["prompt"]
    assert "agroforesterie" in captured["prompt"]


def test_training_suggestions_ok(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "**Protection de l'enfant**\n- ...", "model": "m", "input_tokens": 3, "output_tokens": 9})
    h = _admin(client, "ai.train@test.ci", "Coop AI Train")
    r = client.get("/ai/training-suggestions", headers=h)
    assert r.status_code == 200, r.text
    assert "Protection" in r.json()["text"]
