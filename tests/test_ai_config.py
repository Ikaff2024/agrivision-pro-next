"""Sélecteur de fournisseur IA (runtime) — endpoints propriétaire IKAFFANAN LTD.

Le propriétaire choisit le fournisseur + modèle du Conseil agronomique depuis
l'UI, sans toucher aux variables d'environnement. Les clés API restent des
secrets serveur — jamais exposées ni stockées en base.
"""
KEY = "test-owner-key"


def _h(key=KEY):
    return {"X-Owner-Key": key}


def _setup_key(monkeypatch):
    monkeypatch.setenv("OWNER_API_KEY", KEY)


def test_ai_config_requires_owner_key(client, monkeypatch):
    _setup_key(monkeypatch)
    assert client.get("/owner/ai-config", headers=_h("mauvaise")).status_code == 401
    assert client.put("/owner/ai-config", json={"provider": "anthropic"},
                      headers=_h("mauvaise")).status_code == 401


def test_ai_config_lists_providers_including_openrouter(client, monkeypatch):
    _setup_key(monkeypatch)
    r = client.get("/owner/ai-config", headers=_h())
    assert r.status_code == 200, r.text
    data = r.json()
    assert "current" in data and "provider" in data["current"]
    ids = {p["id"] for p in data["providers"]}
    assert {"anthropic", "openrouter", "deepseek", "qwen"} <= ids
    # Aucune clé API ne doit fuiter : seulement le nom de la variable + l'état.
    for p in data["providers"]:
        assert set(p.keys()) >= {"id", "label", "default_model", "key_env", "ready"}
        assert "api_key" not in p and "key" not in p


def test_ai_config_update_persists(client, monkeypatch):
    _setup_key(monkeypatch)
    r = client.put("/owner/ai-config", json={"provider": "openrouter",
                                             "model": "deepseek/deepseek-chat"}, headers=_h())
    assert r.status_code == 200, r.text
    cur = client.get("/owner/ai-config", headers=_h()).json()["current"]
    assert cur["provider"] == "openrouter"
    assert cur["model"] == "deepseek/deepseek-chat"


def test_ai_config_rejects_unknown_provider(client, monkeypatch):
    _setup_key(monkeypatch)
    r = client.put("/owner/ai-config", json={"provider": "skynet"}, headers=_h())
    assert r.status_code == 400


def test_ai_config_empty_model_falls_back_to_default(client, monkeypatch):
    _setup_key(monkeypatch)
    client.put("/owner/ai-config", json={"provider": "qwen", "model": ""}, headers=_h())
    cur = client.get("/owner/ai-config", headers=_h()).json()["current"]
    assert cur["provider"] == "qwen"
    assert cur["model"] == ""   # vide → le fournisseur utilisera son modèle par défaut
