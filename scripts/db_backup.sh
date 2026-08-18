#!/usr/bin/env bash
# db_backup.sh — dump the basketball_stats PostgreSQL database.
#
# Usage:
#   ./scripts/db_backup.sh            # timestamped dump in ./data/backups/
#   ./scripts/db_backup.sh my_name    # custom stem: ./data/backups/my_name.dump
#
# The dump is in PostgreSQL custom format (-Fc), which pg_restore can load
# selectively and in parallel. Human-readable SQL: change -Fc to -Fp and
# rename the file to .sql.
set -euo pipefail

BACKUP_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/backups"
mkdir -p "$BACKUP_DIR"

STEM="${1:-basketball_stats_$(date +%Y%m%d_%H%M%S)}"
OUT="$BACKUP_DIR/${STEM}.dump"

echo "Backing up basketball_stats → $OUT"

docker compose exec -T db pg_dump \
  --username=basketball_stats \
  --dbname=basketball_stats \
  --format=custom \
  --no-owner \
  --no-privileges \
  > "$OUT"

SIZE=$(du -sh "$OUT" | cut -f1)
echo "Done. $SIZE written to $OUT"
