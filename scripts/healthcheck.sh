#!/usr/bin/env bash
set -euo pipefail

# Health check script — verifies all Axiom services are running
# Run on the server after deployment

COMPOSE_FILE="${1:-docker-compose.prod.yml}"
MAX_RETRIES=10
RETRY_DELAY=5

check_service() {
  local service=$1
  local container_status
  container_status=$(docker compose -f "$COMPOSE_FILE" ps --format json "$service" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','') or d.get('State',''))" 2>/dev/null || echo "not_found")
  echo "$container_status"
}

echo "=== Axiom Health Check ==="

FAILED=0

# Check postgres
echo -n "PostgreSQL: "
PG_STATUS=$(check_service postgres)
if [[ "$PG_STATUS" == *"healthy"* ]] || [[ "$PG_STATUS" == *"running"* ]]; then
  echo "OK"
else
  echo "FAIL ($PG_STATUS)"
  FAILED=1
fi

# Check api via HTTP health endpoint (direct port, not through proxy)
echo -n "API (FastAPI): "
for i in $(seq 1 $MAX_RETRIES); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "OK"
    break
  fi
  if [[ $i -eq $MAX_RETRIES ]]; then
    echo "FAIL (health endpoint unreachable after ${MAX_RETRIES} retries)"
    FAILED=1
  else
    sleep $RETRY_DELAY
  fi
done

# Check web container is running (don't HTTP check — it's behind proxy)
echo -n "Web (Next.js): "
WEB_STATUS=$(check_service web)
if [[ "$WEB_STATUS" == *"healthy"* ]] || [[ "$WEB_STATUS" == *"running"* ]]; then
  echo "OK"
else
  echo "FAIL ($WEB_STATUS)"
  FAILED=1
fi

# Check indexer is running
echo -n "Indexer: "
IDX_STATUS=$(check_service indexer)
if [[ "$IDX_STATUS" == *"running"* ]]; then
  echo "OK"
else
  echo "FAIL ($IDX_STATUS)"
  FAILED=1
fi

echo "========================="

if [[ $FAILED -eq 1 ]]; then
  echo "HEALTH CHECK FAILED"
  # Show logs for debugging
  docker compose -f "$COMPOSE_FILE" logs --tail=20 2>/dev/null || true
  exit 1
fi

echo "ALL SERVICES HEALTHY"
exit 0
