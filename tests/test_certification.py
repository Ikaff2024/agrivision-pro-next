"""Tests d'integration — certification (audits, non-conformites) module #3."""

from tests.conftest import create_member_headers


def _login(client, email, password="pass1234", role="admin", coop="Coop Cert"):
    """Crée un compte FONDATEUR (nouvelle coop) et retourne ses headers."""
    client.post("/auth/register", json={
        "email": email, "password": password, "role": role,
        "cooperative_name": coop, "country": "CI",
    })
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": "Bearer " + tok}


def test_certification_requires_auth(client):
    assert client.get("/certification-audits").status_code == 401
    assert client.get("/non-conformities").status_code == 401


def test_list_certifications_referentiel(client):
    h = _login(client, "cert.ref@test.ci", coop="Coop Ref")
    r = client.get("/certifications", headers=h)
    # Le referentiel est seede au demarrage applicatif (prod/staging) ; en test
    # la table peut etre vide : on verifie juste le contrat de l'endpoint.
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_audit_lifecycle_and_non_conformities(client):
    h = _login(client, "cert.a@test.ci", coop="Coop A")
    a = client.post("/certification-audits", json={
        "audit_type": "external", "auditor_body": "FLOCERT", "scope": "Audit annuel RA",
    }, headers=h)
    assert a.status_code == 201, a.text
    audit = a.json()
    assert audit["status"] == "planned"

    # Ajout d'une non-conformite liee a l'audit
    nc = client.post("/non-conformities", json={
        "audit_id": audit["id"], "severity": "major",
        "description": "Stockage pesticides non conforme",
        "corrective_action": "Reamenager le local", "due_date": "2020-01-01",
    }, headers=h)
    assert nc.status_code == 201, nc.text
    ncd = nc.json()
    assert ncd["severity"] == "major"
    assert ncd["overdue"] is True  # echeance passee, statut open

    # Cloture de l'audit
    c = client.post(f"/certification-audits/{audit['id']}/complete", json={"result": "conditional", "score_pct": 82}, headers=h)
    assert c.status_code == 200 and c.json()["result"] == "conditional"

    # Detail audit inclut la NC
    det = client.get(f"/certification-audits/{audit['id']}", headers=h).json()
    assert det["non_conformity_count"] == 1
    assert len(det["non_conformities"]) == 1

    # Resolution de la NC
    u = client.patch(f"/non-conformities/{ncd['id']}", json={"status": "resolved", "resolution_notes": "Local refait"}, headers=h)
    assert u.status_code == 200, u.text
    assert u.json()["status"] == "resolved" and u.json()["overdue"] is False
    assert u.json()["resolved_date"] is not None


def test_certification_summary(client):
    h = _login(client, "cert.s@test.ci", coop="Coop S")
    audit = client.post("/certification-audits", json={"audit_type": "internal"}, headers=h).json()
    client.post("/non-conformities", json={"audit_id": audit["id"], "severity": "critical", "description": "NC1", "due_date": "2020-01-01"}, headers=h)
    client.post("/non-conformities", json={"audit_id": audit["id"], "severity": "minor", "description": "NC2"}, headers=h)
    s = client.get("/certification/summary", headers=h).json()
    assert s["audits_total"] == 1 and s["audits_planned"] == 1
    assert s["non_conformities_total"] == 2 and s["non_conformities_open"] == 2
    assert s["non_conformities_overdue"] == 1
    assert s["by_severity"]["critical"] == 1 and s["by_severity"]["minor"] == 1


def test_certification_write_role(client):
    h_admin = _login(client, "cert.founder@test.ci", coop="Coop WR")
    h_tech = create_member_headers(client, h_admin, "cert.tech@test.ci", "technician")
    assert client.get("/certification-audits", headers=h_tech).status_code == 200
    assert client.post("/certification-audits", json={"audit_type": "internal"}, headers=h_tech).status_code == 403


def test_non_conformity_invalid_severity(client):
    h = _login(client, "cert.inv@test.ci", coop="Coop Inv")
    r = client.post("/non-conformities", json={"severity": "huge", "description": "Description valide"}, headers=h)
    assert r.status_code == 400
