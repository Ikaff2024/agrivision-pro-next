"""Avis de formation ANONYMES (collecte sans compte, agrégation, cloisonnement)."""


def _admin(client, email, coop="Coop FB"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _session(client, h, title="Session Avis"):
    r = client.post("/training/sessions", json={
        "title": title, "training_type": "child_protection",
        "scheduled_date": "2026-02-01", "location": "Soubré",
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_anonymous_feedback_flow_and_aggregation(client):
    h = _admin(client, "fb.a@test.ci", "Coop FB A")
    sid = _session(client, h)

    # Jeton d'avis (admin)
    tok = client.post(f"/training/sessions/{sid}/feedback-token", headers=h).json()["feedback_token"]
    assert tok and len(tok) >= 8

    # Page publique : titre exposé
    info = client.get(f"/public/training-info?s={tok}")
    assert info.status_code == 200 and info.json()["title"] == "Session Avis"

    # Trois avis anonymes SANS auth
    for note in (5, 4, 3):
        r = client.post("/public/training-feedback", json={"feedback_token": tok, "rating": note})
        assert r.status_code == 201, r.text

    # Agrégation visible côté coopérative
    sessions = client.get("/training/sessions", headers=h).json()
    s = next(x for x in sessions if x["id"] == sid)
    assert s["feedback_count"] == 3
    assert s["feedback_avg"] == 4.0  # (5+4+3)/3


def test_feedback_invalid_token(client):
    assert client.get("/public/training-info?s=nope").status_code == 404
    assert client.post("/public/training-feedback", json={"feedback_token": "badtoken1", "rating": 5}).status_code == 404


def test_feedback_rating_bounds(client):
    h = _admin(client, "fb.b@test.ci", "Coop FB B")
    sid = _session(client, h)
    tok = client.post(f"/training/sessions/{sid}/feedback-token", headers=h).json()["feedback_token"]
    # note hors bornes -> 422
    assert client.post("/public/training-feedback", json={"feedback_token": tok, "rating": 9}).status_code == 422


def test_feedback_token_requires_role(client):
    h = _admin(client, "fb.c@test.ci", "Coop FB C")
    sid = _session(client, h)
    r = client.post(f"/training/sessions/{sid}/feedback-token")  # sans auth
    assert r.status_code in (401, 403)
