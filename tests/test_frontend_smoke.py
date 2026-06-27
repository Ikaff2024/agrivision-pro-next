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
        "generateMissingBoundaries",  # génération en masse des délimitations (P3 scale)
        "recomputeEudr",              # recompute en masse des scores EUDR (P3 scale)
    ],
    "lots.html": [
        "openLot",
        "grantLotWaiver",   # dérogation export en lot (P3 scale)
        "renderSocialAlert",  # alerte sociale (travail enfant) dissociée de l'EUDR
    ],
    "veille.html": [
        "loadMarket",   # veille marché (existant)
        "loadVeille",   # veille réglementaire open-source (digest + items)
        "ingestVeille",
        "setVeilleFilter",   # filtre par catégorie (topic) du moteur open-source
    ],
    "direction.html": [
        "loadDirection",
        "loadAiSummary",     # résumé exécutif IA (réaffectation du moteur)
    ],
    "plantation_detail.html": [
        "renderEudrCard",
        "downloadDdsPdf",
        "openEditModal",        # édition de plantation (corrige le manque région)
        "savePlantationEdit",
        "saveDefoCheck",        # contrôle déforestation EUDR-01b
        "renderCertCard",       # certifications de la parcelle (ajout/retrait)
    ],
    "plantations.html": [
        "renderData",   # rendu de la liste paginée serveur (P2 scale)
        "EUDR_CLS",     # badges EUDR (désormais en ligne dans renderData, plus de fetch séparé)
    ],
    "producers.html": [
        "openEditProducer",   # édition d'un producteur (PUT)
        "submitProducer",     # modale duale create/edit
        "renderColMenu",      # sélecteur de colonnes
        "setCol",
        "exportProducersCsv", # export CSV/Excel (tous producteurs filtrés)
    ],
    "achats.html": [
        "createPurchase",
        "checkDup",          # anti-doublon : alerte si une récolte existe déjà
        "linkToHarvest",     # lier l'achat à la récolte existante
    ],
    "agroforestry.html": [
        "onPlSearch",            # recherche de plantations dans la liste
        "renderPlantationList",
        "selectPlantation",
    ],
    "monitoring.html": [
        "createVisit",
        "submitComplete",
        "captured_latitude",     # géo-horodatage envoyé à la clôture
    ],
    "risk_assessment.html": [
        "producer-select",   # filtre producteur amont (évite de défiler des milliers d'enfants)
        "onProducerChange",
        "loadProducers",
        "grabRaGps",          # géo-horodatage anti-fraude (Phase B) à la validation
        "captured_latitude",
    ],
    "diagnostic.html": [
        "runDiagnostic",
        "grabDiagGps",        # géo-horodatage anti-fraude (Phase B) à la saisie
        "captured_latitude",
    ],
    "farmforce.html": [
        "foodSecurity",          # vivrier/élevage (revenu vital)
        "householdExpenses",     # dépenses ménage
        "editAssessment",        # reprise/édition d'un livret
        "net_income",            # revenu net disponible
        "downloadLivret",        # export PDF du livret
        "li-verdict",            # verdict revenu vital (Living Income)
        "exportAssessmentsCsv",  # export CSV (Excel) de l'historique revenu vital
    ],
    "children.html": [
        "deleteChild",           # suppression d'un enfant en doublon (admin)
        "exportChildrenCsv",     # export CSV (Excel) de la sélection
        "setChildrenView",       # bascule vue cartes / liste
        "renderChildrenList",    # vue liste (tableau) filtrable
        "populateParentFilter",  # filtre par parent (producteur)
        "filter-parent",
    ],
    "ssrte.html": [
        "addMember",          # tableau membres du ménage (Fiche B)
        "memberRows",
        "members-rows",
        "HAZARD_TASKS",       # tâches dangereuses par enfant 5-17
        "downloadFicheB",     # export PDF de la Fiche B
        "addVisitChild",      # tableau enfants structuré (Fiche C)
        "downloadFicheC",     # export PDF de la Fiche C
        "captured_latitude",  # géo-horodatage envoyé à la création de visite SSRTE
        "communityServices",  # accès aux services (Fiche A)
        "downloadFicheA",     # export PDF de la Fiche A
    ],
    "admin.html": [
        "loadCoopProfile",     # édition nom + responsables de la coopérative
        "saveCoopProfile",
        "addManagerRow",
        "uploadLogo",          # logo coop (existant)
    ],
    "remediation.html": [
        "submitCompleteAction",
        "onCaFilesChange",       # pièce jointe de preuve à la clôture d'action
        "ca-files",
    ],
    "certification.html": [
        "loadCoverage",        # couverture par standard
        "loadRegister",        # registre certifié filtrable
        "exportRegisterCsv",   # export CSV du registre
        "bulkAssign",          # affectation en masse
    ],
    "complaints.html": [],  # existence suffit
    "owner.html": [
        "loadAiCost",          # carte coût de revient IA (API Claude) par coopérative
        "renderAiCost",
        "loadAiProvider",      # sélecteur de fournisseur IA (runtime, propriétaire)
        "saveAiProvider",
    ],
    "import.html": [
        "loadImportHistory",   # historique des imports
        "cancelImport",        # annulation d'un import erroné (lot d'import)
    ],
    "auth.js": [
        "setupNotificationWidget",
        "refreshNotifBadge",
        "startTokenAutoRefresh",   # refresh proactif du jeton (anti-déconnexion 2h)
        "ensureFreshToken",
        "openChangePassword",      # changer son propre mot de passe (self-service)
        "submitChangePassword",
        "avpGeoBadge",             # badge géo-horodatage anti-fraude (helper partagé)
        "avpExportCsv",            # export CSV/Excel partagé (BOM UTF-8)
        "avpGateMetricsByPlan",    # masque les métriques hors plan (dashboard/direction)
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
