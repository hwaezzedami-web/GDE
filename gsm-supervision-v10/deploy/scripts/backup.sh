#!/usr/bin/env bash
# Sauvegarde de la base (format custom pg_dump, compressé) avec rotation.
#   Docker : ./deploy/scripts/backup.sh            (utilise le conteneur db)
#   Hôte   : MODE=host PGHOST=… PGUSER=… PGDATABASE=… ./deploy/scripts/backup.sh
# Planification conseillée (cron, chaque nuit à 2 h) :
#   0 2 * * * cd /opt/gsm-supervision && ./deploy/scripts/backup.sh >> /var/log/gsm-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/../.."
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p backups
if [[ "${MODE:-docker}" == "docker" ]]; then
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6' > "backups/gsm_${STAMP}.dump"
else
  pg_dump -Fc -Z 6 > "backups/gsm_${STAMP}.dump"
fi
test -s "backups/gsm_${STAMP}.dump"
find backups -name 'gsm_*.dump' -mtime +"${RETENTION_DAYS}" -delete
echo "$(date -Is) sauvegarde OK : backups/gsm_${STAMP}.dump ($(du -h "backups/gsm_${STAMP}.dump" | cut -f1))"
