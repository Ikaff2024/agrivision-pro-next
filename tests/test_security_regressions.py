"""Tests de non-regression SECURITE — constats P0 de la revue d'architecture.

Ces tests encodent trois proprietes de securite qui ont ete violees en
production et qui doivent le rester (non violees) :

  P0-1  Les donnees de signalement (saisissables SANS COMPTE via le formulaire
        public villageois) ne doivent jamais etre interpretees comme du HTML
        dans l'interface d'administration.
  P0-2  Le lien de reinitialisation de mot de passe ne doit JAMAIS apparaitre
        dans une reponse HTTP hors environnement de developpement explicite.
  P0-3  Le moteur de coherence CacaoGuard et les controles d'alertes ne doivent
        jamais exposer une donnee d'une autre cooperative.

Chaque test echoue AVANT le correctif correspondant : ils constituent la preuve
du defaut autant que la garantie de non-regression.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.db.models import Producer
from app.db.models_social import (
    Child,
    MonitoringVisit,
    SchoolStatus,
    VisitStatus,
    VisitType,
    WorkFrequency,
)
from tests.conftest import TestingSessionLocal

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


# ════════════════════════════════════════════════════════════════════════════
# Helpers partages
# ════════════════════════════════════════════════════════════════════════════

def _register_admin(client, email: str, coop_name: str) -> dict:
    """Cree une cooperative + son admin fondateur, renvoie l'en-tete Bearer."""
    r = client.post("/auth/register", json={
        "email": email,
        "password": "testpass123",
        "role": "admin",
        "cooperative_name": coop_name,
        "country": "Cote d'Ivoire",
    })
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# Marqueur volontairement improbable : s'il apparait dans une reponse destinee
# a une AUTRE cooperative, la fuite est certaine (pas de faux positif possible).
COOP_B_MARKER = "ZZMARQUEURFUITECOOPB"


def _seed_coop_b_social_case(coop_b_id: int, *, overdue: bool = False) -> int:
    """Producteur + enfant + visite non conforme dans la coop B.

    La visite porte une photo SANS consentement trace : c'est exactement la
    condition qui declenche le constat `photos_without_consent`, dont le message
    contient le NOM DU PRODUCTEUR. Avec `overdue`, la visite est aussi en retard,
    ce qui declenche une alerte operationnelle nommant elle aussi le producteur.
    """
    db = TestingSessionLocal()
    try:
        producer = Producer(
            nom_complet=COOP_B_MARKER,
            cooperative_id=coop_b_id,
            is_active=True,
            type_producteur="membre",
        )
        db.add(producer)
        db.commit()
        db.refresh(producer)

        db.add(Child(
            producer_id=producer.id,
            first_name="Enfant",
            last_name=COOP_B_MARKER,
            date_of_birth=date.today() - timedelta(days=365 * 12),
            gender="M",
            school_status=SchoolStatus.ENROLLED,
            is_working_on_farm=True,
            work_frequency=WorkFrequency.DAILY,
            is_active=True,
        ))

        scheduled = date.today() - timedelta(days=30) if overdue else date.today()
        db.add(MonitoringVisit(
            producer_id=producer.id,
            visit_type=VisitType.ROUTINE,
            status=VisitStatus.SCHEDULED if overdue else VisitStatus.COMPLETED,
            scheduled_date=scheduled,
            lead_assessor_id=1,
            photos=["photo-sans-consentement.jpg"],
            checklist_data={},
            visit_location="Village B",
        ))
        db.commit()
        return producer.id
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# P0-1 — XSS stocke via le formulaire public de signalement
# ════════════════════════════════════════════════════════════════════════════

# Charges utiles classiques : balise directe, attribut d'evenement, sortie
# d'attribut, sortie de balise <option>, protocole javascript:.
XSS_PAYLOADS = [
    "<script>window.__xss=1</script>",
    "<img src=x onerror=window.__xss=1>",
    '"><svg onload=window.__xss=1>',
    "</option><script>window.__xss=1</script>",
    "<iframe src=javascript:window.__xss=1>",
]


def _public_token(client, headers) -> str:
    """Jeton public de signalement de la cooperative de l'utilisateur."""
    me = client.get("/me", headers=headers)
    assert me.status_code == 200, me.text
    coop_id = me.json()["cooperative_id"]
    r = client.post(f"/cooperatives/{coop_id}/public-report-token", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["public_report_token"]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_public_complaint_payload_is_stored_and_returned_verbatim(client, payload):
    """Le texte du declarant est conserve TEL QUEL — c'est voulu.

    Un signalement est une piece a valeur probante (CLMRS / Fairtrade) : on ne
    doit pas l'assainir en base. La consequence est que la neutralisation DOIT
    se faire au rendu, cote interface — ce que garantit le test suivant.
    """
    headers = _register_admin(client, "admin@coopxss.ci", "Coop XSS")
    token = _public_token(client, headers)

    r = client.post("/public/complaints", json={
        "coop_token": token,
        "description": f"Travail des enfants signale. {payload}",
        "reporter_name": payload,
        "reporter_contact": payload,
        "location_description": payload,
    })
    assert r.status_code == 201, r.text
    reference = r.json()["reference"]

    listing = client.get("/complaints", headers=headers)
    assert listing.status_code == 200, listing.text
    stored = next(c for c in listing.json() if c["reference"] == reference)
    assert payload in stored["description"], "Le signalement doit etre conserve verbatim."


# Champs de signalement/producteur qui proviennent d'une saisie NON FIABLE
# (formulaire public sans compte, import de registre, saisie enqueteur).
UNTRUSTED_ACCESSORS = [
    "c.description",
    "c.location_description",
    "c.location_gps",
    "c.reporter_name",
    "c.reporter_contact",
    "c.findings",
    "c.referred_to",
    "c.reference",
    "c.source",
    "producer.nom_complet",
    "producer.localite",
    "p.nom_complet",
    "p.localite",
]


def _template_expressions(source: str) -> list[str]:
    """Toutes les expressions `${...}` d'un fichier (litteraux de gabarit JS)."""
    return re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", source)


def test_complaints_page_escapes_all_untrusted_fields():
    """Aucun champ non fiable ne doit etre interpole brut dans du HTML.

    La chaine d'attaque fermee par ce test :
        POST /public/complaints (sans compte)
          -> description persistee verbatim
          -> page d'administration
          -> innerHTML
          -> execution JavaScript dans la session de l'administrateur
          -> vol de avp_token / avp_refresh_token (localStorage)
    """
    source = (FRONTEND / "complaints.html").read_text(encoding="utf-8")
    faulty = []
    for expr in _template_expressions(source):
        for accessor in UNTRUSTED_ACCESSORS:
            if accessor in expr and "avpEsc(" not in expr:
                faulty.append(f"{accessor} -> ${{{expr.strip()}}}")
    assert not faulty, (
        "Champ(s) non fiable(s) injecte(s) sans echappement dans complaints.html :\n  - "
        + "\n  - ".join(sorted(set(faulty)))
        + "\nUtiliser avpEsc() (auth.js) ou textContent."
    )


def test_complaints_page_uses_shared_escape_helper():
    """La page doit s'appuyer sur le helper partage, pas sur une n-ieme copie."""
    source = (FRONTEND / "complaints.html").read_text(encoding="utf-8")
    assert "avpEsc(" in source, "complaints.html doit utiliser avpEsc() (auth.js)."


def test_shared_escape_helper_neutralizes_html():
    """avpEsc doit exister dans auth.js et neutraliser < > & \" '."""
    source = (FRONTEND / "auth.js").read_text(encoding="utf-8")
    assert "function avpEsc(" in source, "auth.js doit exposer avpEsc()."
    assert "window.avpEsc" in source, "avpEsc doit etre expose globalement."
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entity in source, f"avpEsc doit encoder {entity}."


# ════════════════════════════════════════════════════════════════════════════
# P0-2 — Lien de reinitialisation expose dans la reponse HTTP
# ════════════════════════════════════════════════════════════════════════════

def _make_user(client, email="reset@coopreset.ci", coop="Coop Reset"):
    return _register_admin(client, email, coop)


@pytest.mark.parametrize("environment", ["production", "staging", "prod", "", None])
def test_reset_link_never_exposed_outside_dev(client, monkeypatch, environment):
    """Hors dev/test explicite, aucune reponse ne doit contenir reset_link.

    Y compris — et surtout — quand SMTP est absent : c'est precisement l'etat
    dans lequel l'API distribuait des prises de controle de compte. L'absence de
    variable d'environnement doit fermer, pas ouvrir (fail-closed).
    """
    _make_user(client)
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("SMTP_HOST", raising=False)  # SMTP absent

    r = client.post("/auth/forgot-password", json={"email": "reset@coopreset.ci"})
    assert r.status_code == 200
    body = r.json()
    assert "reset_link" not in body, f"reset_link expose avec ENVIRONMENT={environment!r}"
    assert "token" not in r.text.lower() or "reset_link" not in r.text


def test_reset_link_not_exposed_in_production_when_smtp_ok(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr("app.auth.auth_routes.send_password_reset_email", lambda *a, **k: True)
    _make_user(client)

    r = client.post("/auth/forgot-password", json={"email": "reset@coopreset.ci"})
    assert r.status_code == 200
    assert "reset_link" not in r.json()


def test_reset_link_not_exposed_in_production_when_smtp_fails(client, monkeypatch):
    """SMTP configure mais l'envoi echoue : toujours aucune fuite."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr("app.auth.auth_routes.send_password_reset_email", lambda *a, **k: False)
    _make_user(client)

    r = client.post("/auth/forgot-password", json={"email": "reset@coopreset.ci"})
    assert r.status_code == 200
    assert "reset_link" not in r.json()


@pytest.mark.parametrize("environment", ["development", "test"])
def test_reset_link_available_in_explicit_dev_environment(client, monkeypatch, environment):
    """Le filet de secours « admin unique verrouille » reste disponible en dev."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    _make_user(client)

    r = client.post("/auth/forgot-password", json={"email": "reset@coopreset.ci"})
    assert r.status_code == 200
    assert "reset_link" in r.json(), (
        "Le filet de secours doit rester disponible en environnement de dev explicite."
    )


def test_forgot_password_unknown_email_stays_generic(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    _make_user(client)

    r = client.post("/auth/forgot-password", json={"email": "inconnu@nulle-part.ci"})
    assert r.status_code == 200
    body = r.json()
    assert "reset_link" not in body, "Un email inconnu ne doit jamais produire de lien."
    assert body["status"] == "ok", "Reponse generique attendue (anti-enumeration)."


def test_forgot_password_inactive_account_stays_generic(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    _make_user(client)

    db = TestingSessionLocal()
    try:
        from app.db.models import User
        user = db.query(User).filter(User.email == "reset@coopreset.ci").first()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    r = client.post("/auth/forgot-password", json={"email": "reset@coopreset.ci"})
    assert r.status_code == 200
    body = r.json()
    assert "reset_link" not in body, "Un compte suspendu ne doit jamais produire de lien."
    assert body["status"] == "ok"


# ════════════════════════════════════════════════════════════════════════════
# P0-3 — Fuite inter-cooperatives dans CacaoGuard
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def two_coops(client):
    """Coop A (id 1) et coop B (id 2), chacune avec son admin."""
    headers_a = _register_admin(client, "admin@coopa.ci", "Coop A")
    headers_b = _register_admin(client, "admin@coopb.ci", "Coop B")
    return {"a": headers_a, "b": headers_b, "coop_a_id": 1, "coop_b_id": 2}


def test_inconsistencies_do_not_leak_other_cooperative(client, two_coops):
    """Un admin de A ne doit voir aucun producteur de B dans /ai/inconsistencies."""
    _seed_coop_b_social_case(two_coops["coop_b_id"])

    r = client.get("/ai/inconsistencies", headers=two_coops["a"])
    assert r.status_code == 200, r.text
    assert COOP_B_MARKER not in r.text, (
        "FUITE INTER-COOPERATIVES : /ai/inconsistencies expose un producteur de la coop B "
        "a un administrateur de la coop A."
    )


def test_inconsistencies_still_visible_from_owning_cooperative(client, two_coops):
    """Non-regression metier : B doit toujours voir SES propres incoherences."""
    _seed_coop_b_social_case(two_coops["coop_b_id"])

    r = client.get("/ai/inconsistencies", headers=two_coops["b"])
    assert r.status_code == 200, r.text
    assert r.json()["total"] > 0, "La coop B doit voir ses propres incoherences."
    assert COOP_B_MARKER in r.text, "Le producteur de B doit rester visible depuis B."


def test_due_diligence_report_does_not_leak_other_cooperative(client, two_coops):
    """Le rapport de diligence raisonnee de A ne doit citer aucun producteur de B.

    Ce rapport est exporte en PDF et transmis aux acheteurs europeens : une fuite
    y est aussi un incident contractuel, pas seulement technique.
    """
    _seed_coop_b_social_case(two_coops["coop_b_id"])

    r = client.get("/compliance/report", headers=two_coops["a"])
    assert r.status_code == 200, r.text
    assert COOP_B_MARKER not in r.text, (
        "FUITE INTER-COOPERATIVES : /compliance/report expose un producteur de la coop B."
    )


def test_due_diligence_report_remains_functional(client, two_coops):
    """Non-regression metier : le rapport reste complet pour sa propre coop."""
    _seed_coop_b_social_case(two_coops["coop_b_id"])

    r = client.get("/compliance/report", headers=two_coops["b"])
    assert r.status_code == 200, r.text
    report = r.json()
    assert "summary" in report or "indicators" in report or report, "Rapport vide."
    assert COOP_B_MARKER in r.text, "B doit voir ses propres constats dans son rapport."


def test_alert_checks_do_not_leak_other_cooperative(client, two_coops):
    """POST /alerts/run-checks ne doit pas renvoyer les alertes des autres coops.

    Les messages d'alerte contiennent le nom du producteur ou de l'enfant.
    """
    _seed_coop_b_social_case(two_coops["coop_b_id"], overdue=True)

    r = client.post("/alerts/run-checks", headers=two_coops["a"])
    assert r.status_code == 200, r.text
    assert COOP_B_MARKER not in r.text, (
        "FUITE INTER-COOPERATIVES : /alerts/run-checks renvoie une alerte nommant "
        "un producteur de la coop B a un administrateur de la coop A."
    )


def test_alert_checks_still_generate_alerts_for_own_cooperative(client, two_coops):
    """Non-regression metier : B genere bien ses propres alertes."""
    _seed_coop_b_social_case(two_coops["coop_b_id"], overdue=True)

    r = client.post("/alerts/run-checks", headers=two_coops["b"])
    assert r.status_code == 200, r.text
    assert r.json()["reviewed_items"] > 0, "La coop B doit voir ses propres retards."
    assert COOP_B_MARKER in r.text, "L'alerte de B doit nommer son producteur."


def test_inconsistencies_engine_is_fail_closed_without_cooperative():
    """Un appel sans cooperative ne doit JAMAIS signifier « toutes les coops ».

    C'est la propriete structurelle : la signature ambigue (None = global) est la
    cause racine de la fuite, pas seulement la requete oubliee.
    """
    from app.api.cacaoguard_ops_routes import detect_cacaoguard_inconsistencies

    db = TestingSessionLocal()
    try:
        assert detect_cacaoguard_inconsistencies(db, None) == [], (
            "detect_cacaoguard_inconsistencies(db, None) doit etre fail-closed."
        )
    finally:
        db.close()
