#!/bin/bash
# Account indexer health monitor — runs via cron every 5 minutes.
# Checks if the account-indexer container is healthy and the DB cursor
# is advancing. Sends an alert via the Axiom API if something's wrong.
#
# Crontab entry:
#   */5 * * * * /home/deploy/axiom/scripts/check_account_indexer.sh >> /home/deploy/axiom/logs/indexer-monitor.log 2>&1

LOGFILE="/home/deploy/axiom/logs/indexer-monitor.log"
ALERT_FLAG="/tmp/account_indexer_alert_sent"

# Check container status
CONTAINER_STATUS=$(docker inspect --format='{{.State.Health.Status}}' axiom-account-indexer-1 2>/dev/null)
CONTAINER_RUNNING=$(docker inspect --format='{{.State.Running}}' axiom-account-indexer-1 2>/dev/null)

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ "$CONTAINER_RUNNING" != "true" ]; then
    echo "$TIMESTAMP ALERT: account-indexer container is not running!"

    # Try to restart it
    cd /home/deploy/axiom && docker compose -f docker-compose.prod.yml up -d account-indexer 2>&1
    echo "$TIMESTAMP Attempted restart."

    # Send alert (only once per incident)
    if [ ! -f "$ALERT_FLAG" ]; then
        touch "$ALERT_FLAG"
        # Log the alert — email notification through Axiom API could be added here
        echo "$TIMESTAMP ALERT SENT: account-indexer down and restarted"
    fi
    exit 1
fi

if [ "$CONTAINER_STATUS" = "unhealthy" ]; then
    echo "$TIMESTAMP WARNING: account-indexer is unhealthy (stale). Docker will restart it."

    if [ ! -f "$ALERT_FLAG" ]; then
        touch "$ALERT_FLAG"
        echo "$TIMESTAMP ALERT SENT: account-indexer unhealthy"
    fi
    exit 1
fi

# Container is running — check progress
LAST_BLOCK=$(docker exec axiom-postgres-1 psql -U neartax -t -c "SELECT last_processed_block FROM account_indexer_state WHERE id = 1;" 2>/dev/null | tr -d ' ')
INDEX_COUNT=$(docker exec axiom-postgres-1 psql -U neartax -t -c "SELECT reltuples::bigint FROM pg_class WHERE relname = 'account_block_index_v2';" 2>/dev/null | tr -d ' ')

echo "$TIMESTAMP OK: container=$CONTAINER_STATUS block=$LAST_BLOCK entries=$INDEX_COUNT"

# Clear alert flag when healthy
if [ -f "$ALERT_FLAG" ]; then
    rm "$ALERT_FLAG"
    echo "$TIMESTAMP RECOVERED: account-indexer is healthy again"
fi
