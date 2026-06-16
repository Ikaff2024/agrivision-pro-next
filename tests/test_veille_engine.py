"""Moteur de veille agnostique (open-source) — pipeline RAG léger.

Teste la logique SANS réseau ni LLM réel : le `fetcher` (sources) et le `llm`
(synthèse) sont injectés / mockés. Vérifie aussi le cloisonnement par rôle des
endpoints. cf. docs/PLAN_MOTEUR_IA_AGNOSTIQUE.md
"""
from app.services import veille_engine
from app.db.models import VeilleItem
from tests.conftest import TestingSessionLocal, create_member_headers


# ── Normalisation (pure) ─────────────────────────────────────────────────────
def test_normalize_entry_ok_and_dates():
    src = {"key": "eudr_src", "name": "EUDR", "topics": ["eudr"]}
    item = veille_engine.normalize_entry(src, {
        "title": "EUDR — mise à jour", "link": "http://eu/1", "summary": "texte",
        "published_parsed": (2026, 6, 16, 10, 0, 0, 0, 0, 0),
    })
    assert item["title"] == "EUDR — mise à jour"
    assert item["url"] == "http://eu/1"
    assert item["topics"] == ["eudr"]
    assert item["published_at"].year == 2026 and item["published_at"].month == 6
    assert len(item["content_hash"]) == 64


def test_normalize_entry_no_title_returns_none():
    assert veille_engine.normalize_entry({"key": "k"}, {"link": "http://x"}) is None


# ── Ingestion : dédup + fail-soft ────────────────────────────────────────────
def test_ingest_creates_then_dedups(client):
    db = TestingSessionLocal()
    try:
        src = [{"key": "eudr_src", "name": "EUDR", "url": "u", "topics": ["eudr"]}]
        entries = [{"title": "Actu EUDR", "link": "http://eu/1", "summary": "s"}]
        r1 = veille_engine.ingest(db, sources=src, fetcher=lambda url: entries)
        assert r1["created"] == 1 and r1["skipped"] == 0
        r2 = veille_engine.ingest(db, sources=src, fetcher=lambda url: entries)
        assert r2["created"] == 0 and r2["skipped"] == 1  # même hash → dédupliqué
    finally:
        db.close()


def test_ingest_fail_soft_per_source(client):
    db = TestingSessionLocal()
    try:
        src = [
            {"key": "ok", "name": "OK", "url": "u", "topics": []},
            {"key": "bad", "name": "Bad", "url": "v", "topics": []},
        ]

        def fetch(url):
            if url == "v":
                raise RuntimeError("source morte")
            return [{"title": "A", "link": "http://a"}]

        r = veille_engine.ingest(db, sources=src, fetcher=fetch)
        assert r["created"] == 1 and r["errors"] == 1  # une source tombe, l'autre passe
    finally:
        db.close()


# ── Récupération : récence + filtre topics ───────────────────────────────────
def test_retrieve_filters_by_topic(client):
    db = TestingSessionLocal()
    try:
        veille_engine.ingest(db, sources=[
            {"key": "a", "name": "A", "url": "ua", "topics": ["eudr"]},
            {"key": "b", "name": "B", "url": "ub", "topics": ["marche"]},
        ], fetcher=lambda url: [{"title": "T-" + url, "link": "http://" + url}])
        only_eudr = veille_engine.retrieve(db, topics=["eudr"], limit=10)
        assert only_eudr and all("eudr" in [t.lower() for t in it.topics] for it in only_eudr)
        assert veille_engine.retrieve(db, limit=10)  # sans filtre → tout
    finally:
        db.close()


# ── Synthèse : LLM injecté, anti-hallucination (prompt = sources) ────────────
def test_synthesize_uses_injected_llm_and_sources(client):
    db = TestingSessionLocal()
    try:
        veille_engine.ingest(db, sources=[{"key": "a", "name": "Src A", "url": "u", "topics": ["eudr"]}],
                             fetcher=lambda url: [{"title": "Titre unique EUDR", "link": "http://a", "summary": "détail"}])
        items = veille_engine.retrieve(db, limit=10)
        captured = {}

        def fake_llm(prompt):
            captured["prompt"] = prompt
            return {"text": "Synthèse FR", "model": "qwen2.5-test"}

        res = veille_engine.synthesize(items, llm=fake_llm)
        assert res["summary"] == "Synthèse FR" and res["model"] == "qwen2.5-test"
        assert "Titre unique EUDR" in captured["prompt"]   # la synthèse part bien des sources
        assert len(res["items"]) == len(items)
    finally:
        db.close()


def test_synthesize_empty_no_llm_call(client):
    res = veille_engine.synthesize([], llm=lambda p: (_ for _ in ()).throw(AssertionError("LLM ne doit pas être appelé")))
    assert res["model"] is None and res["items"] == []


# ── Endpoints : rôles + flux ─────────────────────────────────────────────────
def test_ingest_endpoint_admin_then_items_readable(client, auth_headers, monkeypatch):
    monkeypatch.setattr(veille_engine, "_fetch_feed",
                        lambda url: [{"title": "Item veille", "link": "http://x", "summary": "s"}])
    r = client.post("/veille/ingest", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["created"] >= 1
    items = client.get("/veille/items", headers=auth_headers).json()
    assert items["count"] >= 1


def test_ingest_requires_admin(client, auth_headers):
    h_tech = create_member_headers(client, auth_headers, "veille.tech@fixture.ci", "technician")
    assert client.post("/veille/ingest", headers=h_tech).status_code == 403


def test_digest_requires_admin(client, auth_headers):
    h_tech = create_member_headers(client, auth_headers, "veille.tech2@fixture.ci", "technician")
    assert client.post("/veille/digest", headers=h_tech).status_code == 403


def test_digest_stored_and_latest(client, auth_headers, monkeypatch):
    monkeypatch.setattr(veille_engine, "_fetch_feed", lambda url: [{"title": "Item", "link": "http://i"}])
    client.post("/veille/ingest", headers=auth_headers)
    monkeypatch.setattr(veille_engine, "synthesize",
                        lambda items, llm=None: {"summary": "OK", "model": "qwen-test", "items": []})
    r = client.post("/veille/digest", headers=auth_headers)
    assert r.status_code == 200 and r.json()["model"] == "qwen-test"
    latest = client.get("/veille/digest", headers=auth_headers).json()
    assert latest["digest"]["payload"]["summary"] == "OK"


def test_digest_502_when_model_unconfigured(client, auth_headers, monkeypatch):
    for v in ("AI_OPENAI_BASE_URL", "AI_OPENAI_MODEL", "AI_OPENAI_API_KEY", "OPENWEIGHTS_API_KEY", "VEILLE_MODEL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(veille_engine, "_fetch_feed", lambda url: [{"title": "Item", "link": "http://i"}])
    client.post("/veille/ingest", headers=auth_headers)
    # items présents + aucun modèle open configuré → synthèse échoue proprement (502), pas de repli Claude.
    assert client.post("/veille/digest", headers=auth_headers).status_code == 502
