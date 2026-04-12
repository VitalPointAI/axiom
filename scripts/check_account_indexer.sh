#!/bin/bash
# Account indexer health monitor — runs via cron every 5 minutes.
#
# Responsibilities:
#   1. Verify the axiom-account-indexer systemd unit is active
#   2. Verify the cursor has advanced since the last check, OR that it is
#      within LIVE_LAG_BLOCKS of the chain tip (i.e. caught up)
#   3. If either check fails, restart the service via systemctl
#   4. Log status to /home/deploy/logs/indexer-monitor.log
#
# Install via crontab (run once as the deploy user):
#   crontab -e
#   */5 * * * * /home/deploy/Axiom/scripts/check_account_indexer.sh >> /home/deploy/logs/indexer-monitor.log 2>&1
#
# Requires sudo access for the systemctl restart step. Configure via:
#   sudo visudo -f /etc/sudoers.d/deploy-indexer
#     deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart axiom-account-indexer.service, /bin/systemctl is-active axiom-account-indexer.service

set -u

SERVICE=axiom-account-indexer.service
STATE_FILE=/tmp/axiom_account_indexer_last_block
ALERT_FLAG=/tmp/axiom_account_indexer_alert
LOGDIR=/home/deploy/logs
mkdir -p "$LOGDIR"

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log() {
    echo "[$TIMESTAMP] $*"
}

# Load env for DB access
ENV_FILE=/home/deploy/Axiom/.env
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

restart_service() {
    log "Restarting $SERVICE"
    if sudo -n /bin/systemctl restart "$SERVICE" 2>&1; then
        log "Restart issued successfully"
    else
        log "ERROR: failed to restart $SERVICE (sudo permissions?)"
        return 1
    fi
}

# 1. Is the service active?
if ! systemctl is-active --quiet "$SERVICE"; then
    log "WARN: $SERVICE is not active"
    if [ ! -f "$ALERT_FLAG" ]; then
        touch "$ALERT_FLAG"
        log "ALERT: indexer down"
    fi
    restart_service
    exit 1
fi

# 2. Read current cursor
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    log "ERROR: POSTGRES_PASSWORD not set in env"
    exit 2
fi
export PGPASSWORD="$POSTGRES_PASSWORD"
CURRENT_CURSOR=$(psql -h 127.0.0.1 -p 5433 -U neartax -t -c \
    "SELECT last_processed_block FROM account_indexer_state WHERE id = 1;" 2>/dev/null | tr -d ' ')

if [ -z "$CURRENT_CURSOR" ]; then
    log "WARN: cannot read cursor from DB"
    exit 1
fi

# 3. Fetch chain tip
TIP=$(curl -s --max-time 10 -X POST https://rpc.mainnet.fastnear.com \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${FASTNEAR_API_KEY:-}" \
    -d '{"jsonrpc":"2.0","id":"1","method":"status","params":[]}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['latest_block_height'])" \
    2>/dev/null)

if [ -z "$TIP" ] || [ "$TIP" -le 0 ] 2>/dev/null; then
    log "WARN: cannot read chain tip (RPC unreachable or throttled)"
    # Don't restart the service just because the RPC is flaky — bail out
    exit 1
fi

BEHIND=$((TIP - CURRENT_CURSOR))

# 4. Compare against previous cursor
STALL_THRESHOLD=${STALL_THRESHOLD:-5}  # caught up if within 5 blocks of tip
if [ "$BEHIND" -le "$STALL_THRESHOLD" ]; then
    log "OK: caught up (cursor=$CURRENT_CURSOR, tip=$TIP, behind=$BEHIND)"
    echo "$CURRENT_CURSOR" > "$STATE_FILE"
    [ -f "$ALERT_FLAG" ] && rm -f "$ALERT_FLAG" && log "RECOVERED"
    exit 0
fi

if [ ! -f "$STATE_FILE" ]; then
    log "OK: first check (cursor=$CURRENT_CURSOR, tip=$TIP, behind=$BEHIND, backfilling)"
    echo "$CURRENT_CURSOR" > "$STATE_FILE"
    exit 0
fi

PREVIOUS_CURSOR=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
if [ "$CURRENT_CURSOR" -le "$PREVIOUS_CURSOR" ]; then
    log "WARN: cursor stalled at $CURRENT_CURSOR (prev=$PREVIOUS_CURSOR, tip=$TIP, behind=$BEHIND)"
    if [ ! -f "$ALERT_FLAG" ]; then
        touch "$ALERT_FLAG"
        log "ALERT: indexer cursor not advancing, attempting restart"
    fi
    restart_service
    exit 1
fi

ADVANCED=$((CURRENT_CURSOR - PREVIOUS_CURSOR))
log "OK: progressing (cursor=$CURRENT_CURSOR, +$ADVANCED since last check, tip=$TIP, behind=$BEHIND)"
echo "$CURRENT_CURSOR" > "$STATE_FILE"
[ -f "$ALERT_FLAG" ] && rm -f "$ALERT_FLAG" && log "RECOVERED"
exit 0
