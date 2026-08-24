#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 1; }

BACKUP_DIR="${1:-$PROJECT_DIR/backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATABASE="$(sed -n 's/^DATABASE_NAME=//p' .env | tail -n 1)"
DATABASE="${DATABASE:-blue_me}"
TARGET="$BACKUP_DIR/blue-me-$STAMP.sql.gz"

if grep -q '^DATABASE_MODE=external$' .env; then
  command -v mysqldump >/dev/null 2>&1 || command -v mariadb-dump >/dev/null 2>&1 || { echo "mysqldump or mariadb-dump is required" >&2; exit 1; }
  DUMP_BIN="$(command -v mariadb-dump || command -v mysqldump)"
  HOST="$(sed -n 's/^DATABASE_HOST=//p' .env | tail -n 1)"
  PORT="$(sed -n 's/^DATABASE_PORT=//p' .env | tail -n 1)"
  USER="$(sed -n 's/^DATABASE_USER=//p' .env | tail -n 1)"
  PASSWORD="$(sed -n 's/^DATABASE_PASSWORD=//p' .env | tail -n 1)"
  MYSQL_PWD="$PASSWORD" "$DUMP_BIN" --single-transaction --routines --triggers -h "$HOST" -P "${PORT:-3306}" -u "$USER" "$DATABASE" | gzip -9 >"$TARGET"
else
  docker compose exec -T db sh -c 'exec mysqldump --single-transaction --routines --triggers -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' | gzip -9 >"$TARGET"
fi
gzip -t "$TARGET"
chmod 600 "$TARGET"
echo "Verified backup: $TARGET"
