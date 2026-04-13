#!/usr/bin/env bash
# Phase 16 rollback script.
#
# Purpose: Restore the Axiom database from a pre-migration backup and
# downgrade the Alembic schema to revision 021 (pre-PQE state).
#
# This script MUST be run with a dump file created by scripts/pre_pqe_backup.sh.
# It is DESTRUCTIVE — it stops services, drops and re-creates the schema from
# the backup, and restarts services. Use only if migration 022 must be reversed.
#
# Usage:
#   export DATABASE_URL=postgres://neartax:<password>@localhost:5432/neartax
#   ./scripts/pqe_rollback.sh [/path/to/dump_file.dump]
#
#   If no dump_file argument is given, uses the latest pre_pqe_*.dump in the
#   backups directory.
#
# Environment variables:
#   DATABASE_URL            Required. Postgres connection URL.
#   DOCKER_COMPOSE          Optional. Docker Compose command (default: "docker compose -f docker-compose.prod.yml")
#
# Requires: pg_restore, alembic, docker compose (or override DOCKER_COMPOSE)

set -euo pipefail

# DATABASE_URL is required
: "${DATABASE_URL:?DATABASE_URL must be set}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/../.planning/phases/16-post-quantum-encryption-at-rest/backups"

# Resolve dump path from argument or latest backup
DUMP_PATH="${1:-}"
if [[ -z "$DUMP_PATH" ]]; then
    DUMP_PATH=$(ls -1t "${BACKUP_DIR}"/pre_pqe_*.dump 2>/dev/null | head -n 1 || true)
fi

if [[ -z "$DUMP_PATH" || ! -f "$DUMP_PATH" ]]; then
    echo "[pqe_rollback] ERROR: No backup dump found." >&2
    echo "[pqe_rollback] Expected: ${BACKUP_DIR}/pre_pqe_*.dump" >&2
    echo "[pqe_rollback] Create one with: ./scripts/pre_pqe_backup.sh" >&2
    exit 1
fi

echo "[pqe_rollback] PQE Rollback — Phase 16 Migration Reversal"
echo "[pqe_rollback] Restore dump: ${DUMP_PATH}"
echo "[pqe_rollback] Database:     ${DATABASE_URL%%@*}@<host-redacted>"
echo ""
echo "WARNING: This will:"
echo "  1. Stop api, auth-service, and indexer containers"
echo "  2. Downgrade Alembic schema to revision 021 (pre-PQE)"
echo "  3. Run pg_restore --clean --if-exists (drops/recreates schema objects)"
echo "  4. Restart services"
echo ""
echo "All data written AFTER the backup was taken will be lost."
echo ""
read -r -p "Type YES to proceed with rollback (or anything else to abort): " CONFIRM

if [[ "$CONFIRM" != "YES" ]]; then
    echo "[pqe_rollback] Aborted — no changes made."
    exit 1
fi

echo ""
echo "[pqe_rollback] Starting rollback at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Docker Compose command (override with DOCKER_COMPOSE env var for dev)
COMPOSE="${DOCKER_COMPOSE:-docker compose -f docker-compose.prod.yml}"

# Step 1: Stop services that write to the database
echo ""
echo "[pqe_rollback] Step 1: Stopping api, auth-service, indexer..."
$COMPOSE stop api auth-service indexer 2>&1 | sed 's/^/[compose] /' || {
    echo "[pqe_rollback] Warning: Could not stop all services (continuing anyway)"
}

# Step 2: Downgrade Alembic schema to 021 (schema only — table drops/column restores)
echo ""
echo "[pqe_rollback] Step 2: Alembic downgrade to 021..."
alembic downgrade 021 2>&1 | sed 's/^/[alembic] /' || {
    echo "[pqe_rollback] Warning: alembic downgrade returned non-zero (may be partly done)"
    echo "[pqe_rollback] Continuing to pg_restore which will overwrite the schema"
}

# Step 3: Restore from backup dump
echo ""
echo "[pqe_rollback] Step 3: pg_restore from ${DUMP_PATH}..."
pg_restore \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    --verbose \
    --dbname="$DATABASE_URL" \
    "$DUMP_PATH" 2>&1 | sed 's/^/[pg_restore] /' || {
    # pg_restore returns non-zero even on partial success (harmless "already exists" errors)
    echo "[pqe_rollback] Note: pg_restore exited non-zero (check output above for actual errors)"
}

# Step 4: Restart services
echo ""
echo "[pqe_rollback] Step 4: Restarting services..."
$COMPOSE up -d api auth-service indexer 2>&1 | sed 's/^/[compose] /' || {
    echo "[pqe_rollback] ERROR: Could not restart services — investigate docker compose status" >&2
    exit 1
}

echo ""
echo "[pqe_rollback] Rollback complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[pqe_rollback] Verify: psql \$DATABASE_URL -c 'SELECT COUNT(*) FROM transactions;'"
echo "[pqe_rollback] Verify: alembic current"
echo ""
echo "If service health checks fail:"
echo "  ./scripts/healthcheck.sh"
