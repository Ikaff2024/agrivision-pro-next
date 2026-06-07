#!/usr/bin/env bash
# Restauration d'une sauvegarde chiffrée AgriVision Pro dans une base de DESTINATION.
# Voir docs/BACKUP_DR.md.
#
# Prérequis : Docker + openssl. Exécuter sous WSL / Linux / Git-Bash.
# Usage :
#   BACKUP_PASSPHRASE='phrase-secrete' \
#   TARGET_DATABASE_URL='postgresql://…(base de DESTINATION)…' \
#   ./ops/restore_db.sh chemin/vers/avp-AAAAMMJJ-HHMMSS.dump.enc
#
# ⚠️ --clean --if-exists : REMPLACE les objets existants dans la base cible.
#    Restaurez de préférence dans une base NEUVE pour ne pas écraser des données vivantes.
set -euo pipefail

ENC="${1:?Usage: restore_db.sh <fichier.dump.enc>}"
: "${BACKUP_PASSPHRASE:?Définir BACKUP_PASSPHRASE (phrase de chiffrement)}"
: "${TARGET_DATABASE_URL:?Définir TARGET_DATABASE_URL (base de DESTINATION)}"
[ -f "$ENC" ] || { echo "Fichier introuvable : $ENC" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Déchiffrement…"
openssl enc -d -aes-256-cbc -pbkdf2 -in "$ENC" -out "$TMP/db.dump" -pass env:BACKUP_PASSPHRASE

echo "Restauration vers la base cible (pg_restore via docker postgres:16)…"
docker run --rm -i -e PGCONNECT_TIMEOUT=30 -v "$TMP:/b" postgres:16 \
  pg_restore --no-owner --no-privileges --clean --if-exists -d "$TARGET_DATABASE_URL" /b/db.dump

echo "Terminé. Repointez ensuite l'API (DATABASE_URL) vers cette base, puis vérifiez /health."
