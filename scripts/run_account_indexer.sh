#!/bin/bash
# Run the Rust account indexer directly on the host (not inside Docker).
# Docker networking adds ~200x overhead to the HTTP requests.
#
# Usage:
#   ./scripts/run_account_indexer.sh              # full backfill from genesis
#   ./scripts/run_account_indexer.sh 100000000    # resume from block 100M
#
# Requires:
#   - /home/deploy/account-indexer-rs-v2 binary
#   - FASTNEAR_API_KEY in .env
#   - PostgreSQL accessible on localhost:5433

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load env
source "$PROJECT_DIR/.env" 2>/dev/null || true
export FASTNEAR_API_KEY

BINARY="/home/deploy/account-indexer-rs-v2"
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$PROJECT_DIR/.env" | cut -d= -f2)
PG_CMD="PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -q"

GENESIS=9820210
CHUNK_SIZE=10000  # 10K blocks per chunk — Rust binary runs fastest at this size
WORKERS=16

# Get start block from argument or DB
if [ -n "$1" ]; then
    START=$1
else
    START=$(PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -t -c \
        "SELECT COALESCE(last_processed_block, 0) FROM account_indexer_state WHERE id = 1;" | tr -d ' ')
    if [ "$START" -le "$GENESIS" ]; then
        START=$GENESIS
    fi
fi

# Get chain tip from FastNear RPC (authenticated)
END=$(curl -s -X POST "https://rpc.mainnet.fastnear.com/$FASTNEAR_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":"1","method":"status","params":[]}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['latest_block_height'])" 2>/dev/null)

if [ -z "$END" ] || [ "$END" -le 0 ] 2>/dev/null; then
    echo "ERROR: Cannot get chain tip from rpc.mainnet.fastnear.com"
    exit 1
fi

echo "================================================================"
echo "  Account Block Index Backfill"
echo "  Range: $START → $END ($(( (END - START) )) blocks)"
echo "  Chunk size: $CHUNK_SIZE blocks"
echo "  Workers: $WORKERS"
echo "  Binary: $BINARY"
echo "================================================================"

CURRENT=$START
TOTAL_PAIRS=0
TOTAL_START=$(date +%s)

while [ "$CURRENT" -lt "$END" ]; do
    CHUNK_END=$((CURRENT + CHUNK_SIZE))
    if [ "$CHUNK_END" -gt "$END" ]; then
        CHUNK_END=$END
    fi

    echo ""
    echo "--- Chunk: $CURRENT → $CHUNK_END ---"
    CHUNK_START_TIME=$(date +%s)

    # Run Rust binary → temp file (stdout=data, stderr=progress)
    TMPFILE=$(mktemp /tmp/abi_chunk_XXXXXX.tsv)
    $BINARY --start "$CURRENT" --end "$CHUNK_END" --workers "$WORKERS" \
        --progress-interval 2000 > "$TMPFILE" || {
        echo "ERROR: Rust binary failed at block $CURRENT"
        rm -f "$TMPFILE"
        exit 1
    }

    # Count pairs
    PAIRS=$(wc -l < "$TMPFILE")

    # COPY into PostgreSQL
    PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -q -c \
        "COPY account_block_index (account_id, block_height) FROM STDIN" < "$TMPFILE"

    # Update cursor
    PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -q -c \
        "UPDATE account_indexer_state SET last_processed_block = $CHUNK_END, updated_at = NOW() WHERE id = 1;"

    rm -f "$TMPFILE"

    TOTAL_PAIRS=$((TOTAL_PAIRS + PAIRS))
    CHUNK_END_TIME=$(date +%s)
    CHUNK_ELAPSED=$((CHUNK_END_TIME - CHUNK_START_TIME))
    TOTAL_ELAPSED=$((CHUNK_END_TIME - TOTAL_START))
    BLOCKS_DONE=$((CHUNK_END - START))
    BLOCKS_LEFT=$((END - CHUNK_END))
    RATE=$((BLOCKS_DONE / (TOTAL_ELAPSED + 1)))
    ETA_HOURS=$(echo "scale=1; $BLOCKS_LEFT / ($RATE + 1) / 3600" | bc)

    PCT=$(echo "scale=1; $BLOCKS_DONE * 100 / ($END - $START)" | bc)

    echo "  $PAIRS pairs loaded in ${CHUNK_ELAPSED}s | Total: $TOTAL_PAIRS pairs | ${PCT}% | ~${RATE} blocks/sec | ETA: ${ETA_HOURS}h"

    CURRENT=$((CHUNK_END + 1))
done

echo ""
echo "================================================================"
echo "  Backfill complete!"
echo "  Total pairs: $TOTAL_PAIRS"
echo "  Total time: $(($(date +%s) - TOTAL_START))s"
echo "================================================================"

# Rebuild indexes
echo "Rebuilding indexes..."
PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -c "
    DELETE FROM account_block_index a
    USING account_block_index b
    WHERE a.ctid < b.ctid
      AND a.account_id = b.account_id
      AND a.block_height = b.block_height;
"
echo "Dedup complete."

PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -c "
    ALTER TABLE account_block_index
    ADD CONSTRAINT account_block_index_pkey
    PRIMARY KEY (account_id, block_height);
"
echo "Primary key added."

PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -c "
    CREATE INDEX IF NOT EXISTS ix_abi_account_block
    ON account_block_index (account_id, block_height);
"
echo "Index created. Done!"
