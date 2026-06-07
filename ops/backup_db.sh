#!/usr/bin/env bash
# Sauvegarde PostgreSQL chiffrée — manuelle (avant une opération sensible : mise en
# prod, migration, import massif…). Voir docs/BACKUP_DR.md.
#
# Prérequis : Docker + openssl. Exécuter sous WSL / Linux / Git-Bash.
# Usage :
#   BACKUP_PASSPHRASE='phrase-secrete' \
#   DATABASE_URL='postgresql://…proxy.rlwy.net:PORT/railway' \
#   ./ops/backup_db.sh [dossier_sortie]
#
# La chaîne DATABASE_URL doit être la chaîne PUBLIQUE (joignable hors Railway).
set -euo pipefail

: "${DATABASE_URL:?Définir DATABASE_URL (chaîne PUBLIQUE Railway)}"
: "${BACKUP_PASSPHRASE:?Définir BACKUP_PASSPHRASE (phrase de chiffrement)}"

OUT="${1:-.}"
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="$OUT/avp-${STAMP}.dump.enc"

echo "Sauvegarde en cours (pg_dump via docker postgres:16, chiffrement AES-256)…"
docker run --rm -e PGCONNECT_TIMEOUT=30 postgres:16 \
  pg_dump --no-owner --no-privileges -Fc "$DATABASE_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -out "$DEST" -pass env:BACKUP_PASSPHRASE

SIZE="$(stat -c%s "$DEST" 2>/dev/null || stat -f%z "$DEST")"
if [ "${SIZE:-0}" -lt 1000 ]; then
  echo "ERREUR : sauvegarde anormalement petite (<1 Ko) — le dump a probablement échoué." >&2
  exit 1
fi
echo "OK → $DEST (${SIZE} octets)"
echo "Conservez la phrase secrète : sans elle, ce fichier est irrécupérable."
