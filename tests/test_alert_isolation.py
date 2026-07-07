"""Cloisonnement multi-tenant des ALERTES (régression fuite inter-coopératives).

Alert n'a pas de cooperative_id : le périmètre se résout via source_entity/source_id
(-> producteur -> coopérative). Sans ce filtre, les COMPTEURS d'alertes ouvertes
fuitaient d'une coopérative à l'autre (même nombre affiché partout). Ce test crée
une alerte dans la coop A et vérifie que la coop B voit 0.
"""


def _admin(client, email, coop):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _producer(client, h, nom):
    r = client.post("/producers", json={"nom_complet": nom, "type_producteur": "membre"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _open_alert_via_complaint(client, h, producer_id):
    """Un signalement de sévérité HIGH rattaché à un producteur crée une alerte ouverte."""
    r = client.post("/complaints", json={
        "complaint_type": "other", "severity": "high",
        "description": "Cas grave signale par un agent de terrain.",
        "producer_id": producer_id,
    }, headers=h)
    assert r.status_code == 201, r.text


def test_open_alerts_do_not_leak_across_cooperatives(client):
    ha = _admin(client, "iso.a@test.ci", "Coop Iso A")
    hb = _admin(client, "iso.b@test.ci", "Coop Iso B")

    pa = _producer(client, ha, "Producteur A")
    _open_alert_via_complaint(client, ha, pa)

    # Coop A voit son alerte.
    a_cg = client.get("/cacaoguard/summary", headers=ha).json()
    a_dir = client.get("/dashboard/direction", headers=ha).json()
    assert a_cg["active_alerts"] >= 1
    assert a_dir["alerts"]["open"] >= 1

    # Coop B (aucune activité) ne doit RIEN voir de l'alerte de A.
    b_cg = client.get("/cacaoguard/summary", headers=hb).json()
    b_dir = client.get("/dashboard/direction", headers=hb).json()
    assert b_cg["active_alerts"] == 0, "Fuite d'alertes CacaoGuard entre coopératives !"
    assert b_dir["alerts"]["open"] == 0, "Fuite d'alertes (dashboard) entre coopératives !"


def test_offline_sync_alerts_scoped_to_cooperative(client):
    """La synchro hors-ligne ne renvoie que les alertes de la coopérative."""
    ha = _admin(client, "iso.sa@test.ci", "Coop Sync A")
    hb = _admin(client, "iso.sb@test.ci", "Coop Sync B")
    pa = _producer(client, ha, "Producteur SA")
    _open_alert_via_complaint(client, ha, pa)

    a = client.post("/sync/pull", json={"entities": ["alerts"]}, headers=ha).json()
    b = client.post("/sync/pull", json={"entities": ["alerts"]}, headers=hb).json()
    assert a["counts"]["alerts"] >= 1
    assert b["counts"]["alerts"] == 0, "Fuite d'alertes via la synchro hors-ligne !"
