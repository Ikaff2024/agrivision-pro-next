"""Aya « auto-apprenante » — mémoire de coopérative enseignable + feedback 👍/👎.

Vérifie : injection des faits dans le contexte, cloisonnement multi-tenant,
habilitation (seule la direction enseigne), et promotion d'une correction en fait.
"""
import app.services.llm_client as llmc
from tests.conftest import create_member_headers


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _capture_chat(monkeypatch):
    captured = {}
    monkeypatch.setattr(llmc, "chat", lambda db, p, **k: (captured.update(prompt=p) or {"text": "ok", "model": "m"}))
    return captured


def test_taught_fact_is_injected_into_context(client, monkeypatch):
    captured = _capture_chat(monkeypatch)
    h = _admin(client, "aya.mem@test.ci", "Coop Mem")
    r = client.post("/assistant/memory", json={"content": "Notre prix plancher 2026 est 1000 FCFA/kg", "category": "prix"}, headers=h)
    assert r.status_code == 201, r.text

    # Le fait apparaît dans la liste…
    lst = client.get("/assistant/memory", headers=h).json()
    assert any("prix plancher 2026" in m["content"] for m in lst)

    # …et il est injecté dans le contexte d'Aya.
    client.post("/assistant/ask", json={"question": "Quel est notre prix plancher ?"}, headers=h)
    assert "MÉMOIRE COOPÉRATIVE" in captured["prompt"]
    assert "prix plancher 2026" in captured["prompt"]


def test_memory_is_cooperative_scoped(client, monkeypatch):
    captured = _capture_chat(monkeypatch)
    ha = _admin(client, "aya.a@test.ci", "Coop Mem A")
    hb = _admin(client, "aya.b@test.ci", "Coop Mem B")
    client.post("/assistant/memory", json={"content": "SECRET-FACT-A", "category": "general"}, headers=ha)

    # B ne voit pas le fait de A, ni dans sa liste, ni dans son contexte.
    lst_b = client.get("/assistant/memory", headers=hb).json()
    assert all("SECRET-FACT-A" not in m["content"] for m in lst_b)
    client.post("/assistant/ask", json={"question": "infos ?"}, headers=hb)
    assert "SECRET-FACT-A" not in captured["prompt"]


def test_only_direction_can_teach(client):
    h = _admin(client, "aya.role@test.ci", "Coop Mem Role")
    h_tech = create_member_headers(client, h, "aya.tech@test.ci", "technician")
    # Le technicien peut CONSULTER…
    assert client.get("/assistant/memory", headers=h_tech).status_code == 200
    # …mais pas ENSEIGNER.
    assert client.post("/assistant/memory", json={"content": "essai technicien"}, headers=h_tech).status_code == 403


def test_feedback_thumbs_up(client):
    h = _admin(client, "aya.fb@test.ci", "Coop Mem FB")
    r = client.post("/assistant/feedback", json={"question": "Q ?", "answer": "R", "rating": 1}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["learned"] is False


def test_correction_by_direction_is_learned(client, monkeypatch):
    captured = _capture_chat(monkeypatch)
    h = _admin(client, "aya.corr@test.ci", "Coop Mem Corr")
    r = client.post("/assistant/feedback", json={
        "question": "Combien de maladies ?", "answer": "réponse fausse",
        "rating": -1, "correction": "Le modèle détecte 3 maladies de cabosse.",
    }, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["learned"] is True

    # La correction devient un fait mémoire (source=correction) et est réinjectée.
    lst = client.get("/assistant/memory", headers=h).json()
    assert any(m["source"] == "correction" and "3 maladies" in m["content"] for m in lst)
    client.post("/assistant/ask", json={"question": "maladies ?"}, headers=h)
    assert "3 maladies de cabosse" in captured["prompt"]


def test_correction_by_technician_not_learned(client):
    h = _admin(client, "aya.corr2@test.ci", "Coop Mem Corr2")
    h_tech = create_member_headers(client, h, "aya.tech2@test.ci", "technician")
    r = client.post("/assistant/feedback", json={
        "question": "Q ?", "answer": "R", "rating": -1, "correction": "tentative technicien",
    }, headers=h_tech)
    assert r.status_code == 201, r.text          # le retour est bien enregistré…
    assert r.json()["learned"] is False           # …mais NON promu en fait mémoire
    lst = client.get("/assistant/memory", headers=h).json()
    assert all("tentative technicien" not in m["content"] for m in lst)


def test_forget_fact(client, monkeypatch):
    captured = _capture_chat(monkeypatch)
    h = _admin(client, "aya.del@test.ci", "Coop Mem Del")
    mid = client.post("/assistant/memory", json={"content": "fait-a-oublier"}, headers=h).json()["id"]
    assert client.delete(f"/assistant/memory/{mid}", headers=h).status_code == 200
    lst = client.get("/assistant/memory", headers=h).json()
    assert all("fait-a-oublier" not in m["content"] for m in lst)
    client.post("/assistant/ask", json={"question": "des infos ?"}, headers=h)
    assert "fait-a-oublier" not in captured["prompt"]


def test_memory_requires_auth(client):
    assert client.get("/assistant/memory").status_code == 401
    assert client.post("/assistant/memory", json={"content": "x"}).status_code == 401
    assert client.post("/assistant/feedback", json={"question": "q", "rating": 1}).status_code == 401
