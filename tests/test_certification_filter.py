"""Filtre par certification sur les listes producteurs et plantations."""

from app.db.models import Certification, Plantation, PlantationCertification
from tests.conftest import TestingSessionLocal


def _login(client, email="cert.admin@test.ci", coop="Coop Cert"):
    client.post("/auth/register", json={
        "email": email, "password": "pass1234", "role": "admin",
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": "pass1234"}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def _plantation(client, h, name, owner):
    return client.post("/plantations", json={
        "name": name, "owner_name": owner, "country": "CI", "hectares": 2.0,
    }, headers=h).json()


def _attach_cert(plantation_id, code):
    """Crée le lien plantation↔certification directement (pas d'endpoint dédié dans ces tests)."""
    db = TestingSessionLocal()
    try:
        cert = db.query(Certification).filter(Certification.code == code).first()
        if not cert:
            cert = Certification(code=code, nom_complet=code, actif=True)
            db.add(cert)
            db.flush()
        db.add(PlantationCertification(plantation_id=plantation_id, certification_id=cert.id))
        db.commit()
    finally:
        db.close()


def test_plantation_and_producer_certification_filter(client):
    h = _login(client)
    # P1 certifiée FT, P2 sans certification.
    p1 = _plantation(client, h, "Parcelle FT", "Kouassi FT")
    p2 = _plantation(client, h, "Parcelle Nue", "Konan Nu")
    _attach_cert(p1["id"], "FT")

    # filters-options ne propose que les certifs réellement présentes.
    opts = client.get("/plantations/filters-options", headers=h).json()
    assert opts["certifications"] == ["FT"]

    # Plantations : filtre FT -> seulement P1.
    ft = client.get("/plantations?certification=FT", headers=h).json()
    ids = [p["id"] for p in ft]
    assert p1["id"] in ids and p2["id"] not in ids

    # Plantations : filtre RA (aucune) -> vide.
    assert client.get("/plantations?certification=RA", headers=h).json() == []

    # Producteurs : filtre FT -> seulement le producteur de P1.
    prod_ft = client.get("/producers?certification=FT", headers=h).json()
    prod_ids = [p["id"] for p in prod_ft]
    assert p1["producer_id"] in prod_ids and p2["producer_id"] not in prod_ids

    # Producteurs : sans filtre -> les deux producteurs présents.
    all_prod = client.get("/producers", headers=h).json()
    assert {p1["producer_id"], p2["producer_id"]}.issubset({p["id"] for p in all_prod})


def test_certification_filter_is_cooperative_scoped(client):
    """Le filtre certif reste cloisonné : une coop ne voit pas les certifs d'une autre."""
    ha = _login(client, "cert.a@test.ci", "Coop Cert A")
    hb = _login(client, "cert.b@test.ci", "Coop Cert B")
    pa = _plantation(client, ha, "PA", "Owner A")
    _attach_cert(pa["id"], "FT")
    # Coop B n'a aucune certif -> filters-options vide, filtre FT vide.
    assert client.get("/plantations/filters-options", headers=hb).json()["certifications"] == []
    assert client.get("/plantations?certification=FT", headers=hb).json() == []
    assert client.get("/producers?certification=FT", headers=hb).json() == []
