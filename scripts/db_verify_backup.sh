#!/usr/bin/env bash
# db_verify_backup.sh — prove a backup is restorable, without touching live data.
#
# Restores a pg_dump custom-format file into a throw-away PostgreSQL container
# and compares the exact row count of every table with the live database.
#
# Usage:
#   ./scripts/db_verify_backup.sh                 # takes a fresh dump, then verifies it
#   ./scripts/db_verify_backup.sh path/to.dump    # verifies an existing dump
#
# Environment: DC (compose command, see db_backup.sh), PG_IMAGE (default
# postgres:16-alpine; keep it equal to the db service image).
# A dump older than the live data legitimately differs (rows added since); the
# fresh-dump mode is meant to be run while no ingestion is writing.
set -euo pipefail

DC="${DC:-docker compose}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="${1:-}"
CLEAN_DUMP=0

if [[ -z "$DUMP" ]]; then
  STEM="verify_$(date +%Y%m%d_%H%M%S)"
  BACKUP_DIR="${BACKUP_DIR:-$ROOT/data/backups}" "$ROOT/scripts/db_backup.sh" "$STEM" >/dev/null
  DUMP="${BACKUP_DIR:-$ROOT/data/backups}/${STEM}.dump"
  CLEAN_DUMP=1
fi
[[ -f "$DUMP" ]] || { echo "File not found: $DUMP" >&2; exit 1; }

NAME="pgverify-$$"
cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  if [[ "$CLEAN_DUMP" -eq 1 ]]; then rm -f "$DUMP"; fi
}
trap cleanup EXIT

COUNTS_SQL="select table_name || ' ' || (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
            from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1;"

echo "Starting scratch PostgreSQL ($PG_IMAGE)"
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=verify -e POSTGRES_USER=basketball_stats \
  -e POSTGRES_DB=basketball_stats "$PG_IMAGE" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$NAME" pg_isready -U basketball_stats -d basketball_stats >/dev/null 2>&1 && break
  sleep 1
done
# pg_isready can answer during the image's init phase; wait until queries work.
for _ in $(seq 1 30); do
  docker exec "$NAME" psql -U basketball_stats -d basketball_stats -Atc "select 1" >/dev/null 2>&1 && break
  sleep 1
done

echo "Restoring $(basename "$DUMP") into the scratch database"
docker exec -i "$NAME" pg_restore --username=basketball_stats --dbname=basketball_stats \
  --no-owner --no-privileges --exit-on-error < "$DUMP"

LIVE="$($DC exec -T db psql -U basketball_stats -d basketball_stats -At -c "$COUNTS_SQL" | tr -d '\r')"
RESTORED="$(docker exec "$NAME" psql -U basketball_stats -d basketball_stats -At -c "$COUNTS_SQL")"

TABLES="$(echo "$RESTORED" | grep -c .)"
if [[ "$LIVE" == "$RESTORED" ]]; then
  echo "OK: $TABLES tables restored; every row count matches the live database."
else
  echo "MISMATCH between live and restored row counts (live < > restored):" >&2
  diff <(echo "$LIVE") <(echo "$RESTORED") >&2 || true
  exit 1
fi
