#!/bin/bash
# ============================================================
#  TITAN OMNISCALE X v16 - Database Restore Script
#  Phase 3: VPS Deploy
#
#  Restores a PostgreSQL backup from a compressed dump.
#
#  Usage:
#    ./deploy/scripts/restore.sh /backups/titan_20250101_120000.sql.gz
# ============================================================

set -euo pipefail

BACKUP_FILE="${1:?Usage: restore.sh <backup_file.sql.gz>}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "=== TITAN OMNISCALE X Restore ==="
echo "Source: ${BACKUP_FILE}"
echo ""
echo "WARNING: This will DROP and recreate the database!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read -r

# Drop existing connections and recreate database
echo "Recreating database..."
psql \
    --host="${PGHOST:-db}" \
    --username="${PGUSER:-titan}" \
    --dbname="postgres" \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PGDATABASE:-titan_db}' AND pid <> pg_backend_pid();" \
    2>/dev/null || true

psql \
    --host="${PGHOST:-db}" \
    --username="${PGUSER:-titan}" \
    --dbname="postgres" \
    -c "DROP DATABASE IF EXISTS ${PGDATABASE:-titan_db};" \
    2>/dev/null || true

psql \
    --host="${PGHOST:-db}" \
    --username="${PGUSER:-titan}" \
    --dbname="postgres" \
    -c "CREATE DATABASE ${PGDATABASE:-titan_db} OWNER ${PGUSER:-titan};"

# Restore from backup
echo "Restoring data..."
gunzip -c "${BACKUP_FILE}" | psql \
    --host="${PGHOST:-db}" \
    --username="${PGUSER:-titan}" \
    --dbname="${PGDATABASE:-titan_db}" \
    2>&1 | tail -20

echo "=== Restore Complete ==="
