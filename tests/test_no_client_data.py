"""Garde-fou : aucune donnee client reelle ne doit entrer dans le depot PUBLIC.

Ce test tourne dans la CI a chaque push. Il inspecte les fichiers SUIVIS PAR GIT
(pas le disque : les artefacts locaux et les tmp_path de pytest ne le concernent
pas) et echoue si l'un des motifs interdits reapparait.

Perimetre volontairement etroit et lisible — ce n'est pas un DLP. Il repond a une
seule question : « un registre coopérative reel, un export SSRTE/FarmForce, un
dump de base ou un .env a-t-il ete recommis par inadvertance ? »

Pour AUTORISER un nouveau fichier de donnees, ajoutez-le a `ALLOWED_DATA_FILES`
ci-dessous ET a l'exception correspondante dans `.gitignore`. Le double point de
decision est intentionnel : on ne contourne pas la regle par accident.
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


# ── 1. Noms de fichiers clients connus ──────────────────────────────────────
# Motifs (insensibles a la casse) qui ont deja designe des donnees reelles.
FORBIDDEN_FILENAME_PATTERNS = [
    r"registre\s*ft\s*yeyasso",
    r"farm\s*force\s*yeyasso",
    r"_locked_yeyasso",
    r"\bdigital data capturing tool cocoa\.FR_",
]

# ── 2. Extensions de donnees, avec allowlist explicite ──────────────────────
DATA_EXTENSIONS = {
    ".xlsx", ".xlsm", ".xls", ".csv", ".tsv",
    ".db", ".sqlite", ".sqlite3", ".sql", ".dump", ".parquet",
}

# Seuls ces fichiers de donnees ont le droit d'etre versionnes.
ALLOWED_DATA_FILES = {
    "e2e/fixtures/registre_demo_e2e.xlsx",          # genere par make_registry.py
    "docs/Registre FT Coop test 2 2025-2026 Act.xlsx",  # cf. note ci-dessous
}

# ── 3. Secrets et sauvegardes ───────────────────────────────────────────────
FORBIDDEN_EXACT = {".env", ".env.local", ".env.production", ".env.prod"}


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


def test_no_unexpected_data_file_is_tracked():
    """Tout fichier de donnees suivi doit figurer dans l'allowlist."""
    offenders = [
        path for path in _tracked_files()
        if Path(path).suffix.lower() in DATA_EXTENSIONS
        and path not in ALLOWED_DATA_FILES
    ]
    assert not offenders, (
        "Fichier(s) de donnees non autorise(s) :\n  - " + "\n  - ".join(offenders)
        + "\n\nSi ce fichier est une fixture SYNTHETIQUE legitime : ajoutez-le a "
          "ALLOWED_DATA_FILES (tests/test_no_client_data.py) ET a l'exception "
          "correspondante dans .gitignore.\n"
          "S'il contient des donnees reelles : ne le committez pas."
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


@pytest.mark.parametrize("pattern", FORBIDDEN_FILENAME_PATTERNS)
def test_forbidden_patterns_actually_match_the_files_they_target(pattern):
    """Auto-test : chaque motif doit reconnaitre le nom qu'il vise.

    Un motif casse laisserait passer le fichier sans que personne ne le voie.
    """
    samples = {
        r"registre\s*ft\s*yeyasso": "docs/Registre FT YEYASSO 2025-2026 Act .xlsx",
        r"farm\s*force\s*yeyasso": "farm Force yeyasso -22._23pdf.pdf",
        r"_locked_yeyasso": "docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx",
        r"\bdigital data capturing tool cocoa\.FR_": (
            "docs/digital data capturing tool cocoa.FR_locked_Yeyasso.xlsx"
        ),
    }
    assert re.search(pattern, samples[pattern], re.IGNORECASE), (
        f"Le motif {pattern!r} ne reconnait plus le fichier qu'il doit bloquer."
    )
