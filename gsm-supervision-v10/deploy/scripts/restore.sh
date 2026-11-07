#!/usr/bin/env bash
# Restauration d'une sauvegarde : ./deploy/scripts/restore.sh backups/gsm_YYYYMMDD_HHMMSS.dump
# ATTENTION : remplace le contenu actuel de la base. Les services API/collecte sont arrêtés pendant l'opération.
set -euo pipefail
cd "$(dirname "$0")/../.."
FILE="${1:?Usage : restore.sh <fichier.dump>}"
test -s "$FILE"
read -r -p "Restaurer $FILE et ÉCRASER la base actuelle ? (oui/non) " ok
[[ "$ok" == "oui" ]] || { echo "Abandon."; exit 1; }
if [[ "${MODE:-docker}" == "docker" ]]; then
  docker compose stop api collector web
  docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$FILE"
  docker compose start api collector web
else
  systemctl stop gsm-collector gsm-api
  pg_restore --clean --if-exists --no-owner -d "${PGDATABASE:?}" "$FILE"
  systemctl start gsm-api gsm-collector
fi
echo "Restauration terminée. Vérifier : curl -s http://localhost:${WEB_PORT:-8080}/api/health"
