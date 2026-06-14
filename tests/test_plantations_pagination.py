"""P2 scale : /plantations?paginated=true enrichi (score / risque / EUDR) + filtre risk.

Vérifie que le mode paginé renvoie total + pages + items enrichis, que la pagination
fonctionne, que le filtre risk est pris en compte, et que le mode liste brute reste
rétro-compatible (le frontend actuel en dépend tant que la refonte n'est pas déployée).
"""


def _login(client, email="plant.pager@test.ci", coop="Coop PlantPager"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_plantations_paginated_enriched_and_risk_filter(client):
    h = _login(client)
    for i in range(3):
        r = client.post("/plantations", json={
            "name": f"Parcelle {i}", "owner_name": f"Prod {i}", "country": "CI",
        }, headers=h)
        assert r.status_code in (200, 201), r.text

    # Mode paginé : total + pages + items enrichis
    p1 = client.get("/plantations?paginated=true&page=1&page_size=2", headers=h).json()
    assert p1["total"] == 3
    assert p1["total_pages"] == 2
    assert len(p1["items"]) == 2
    item = p1["items"][0]
    for k in ("id", "name", "score", "risk_level", "eudr_status", "eudr_max", "export_waiver"):
        assert k in item, f"clé '{k}' absente de l'item paginé"

    # Page 2 : le reste
    p2 = client.get("/plantations?paginated=true&page=2&page_size=2", headers=h).json()
    assert len(p2["items"]) == 1

    # Filtre risque sans diagnostic enregistré -> aucune parcelle
    assert client.get("/plantations?paginated=true&risk=HIGH", headers=h).json()["total"] == 0

    # Mode liste brute (rétro-compatible) : toujours une liste simple
    raw = client.get("/plantations", headers=h).json()
    assert isinstance(raw, list) and len(raw) == 3
