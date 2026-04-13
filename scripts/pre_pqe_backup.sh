#!/usr/bin/env bash
# Phase 16 pre-migration backup script.
#
# Purpose: Creates a full pg_dump -Fc archive of the Axiom database BEFORE
# migration 022 executes its TRUNCATE of user-data tables (D-20, D-23).
#
# This script MUST be run before `alembic upgrade 022` is executed.
# The dump file can be used by scripts/pqe_rollback.sh to restore the
# database to its pre-PQE state if the migration needs to be reversed.
#
# Usage:
#   export DATABASE_URL=postgres://neartax:<password>@localhost:5432/neartax
#   ./scripts/pre_pqe_backup.sh
#
# Output:
#   .planning/phases/16-post-quantum-encryption-at-rest/backups/pre_pqe_YYYYMMDD_HHMMSS.dump
#   Prints the dump path to stdout on success.
#
# Requirements: pg_dump must be in PATH (standard on any system with Postgres client tools)

set -euo pipefail

# DATABASE_URL is required — fail loudly if not set
: "${DATABASE_URL:?DATABASE_URL must be set (e.g. postgres://neartax:<pw>@localhost:5432/neartax)}"

# Backup directory — relative to the script location, resolves to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/../.planning/phases/16-post-quantum-encryption-at-rest/backups"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Ensure backups directory is in .gitignore (T-16-23: backup contains plaintext user data)
GITIGNORE="${SCRIPT_DIR}/../.gitignore"
if [[ -f "$GITIGNORE" ]]; then
    if ! grep -q "16-post-quantum-encryption-at-rest/backups" "$GITIGNORE" 2>/dev/null; then
        echo ".planning/phases/16-post-quantum-encryption-at-rest/backups/" >> "$GITIGNORE"
        echo "[pre_pqe_backup] Added backups/ to .gitignore (T-16-23: dump contains plaintext user data)"
    fi
fi

# Generate timestamped dump filename
STAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/pre_pqe_${STAMP}.dump"

echo "[pre_pqe_backup] Starting pg_dump backup at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[pre_pqe_backup] Database: ${DATABASE_URL%%@*}@<host-redacted>"
echo "[pre_pqe_backup] Output:   ${OUT}"
echo ""

# Run pg_dump in custom format (parallel-restorable, compressed)
pg_dump \
    --format=custom \
    --no-owner \
    --no-acl \
    --verbose \
    --file="$OUT" \
    "$DATABASE_URL" 2>&1 | grep -v "^$" | sed 's/^/[pg_dump] /' || {
    echo "[pre_pqe_backup] ERROR: pg_dump failed" >&2
    rm -f "$OUT"
    exit 1
}

# Verify dump is not empty
if [[ ! -s "$OUT" ]]; then
    echo "[pre_pqe_backup] ERROR: dump file is empty — pg_dump may have failed silently" >&2
    rm -f "$OUT"
    exit 1
fi

SIZE=$(du -h "$OUT" | cut -f1)
echo ""
echo "[pre_pqe_backup] SUCCESS"
echo "[pre_pqe_backup] Dump file: ${OUT}"
echo "[pre_pqe_backup] File size: ${SIZE}"
echo ""
echo "Next steps:"
echo "  1. Set required env vars (EMAIL_HMAC_KEY, NEAR_ACCOUNT_HMAC_KEY, TX_DEDUP_KEY,"
echo "     ACB_DEDUP_KEY, SESSION_DEK_WRAP_KEY, INTERNAL_SERVICE_TOKEN)"
echo "  2. Run: alembic upgrade 022"
echo "  3. If rollback needed: ./scripts/pqe_rollback.sh ${OUT}"
echo ""
echo "$OUT"
