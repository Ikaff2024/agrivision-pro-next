"""Assistant « mes données » — Q&A ancré sur un instantané coop, via le moteur IA."""
import json

import app.services.llm_client as llmc
from tests.conftest import TestingSessionLocal, create_member_headers


def _admin(client, email, coop="Coop Assist"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_assistant_grounded_on_snapshot(client, monkeypatch):
    captured = {}
    def _chat(db, prompt, **kw):
        captured["prompt"] = prompt
        return {"text": "Vous avez 1 parcelle.", "model": "meta-llama/llama-3.3-70b-instruct",
                "input_tokens": 50, "output_tokens": 10}
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "assist.ok@test.ci")
    # Une parcelle non conforme (sans polygone/GPS) → apparaît dans l'instantané.
    client.post("/plantations", json={"name": "Parcelle X", "owner_name": "O", "country": "CI",
                                      "region": "Soubré", "hectares": 2.0}, headers=h)
    r = client.post("/assistant/ask", json={"question": "Quelles parcelles non conformes ?"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["answer"]
    # Le prompt est ANCRÉ : il contient la question + un instantané JSON cloisonné.
    assert "QUESTION" in captured["prompt"] and "DONNÉES" in captured["prompt"]
    assert "Parcelle X" in captured["prompt"]   # entité réelle de la coop incluse


def test_assistant_502_when_provider_unconfigured(client, monkeypatch):
    def _chat(db, p, **k):
        raise llmc.LLMNotConfigured("Fournisseur IA non configuré.")
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "assist.502@test.ci", coop="Coop Assist 502")
    r = client.post("/assistant/ask", json={"question": "Test ?"}, headers=h)
    assert r.status_code == 502


def test_assistant_reserved_to_direction(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "x", "model": "m"})
    h = _admin(client, "assist.role@test.ci", coop="Coop Assist Role")
    h_tech = create_member_headers(client, h, "assist.tech@test.ci", "technician")
    assert client.post("/assistant/ask", json={"question": "Test ?"}, headers=h_tech).status_code == 403


def test_assistant_requires_auth(client):
    assert client.post("/assistant/ask", json={"question": "Test ?"}).status_code == 401


def test_assistant_isolation(client, monkeypatch):
    """L'instantané ne contient QUE les données de la coop de l'utilisateur."""
    captured = {}
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: (captured.update(prompt=p) or {"text": "ok", "model": "m"}))
    ha = _admin(client, "assist.a@test.ci", coop="Coop Assist A")
    hb = _admin(client, "assist.b@test.ci", coop="Coop Assist B")
    client.post("/plantations", json={"name": "SECRET-A", "owner_name": "O", "country": "CI", "hectares": 1.0}, headers=ha)
    client.post("/assistant/ask", json={"question": "parcelles ?"}, headers=hb)
    assert "SECRET-A" not in captured["prompt"]   # B ne voit pas la parcelle de A
