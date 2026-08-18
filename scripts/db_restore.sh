#!/usr/bin/env bash
# db_restore.sh — restore basketball_stats from a pg_dump custom-format file.
#
# Usage:
#   ./scripts/db_restore.sh ./data/backups/basketball_stats_20260818_180000.dump
#
# WARNING: drops and recreates the public schema — all existing data is lost.
# The DB service must be running; the backend/worker should be stopped first
# so no connections are active during the restore.
set -euo pipefail

DUMP="${1:-}"
if [[ -z "$DUMP" ]]; then
  echo "Usage: $0 <path-to-dump-file>" >&2
  exit 1
fi

if [[ ! -f "$DUMP" ]]; then
  echo "File not found: $DUMP" >&2
  exit 1
fi

echo "Restoring basketball_stats from $DUMP"
echo "  This will DROP all existing data. Ctrl-C within 5 s to abort."
sleep 5

# Drop and recreate the public schema to guarantee a clean slate.
docker compose exec -T db psql \
  --username=basketball_stats \
  --dbname=basketball_stats \
  --command="DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Restore. --no-owner so objects keep the basketball_stats owner.
docker compose exec -T db pg_restore \
  --username=basketball_stats \
  --dbname=basketball_stats \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  < "$DUMP"

echo "Done. Run 'python manage.py migrate' if the schema version changed."
