"""Garde-fou : aucune donnee client reelle ne doit entrer dans le depot PUBLIC.

Ce test tourne dans la CI a chaque push (job « Lint & Tests », vert). Il inspecte
les fichiers SUIVIS PAR GIT — pas le disque : les artefacts locaux et les
tmp_path de pytest ne le concernent pas — et echoue si un document interdit
reapparait.

POLITIQUE : document binaire INTERDIT par defaut, document public AUTORISE
EXPLICITEMENT. Tout PDF, DOCX, XLSX, CSV ou dump de base versionne doit figurer
dans `ALLOWED_DOCUMENTS` ci-dessous, classe par finalite. Il n'y a pas de
categorie « divers » : un document qu'on ne sait pas classer n'a pas sa place
dans un depot public.

Pour AUTORISER un nouveau document, il faut deux gestes : l'ajouter ici ET
ajouter l'exception correspondante dans `.gitignore`. Un test verifie que les
deux listes coincident, pour qu'aucune ne derive de l'autre.

Perimetre volontairement etroit et lisible — ce n'est pas un DLP. Il repond a
une seule question : « un document client reel a-t-il ete recommis par
inadvertance ? »
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _tracked_files() -> list[str]:
    """Fichiers suivis par git, chemins relatifs a la racine du depot."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


# ════════════════════════════════════════════════════════════════════════════
# Allowlist documentaire — classee par FINALITE
# ════════════════════════════════════════════════════════════════════════════

# 1. Specimens officiels et formulaires VIERGES.
#    Verifies sans aucun champ rempli sur l'integralite de leurs pages
#    (aucun telephone, date renseignee, coordonnee GPS ni numero long).
#    Les SPECIMEN_* portent des coordonnees volontairement fictives.
SPECIMENS_VIERGES = {
    "docs/SPECIMEN_SSRTE_FicheA.pdf",
    "docs/SPECIMEN_SSRTE_FicheB.pdf",
    "docs/SPECIMEN_SSRTE_FicheB_cas_sain.pdf",
    "docs/SPECIMEN_SSRTE_FicheC.pdf",
    "docs/SPECIMEN_SSRTE_FicheC_cas_conforme.pdf",
    "docs/ANNEXE_SPECIMENS_SSRTE.pdf",
    "docs/F1 PROFILLAGE DE MENAGE.pdf",
    "docs/SSRTE FICHE A - FO.pdf",
    "docs/SSRTE FICHE C - VISITE DES PLANTATIONS-1.pdf",
}

# 2. Documentation produit publique — redigee par l'editeur.
#    La plupart sont generees depuis une source .md/.html versionnee.
DOCUMENTATION_PUBLIQUE = {
    "docs/PRESENTATION_MODULES.pdf",
    "docs/PRESENTATION_CACAOGUARD.pdf",
    "docs/ONEPAGER_ICI_AgriVision.pdf",
    "docs/OBJECTIONS_ICI.pdf",
    "docs/CHECKLIST_DEMO_ICI.pdf",
    "docs/CHECKLIST_MISE_EN_REGLE.pdf",
    "docs/COURRIER_ICI.pdf",
    "docs/REFERENTIEL_CONFORMITE_DONNEES.pdf",
    "docs/VISION_JUMEAU_NUMERIQUE.pdf",
    "docs/Manuel_Utilisateur_AgriVision_Pro_CacaoGuard_FarmForce.docx",
    "docs/Manuel_Formation_AgriVision_Pro.docx",
    "frontend/AgriVision_Pro_Guide_Utilisateur_v1_5_0.docx",
}

# 3. Fixtures synthetiques — generees par un script du depot.
FIXTURES_SYNTHETIQUES = {
    "e2e/fixtures/registre_demo_e2e.xlsx",      # e2e/fixtures/make_registry.py
}

ALLOWED_DOCUMENTS = SPECIMENS_VIERGES | DOCUMENTATION_PUBLIQUE | FIXTURES_SYNTHETIQUES

# Extensions soumises a la politique « interdit sauf allowlist ».
DOCUMENT_EXTENSIONS = {
    # tableurs et donnees tabulaires
    ".xlsx", ".xlsm", ".xls", ".csv", ".tsv",
    # bases et exports
    ".db", ".sqlite", ".sqlite3", ".sql", ".dump", ".parquet",
    # documents bureautiques et imprimables
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods",
}


# ── Noms de fichiers clients connus ─────────────────────────────────────────
# Motifs (insensibles a la casse) qui ont deja designe des donnees reelles.
FORBIDDEN_FILENAME_PATTERNS = [
    r"registre\s*ft\s*yeyasso",
    r"registre\s*ft\s*coop\s*test",
    r"farm\s*force\s*yeyasso",
    r"_locked_yeyasso",
    r"\bdigital data capturing tool cocoa\.FR_",
    r"\bDD farm records cocoa\.FR\.",
]

# ── Secrets ─────────────────────────────────────────────────────────────────
FORBIDDEN_EXACT = {".env", ".env.local", ".env.production", ".env.prod"}


# ════════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════════

def test_no_known_client_file_is_tracked():
    """Aucun fichier au nom d'un client connu ne doit etre suivi."""
    offenders = [
        path for path in _tracked_files()
        if any(re.search(pat, path, re.IGNORECASE) for pat in FORBIDDEN_FILENAME_PATTERNS)
    ]
    assert not offenders, (
        "Fichier(s) de donnees client reintroduit(s) dans le depot public :\n  - "
        + "\n  - ".join(offenders)
        + "\n\nCes fichiers contiennent des donnees personnelles de producteurs. "
          "Utilisez les generateurs de tests/fixtures/ a la place."
    )


def test_every_tracked_document_is_explicitly_allowed():
    """Document binaire interdit par defaut, publiable seulement si liste ici."""
    offenders = sorted(
        path for path in _tracked_files()
        if Path(path).suffix.lower() in DOCUMENT_EXTENSIONS
        and path not in ALLOWED_DOCUMENTS
    )
    assert not offenders, (
        "Document(s) binaire(s) non autorise(s) :\n  - " + "\n  - ".join(offenders)
        + "\n\nLe depot est PUBLIC. Pour publier un document, classez-le par "
          "finalite dans ALLOWED_DOCUMENTS (tests/test_no_client_data.py) ET "
          "ajoutez l'exception correspondante dans .gitignore.\n"
          "S'il contient — ou peut contenir — des donnees client : ne le "
          "committez pas."
    )


def test_allowlist_has_no_stale_entry():
    """Un document retire du depot doit sortir de l'allowlist.

    Sans cette verification, l'allowlist se transforme en liste de souhaits et
    perd sa valeur de point de decision.
    """
    tracked = set(_tracked_files())
    stale = sorted(ALLOWED_DOCUMENTS - tracked)
    assert not stale, (
        "Entree(s) d'allowlist ne correspondant a aucun fichier suivi :\n  - "
        + "\n  - ".join(stale)
        + "\n\nRetirez-les de ALLOWED_DOCUMENTS et de .gitignore."
    )


def test_gitignore_exceptions_match_the_allowlist():
    """`.gitignore` et l'allowlist doivent designer exactement les memes fichiers.

    Les deux listes sont le double point de decision de la politique. Si elles
    divergent, l'une des deux ment : soit un document autorise ici est en
    realite ignore par git, soit `.gitignore` reautorise un document que ce
    test refuse.
    """
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    exceptions = {
        line[1:].strip()
        for line in gitignore.splitlines()
        if line.startswith("!") and Path(line[1:].strip()).suffix.lower() in DOCUMENT_EXTENSIONS
    }
    # Les exceptions par motif (tests/fixtures/*.xlsx) couvrent des fichiers
    # generes a la volee : on les ecarte de la comparaison nominative.
    exceptions = {e for e in exceptions if "*" not in e}

    missing_in_gitignore = sorted(ALLOWED_DOCUMENTS - exceptions)
    missing_in_allowlist = sorted(exceptions - ALLOWED_DOCUMENTS)
    assert not missing_in_gitignore and not missing_in_allowlist, (
        "Desynchronisation entre .gitignore et ALLOWED_DOCUMENTS.\n"
        f"Autorises ici mais absents de .gitignore : {missing_in_gitignore}\n"
        f"Reautorises par .gitignore mais absents d'ici : {missing_in_allowlist}"
    )


def test_no_env_file_is_tracked():
    """Aucun .env reel — seul .env.example est legitime."""
    offenders = [p for p in _tracked_files() if Path(p).name in FORBIDDEN_EXACT]
    assert not offenders, (
        "Fichier(s) d'environnement suivi(s) : " + ", ".join(offenders)
    )


def test_generators_exist_for_replaced_client_files():
    """Les generateurs synthetiques doivent rester presents.

    Sans eux, la tentation de reintroduire le fichier client revient.
    """
    for generator in (
        "tests/fixtures/generate_large_registry.py",
        "tests/fixtures/generate_farmforce_workbook.py",
        "e2e/fixtures/make_registry.py",
    ):
        assert (REPO / generator).exists(), f"Generateur manquant : {generator}"


@pytest.mark.parametrize("pattern,sample", [
    (r"registre\s*ft\s*yeyasso", "docs/Registre FT YEYASSO 2025-2026 Act .xlsx"),
    (r"registre\s*ft\s*coop\s*test", "docs/Registre FT Coop test 2 2025-2026 Act.xlsx"),
    (r"farm\s*force\s*yeyasso", "farm Force yeyasso -22._23pdf.pdf"),
    (r"_locked_yeyasso", "docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx"),
    (r"\bdigital data capturing tool cocoa\.FR_",
     "docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx"),
    (r"\bDD farm records cocoa\.FR\.", "docs/DD farm records cocoa.FR.2025-2026.pdf"),
])
def test_forbidden_patterns_actually_match_the_files_they_target(pattern, sample):
    """Auto-test : chaque motif doit reconnaitre le nom qu'il vise.

    Un motif casse laisserait passer le fichier sans que personne ne le voie.
    """
    assert pattern in FORBIDDEN_FILENAME_PATTERNS, (
        f"Motif {pattern!r} absent de FORBIDDEN_FILENAME_PATTERNS."
    )
    assert re.search(pattern, sample, re.IGNORECASE), (
        f"Le motif {pattern!r} ne reconnait plus le fichier qu'il doit bloquer."
    )
