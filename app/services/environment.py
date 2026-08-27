"""Environnement d'execution du serveur — source unique, FAIL-CLOSED.

Toute decision de securite qui depend de « sommes-nous en production ? » doit
passer par ici, et JAMAIS etre deduite d'un etat operationnel (SMTP configure
ou non, base SQLite ou PostgreSQL, presence d'une cle...). Un service qui tombe
en panne ne doit pas ouvrir une porte : c'est exactement le defaut qui exposait
les liens de reinitialisation de mot de passe des que SMTP disparaissait.

Regle : seule une valeur EXPLICITE de la variable `ENVIRONMENT` parmi
`development` / `test` desserre une protection. Tout le reste — production,
staging, valeur inconnue, variable absente, variable vide — est traite comme de
la production. L'oubli de configuration ferme, il n'ouvre pas.

La lecture se fait a l'APPEL (et non a l'import) pour que la valeur reste
verifiable en test et modifiable sans redemarrage du processus.
"""
from __future__ import annotations

import os

# Seuls ces environnements, nommes explicitement, autorisent les facilites de
# developpement (ex. recuperer un lien de reinitialisation sans serveur SMTP).
DEV_ENVIRONMENTS = frozenset({"development", "test"})


def current_environment() -> str:
    """Nom normalise de l'environnement courant (`production` par defaut)."""
    return (os.getenv("ENVIRONMENT") or "production").strip().lower() or "production"


def is_development() -> bool:
    """Vrai uniquement si ENVIRONMENT vaut explicitement development ou test."""
    return current_environment() in DEV_ENVIRONMENTS


def is_production() -> bool:
    """Vrai partout ailleurs — y compris si ENVIRONMENT est absente ou inconnue."""
    return not is_development()
