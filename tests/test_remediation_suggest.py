"""Brouillon d'actions de remédiation par IA (réaffectation du moteur open-source)."""
import app.services.llm_client as llmc
from app.db.models_social import RemediationPlan
from tests.conftest import TestingSessionLocal, create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plan_with_child(client, h):
    """Crée une parcelle (→ producteur) + un enfant à risque → plan auto-créé."""
    p = client.post("/plantations", json={
        "name": "P", "owner_name": "O", "country": "CI", "hectares": 2.0,
    }, headers=h).json()
    r = client.post("/children", json={
        "producer_id": p["producer_id"], "first_name": "Aya", "last_name": "K",
        "date_of_birth": "2014-01-01", "gender": "F", "school_status": "never_enrolled",
        "is_working_on_farm": True, "work_frequency": "daily",
        "dangerous_tasks_performed": ["machete", "pesticide"],
    }, headers=h)
    assert r.status_code == 201, r.text
    db = TestingSessionLocal()
    try:
        plan = db.query(RemediationPlan).order_by(RemediationPlan.id.desc()).first()
        return plan.id
    finally:
        db.close()


def test_suggest_actions_parses_json(client, monkeypatch):
    captured = {}
    def _chat(db, prompt, **kw):
        captured["prompt"] = prompt
        return {"text": '[{"action_type":"education","description":"Inscrire l enfant a l ecole","timeframe_days":30},'
                        '{"action_type":"health","description":"Organiser une visite medicale","timeframe_days":15},'
                        '{"action_type":"bidon","description":"Type inconnu -> other","timeframe_days":9999}]',
                "model": "meta-llama/llama-3.3-70b-instruct", "input_tokens": 20, "output_tokens": 40}
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "rem.sugg@test.ci", "Coop Sugg")
    pid = _plan_with_child(client, h)
    before = len(client.get(f"/remediation/plans/{pid}/actions", headers=h).json())
    r = client.post(f"/remediation/plans/{pid}/suggest-actions", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()["suggestions"]
    assert len(s) == 3
    assert s[0]["action_type"] == "education"
    assert s[2]["action_type"] == "other"          # type invalide -> normalisé
    assert s[2]["timeframe_days"] == 365            # borné
    assert "PROFIL ENFANT" in captured["prompt"]    # prompt fondé sur le profil réel
    # Suggérer ne CRÉE rien : le nombre d'actions du plan est inchangé.
    after = len(client.get(f"/remediation/plans/{pid}/actions", headers=h).json())
    assert after == before


def test_suggest_502_when_provider_unconfigured(client, monkeypatch):
    def _chat(db, p, **k):
        raise llmc.LLMNotConfigured("Fournisseur IA non configuré.")
    monkeypatch.setattr(llmc, "chat", _chat)
    h = _admin(client, "rem.sugg502@test.ci", "Coop Sugg502")
    pid = _plan_with_child(client, h)
    assert client.post(f"/remediation/plans/{pid}/suggest-actions", headers=h).status_code == 502


def test_suggest_reserved_to_write_role(client, monkeypatch):
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: {"text": "[]", "model": "m"})
    h = _admin(client, "rem.sugg.role@test.ci", "Coop SuggRole")
    pid = _plan_with_child(client, h)
    h_tech = create_member_headers(client, h, "rem.tech@test.ci", "technician")
    assert client.post(f"/remediation/plans/{pid}/suggest-actions", headers=h_tech).status_code == 403
