"""Smoke tests frontend — sans navigateur.

Objectif : attraper en CI les régressions silencieuses qui nous ont coûté du
temps en test manuel (Ctrl+Shift+R sans fin) :

  1. Le numéro de version du Service Worker (sw.js) doit correspondre au badge
     affiché sur map.html. Si on oublie de bumper l'un des deux, on ne sait plus
     si le navigateur sert le nouveau code ou un cache obsolète.
  2. Les fonctions / boutons critiques de chaque page doivent exister. Un
     copier-coller raté ou un merge qui supprime une fonction est attrapé ici,
     sans avoir à cliquer dans l'UI.

Ces tests lisent les fichiers statiques uniquement — pas de serveur, pas de DB.
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _read(name: str) -> str:
    path = FRONTEND / name
    assert path.exists(), f"Fichier frontend introuvable : {path}"
    return path.read_text(encoding="utf-8")


# ── 1. Cohérence de version Service Worker ↔ badge map.html ──────────────────
def test_sw_version_matches_map_badge():
    sw = _read("sw.js")
    m = re.search(r"CACHE_VERSION\s*=\s*'([^']+)'", sw)
    assert m, "CACHE_VERSION introuvable dans sw.js"
    sw_version = m.group(1)

    map_html = _read("map.html")
    assert sw_version in map_html, (
        f"Le badge de version de map.html ne correspond pas au Service Worker.\n"
        f"sw.js déclare CACHE_VERSION='{sw_version}' mais ce texte est absent de "
        f"map.html. Bumpe le badge #avp-version-badge pour qu'il corresponde."
    )


def test_sw_has_skip_waiting_and_claim():
    """Garantit l'activation immédiate des nouveaux déploiements (pas besoin de
    fermer tous les onglets)."""
    sw = _read("sw.js")
    assert "skipWaiting()" in sw, "sw.js doit appeler skipWaiting() à l'install"
    assert "clients.claim()" in sw, "sw.js doit appeler clients.claim() à l'activation"


# ── 2. Présence des fonctions / éléments critiques par page ──────────────────
PAGE_MARKERS = {
    "map.html": [
        "computeAreaHectaresFromLatLngs",
        "updateLiveAreaDisplay",
        "loadDeclaredHectaresHint",
        "avp-version-badge",
    ],
    "eudr.html": [
        "DDS",  # bouton/téléchargement Due Diligence Statement
    ],
    "plantation_detail.html": [
        "renderEudrCard",
        "downloadDdsPdf",
        "openEditModal",        # édition de plantation (corrige le manque région)
        "savePlantationEdit",
    ],
    "plantations.html": [
        "loadEudrBadges",
    ],
    "risk_assessment.html": [
        "producer-select",   # filtre producteur amont (évite de défiler des milliers d'enfants)
        "onProducerChange",
        "loadProducers",
    ],
    "complaints.html": [],  # existence suffit
    "auth.js": [
        "setupNotificationWidget",
        "refreshNotifBadge",
        "startTokenAutoRefresh",   # refresh proactif du jeton (anti-déconnexion 2h)
        "ensureFreshToken",
    ],
}


@pytest.mark.parametrize("page,markers", PAGE_MARKERS.items())
def test_page_contains_critical_markers(page, markers):
    content = _read(page)
    for marker in markers:
        assert marker in content, (
            f"Marqueur critique '{marker}' absent de {page} — "
            f"une fonction/bouton attendu a peut-être été supprimé."
        )


# ── 3. Les pages clés sont bien précachées par le Service Worker ─────────────
def test_key_pages_in_sw_precache():
    sw = _read("sw.js")
    for page in ("/eudr.html", "/complaints.html", "/map.html"):
        assert page in sw, (
            f"{page} absent de STATIC_ASSETS dans sw.js — "
            f"la page ne sera pas disponible hors ligne."
        )
