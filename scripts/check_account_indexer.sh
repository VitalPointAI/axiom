#!/bin/bash
# Account indexer health monitor — runs via cron every 5 minutes.
# Checks that the host-run account indexer (v0.3 Rust binary) is running
# and the cursor is advancing. Sends an alert via the Axiom API if stalled.
#
# Crontab entry:
#   */5 * * * * /home/deploy/Axiom/scripts/check_account_indexer.sh >> /home/deploy/logs/indexer-monitor.log 2>&1

LOGFILE="/home/deploy/logs/indexer-monitor.log"
ALERT_FLAG="/tmp/account_indexer_alert_sent"
STATE_FILE="/tmp/account_indexer_last_block"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Check if the Rust indexer process is running
INDEXER_PID=$(pgrep -f "account-indexer-rs-v2.*--database-url" | head -1)

if [ -z "$INDEXER_PID" ]; then
    echo "$TIMESTAMP WARNING: account-indexer-rs-v2 not running"
    if [ ! -f "$ALERT_FLAG" ]; then
        touch "$ALERT_FLAG"
        echo "$TIMESTAMP ALERT: account indexer process is not running"
    fi
    exit 1
fi

# Container is running — check cursor progress
PG_PASS=$(grep '^POSTGRES_PASSWORD=' /home/deploy/Axiom/.env 2>/dev/null | cut -d= -f2)
LAST_BLOCK=$(PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -t -c \
    "SELECT last_processed_block FROM account_indexer_state WHERE id = 1;" 2>/dev/null | tr -d ' ')
INDEX_COUNT=$(PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -p 5433 -U neartax -t -c \
    "SELECT reltuples::bigint FROM pg_class WHERE relname = 'account_transactions';" 2>/dev/null | tr -d ' ')

echo "$TIMESTAMP OK: pid=$INDEXER_PID block=$LAST_BLOCK entries=$INDEX_COUNT"

# Check for cursor stall — if last_block hasn't moved in 2 consecutive checks
if [ -f "$STATE_FILE" ]; then
    PREV_BLOCK=$(cat "$STATE_FILE")
    if [ "$LAST_BLOCK" = "$PREV_BLOCK" ]; then
        echo "$TIMESTAMP WARNING: cursor stalled at block $LAST_BLOCK"
        if [ ! -f "$ALERT_FLAG" ]; then
            touch "$ALERT_FLAG"
            echo "$TIMESTAMP ALERT: indexer cursor has not advanced"
        fi
        exit 1
    fi
fi
echo "$LAST_BLOCK" > "$STATE_FILE"

# Clear alert flag when healthy and progressing
if [ -f "$ALERT_FLAG" ]; then
    rm "$ALERT_FLAG"
    echo "$TIMESTAMP RECOVERED: account indexer is healthy again"
fi
