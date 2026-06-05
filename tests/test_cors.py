"""Tests CORS — le domaine de production doit être autorisé (régression prod)."""


def _preflight(client, origin):
    return client.options("/auth/login", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })


def test_cors_allows_prod_www(client):
    r = _preflight(client, "https://www.app-agrivision-pro.com")
    assert r.headers.get("access-control-allow-origin") == "https://www.app-agrivision-pro.com"


def test_cors_allows_prod_apex(client):
    r = _preflight(client, "https://app-agrivision-pro.com")
    assert r.headers.get("access-control-allow-origin") == "https://app-agrivision-pro.com"


def test_cors_allows_netlify_preview(client):
    r = _preflight(client, "https://deploy-preview-12--agrivision.netlify.app")
    assert r.headers.get("access-control-allow-origin") == "https://deploy-preview-12--agrivision.netlify.app"


def test_cors_blocks_unknown_origin(client):
    r = _preflight(client, "https://evil.example.com")
    assert r.headers.get("access-control-allow-origin") is None
