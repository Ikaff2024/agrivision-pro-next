"""Résumé exécutif IA pour la direction (réaffectation du moteur open-source)."""
import app.services.llm_client as llmc
from tests.conftest import TestingSessionLocal, create_member_headers


def _admin(client, email, coop="Coop Dir AI"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_ai_summary_ok(client, monkeypatch):
    captured = {}
    def _chat(db, prompt, **kw):
        captured["prompt"] = prompt
        return {"text": "Synthèse direction.", "model": "meta-llama/llama-3.3-70b-instruct",
                "input_tokens": 200, "output_tokens": 90}
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "dir.ai@test.ci")
    r = client.get("/dashboard/direction/ai-summary", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "Synthèse direction."
    assert body["model"]
    # Le prompt s'appuie sur les vrais KPI (réutilise l'agrégat direction).
    assert "INDICATEURS" in captured["prompt"] and "EUDR" in captured["prompt"]


def test_ai_summary_502_when_provider_unconfigured(client, monkeypatch):
    def _chat(db, prompt, **kw):
        raise llmc.LLMNotConfigured("Fournisseur IA non configuré.")
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "dir.ai502@test.ci", coop="Coop Dir 502")
    r = client.get("/dashboard/direction/ai-summary", headers=h)
    assert r.status_code == 502


def test_ai_summary_reserved_to_direction(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "x", "model": "m"})
    h = _admin(client, "dir.ai.role@test.ci", coop="Coop Dir Role")
    h_tech = create_member_headers(client, h, "dir.tech@test.ci", "technician")
    assert client.get("/dashboard/direction/ai-summary", headers=h_tech).status_code == 403


def test_ai_summary_requires_auth(client):
    assert client.get("/dashboard/direction/ai-summary").status_code == 401
