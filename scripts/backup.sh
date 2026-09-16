#!/usr/bin/env bash
# Database + media backup (T29). Cron example (daily 03:30):
#   30 3 * * * /path/to/scripts/backup.sh
set -euo pipefail

cd "$(dirname "$0")/.."
STAMP="$(date +%F_%H%M)"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

echo "[1/2] Dumping database..."
if command -v docker >/dev/null 2>&1 && docker compose ps db >/dev/null 2>&1; then
    docker compose exec -T db pg_dump -U postgres teaching_space \
        | gzip > "$BACKUP_DIR/db_$STAMP.sql.gz"
else
    # SQLite fallback (dev)
    cp db.sqlite3 "$BACKUP_DIR/db_$STAMP.sqlite3"
fi

echo "[2/2] Archiving media..."
tar -czf "$BACKUP_DIR/media_$STAMP.tar.gz" media/ 2>/dev/null || true

# Keep 14 days of backups
find "$BACKUP_DIR" -name 'db_*' -mtime +14 -delete
find "$BACKUP_DIR" -name 'media_*' -mtime +14 -delete

echo "Backup complete: $BACKUP_DIR/db_$STAMP*"
