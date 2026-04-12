#!/bin/bash
# Account block indexer — runs the Rust binary on the host in a loop that
# backfills from the stored cursor to chain tip, then follows the chain tip
# indefinitely. Designed to run as a systemd service with Restart=always.
#
# Usage:
#   ./scripts/run_account_indexer.sh              # resume from cursor in DB
#   ./scripts/run_account_indexer.sh 100000000    # start from specific block
#
# Requires:
#   - /home/deploy/account-indexer-rs-v2 binary
#   - FASTNEAR_API_KEY in .env
#   - PostgreSQL accessible on 127.0.0.1:5433
#
# Exit behaviour:
#   - Transient errors (RPC unreachable, chunk failure) -> retry after delay
#   - Fatal errors (missing binary, bad env) -> exit non-zero, systemd restarts

set -u  # catch unset variables; no -e so we can handle errors inline

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env (systemd EnvironmentFile already sets these, but allow manual runs)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

if [ -z "${FASTNEAR_API_KEY:-}" ]; then
    echo "ERROR: FASTNEAR_API_KEY is not set. Check .env" >&2
    exit 2
fi

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "ERROR: POSTGRES_PASSWORD is not set. Check .env" >&2
    exit 2
fi

BINARY="/home/deploy/account-indexer-rs-v2"
if [ ! -x "$BINARY" ]; then
    echo "ERROR: binary not found or not executable: $BINARY" >&2
    exit 2
fi

export FASTNEAR_API_KEY
PG_PASS="$POSTGRES_PASSWORD"
export PGPASSWORD="$PG_PASS"
DATABASE_URL="postgresql://neartax:${PG_PASS}@127.0.0.1:5433/neartax"
PG_PSQL=(psql -h 127.0.0.1 -p 5433 -U neartax -q)

GENESIS=9820210
BACKFILL_CHUNK_SIZE=${BACKFILL_CHUNK_SIZE:-10000}  # backfill chunk size
LIVE_CHUNK_SIZE=${LIVE_CHUNK_SIZE:-100}            # live mode chunk size
WORKERS=${WORKERS:-16}
TIP_POLL_INTERVAL=${TIP_POLL_INTERVAL:-5}           # seconds between tip checks when caught up
ERROR_RETRY_DELAY=${ERROR_RETRY_DELAY:-15}          # seconds to wait after a transient error
LIVE_LAG_BLOCKS=${LIVE_LAG_BLOCKS:-5}               # fall behind tip by N blocks to give finality buffer

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

get_cursor() {
    "${PG_PSQL[@]}" -t -c \
        "SELECT COALESCE(last_processed_block, 0) FROM account_indexer_state WHERE id = 1;" \
        2>/dev/null | tr -d ' '
}

get_chain_tip() {
    curl -s --max-time 10 -X POST "https://rpc.mainnet.fastnear.com" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer $FASTNEAR_API_KEY" \
        -d '{"jsonrpc":"2.0","id":"1","method":"status","params":[]}' \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['latest_block_height'])" \
        2>/dev/null
}

# Process one chunk [from, to]. Returns 0 on success, non-zero on failure.
# Updates the cursor in the DB when the chunk loads successfully.
process_chunk() {
    local from=$1
    local to=$2

    local tmpfile
    tmpfile=$(mktemp /tmp/atx_chunk_XXXXXX.tsv)

    # Run the Rust binary. stdout = TSV data, stderr = progress messages.
    if ! "$BINARY" \
            --start "$from" --end "$to" \
            --workers "$WORKERS" \
            --progress-interval 2000 \
            --database-url "$DATABASE_URL" \
            > "$tmpfile"; then
        log "ERROR: Rust binary failed for chunk $from → $to"
        rm -f "$tmpfile"
        return 1
    fi

    local rows
    rows=$(wc -l < "$tmpfile")

    # COPY into staging → dedup insert into account_transactions → update cursor
    if ! "${PG_PSQL[@]}" <<EOSQL
CREATE TEMP TABLE IF NOT EXISTS atx_staging (account_int INTEGER, block_height INTEGER);
TRUNCATE atx_staging;
\copy atx_staging (account_int, block_height) FROM '$tmpfile'
INSERT INTO account_transactions (account_int, block_height)
SELECT DISTINCT account_int, block_height FROM atx_staging
ON CONFLICT DO NOTHING;
DROP TABLE atx_staging;
UPDATE account_indexer_state SET last_processed_block = $to, updated_at = NOW() WHERE id = 1;
EOSQL
    then
        log "ERROR: psql COPY/INSERT failed for chunk $from → $to"
        rm -f "$tmpfile"
        return 1
    fi

    rm -f "$tmpfile"
    echo "$rows"  # return value: row count
    return 0
}

# ──────────────────────────────────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────────────────────────────────

log "Account block indexer starting (follow mode, Restart=always compatible)"

# Allow manual override of start block on the command line
if [ $# -ge 1 ] && [ -n "$1" ]; then
    MANUAL_START=$1
    log "Manual start block requested: $MANUAL_START — updating cursor"
    "${PG_PSQL[@]}" -c "UPDATE account_indexer_state SET last_processed_block = $MANUAL_START WHERE id = 1;"
fi

# Bump genesis floor on first run (if the state table says 0, start from genesis)
CURRENT_CURSOR=$(get_cursor)
if [ -z "$CURRENT_CURSOR" ] || [ "$CURRENT_CURSOR" -lt "$GENESIS" ]; then
    log "Cursor below genesis ($CURRENT_CURSOR) — starting from $GENESIS"
    "${PG_PSQL[@]}" -c "UPDATE account_indexer_state SET last_processed_block = $GENESIS WHERE id = 1;" \
        > /dev/null
fi

# ──────────────────────────────────────────────────────────────────────────
# Main follow loop
# ──────────────────────────────────────────────────────────────────────────

TOTAL_ROWS=0
LOOP_START=$(date +%s)

while true; do
    CURSOR=$(get_cursor)
    if [ -z "$CURSOR" ]; then
        log "WARN: failed to read cursor from DB, retrying in ${ERROR_RETRY_DELAY}s"
        sleep "$ERROR_RETRY_DELAY"
        continue
    fi

    TIP=$(get_chain_tip)
    if [ -z "$TIP" ] || [ "$TIP" -le 0 ] 2>/dev/null; then
        log "WARN: failed to get chain tip, retrying in ${ERROR_RETRY_DELAY}s"
        sleep "$ERROR_RETRY_DELAY"
        continue
    fi

    # Aim for N blocks behind the tip to give blocks time to finalize
    TARGET=$((TIP - LIVE_LAG_BLOCKS))

    if [ "$CURSOR" -ge "$TARGET" ]; then
        # Caught up — wait briefly and check again
        sleep "$TIP_POLL_INTERVAL"
        continue
    fi

    BLOCKS_BEHIND=$((TARGET - CURSOR))
    # Use big chunks for backfill, small chunks when close to tip (live mode)
    if [ "$BLOCKS_BEHIND" -gt "$BACKFILL_CHUNK_SIZE" ]; then
        CHUNK_SIZE=$BACKFILL_CHUNK_SIZE
        MODE="backfill"
    else
        CHUNK_SIZE=$LIVE_CHUNK_SIZE
        MODE="live"
        if [ "$CHUNK_SIZE" -gt "$BLOCKS_BEHIND" ]; then
            CHUNK_SIZE=$BLOCKS_BEHIND
        fi
    fi

    CHUNK_FROM=$((CURSOR + 1))
    CHUNK_TO=$((CURSOR + CHUNK_SIZE))
    if [ "$CHUNK_TO" -gt "$TARGET" ]; then
        CHUNK_TO=$TARGET
    fi

    CHUNK_START_TIME=$(date +%s)
    CHUNK_ROWS=$(process_chunk "$CHUNK_FROM" "$CHUNK_TO")
    CHUNK_RC=$?
    CHUNK_END_TIME=$(date +%s)

    if [ $CHUNK_RC -ne 0 ]; then
        log "ERROR: chunk $CHUNK_FROM → $CHUNK_TO failed, retrying in ${ERROR_RETRY_DELAY}s"
        sleep "$ERROR_RETRY_DELAY"
        continue
    fi

    TOTAL_ROWS=$((TOTAL_ROWS + CHUNK_ROWS))
    CHUNK_ELAPSED=$((CHUNK_END_TIME - CHUNK_START_TIME + 1))
    CHUNK_BLOCKS=$((CHUNK_TO - CHUNK_FROM + 1))
    CHUNK_RATE=$((CHUNK_BLOCKS / CHUNK_ELAPSED))
    LOOP_ELAPSED=$((CHUNK_END_TIME - LOOP_START))
    BLOCKS_LEFT=$((TIP - CHUNK_TO))

    log "[$MODE] $CHUNK_FROM → $CHUNK_TO ($CHUNK_BLOCKS blocks, $CHUNK_ROWS rows) in ${CHUNK_ELAPSED}s | ${CHUNK_RATE} blk/s | behind tip: $BLOCKS_LEFT | session rows: $TOTAL_ROWS | uptime: ${LOOP_ELAPSED}s"
done
