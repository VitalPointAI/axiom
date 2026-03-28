#!/usr/bin/env bash
set -euo pipefail

# Health check script — verifies all Axiom services are running
# Run on the server after deployment

COMPOSE_FILE="${1:-docker-compose.prod.yml}"
MAX_RETRIES=10
RETRY_DELAY=5

echo "=== Axiom Health Check ==="

FAILED=0

# Check postgres
echo -n "PostgreSQL: "
PG_STATUS=$(docker compose -f "$COMPOSE_FILE" ps postgres --format '{{.Status}}' 2>/dev/null || echo "not_found")
if [[ "$PG_STATUS" == *"healthy"* ]] || [[ "$PG_STATUS" == *"Up"* ]]; then
  echo "OK ($PG_STATUS)"
else
  echo "FAIL ($PG_STATUS)"
  FAILED=1
fi

# Check api health via docker exec (it's not exposed on host ports)
echo -n "API (FastAPI): "
for i in $(seq 1 $MAX_RETRIES); do
  if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
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

# Check web container is running
echo -n "Web (Next.js): "
WEB_STATUS=$(docker compose -f "$COMPOSE_FILE" ps web --format '{{.Status}}' 2>/dev/null || echo "not_found")
if [[ "$WEB_STATUS" == *"healthy"* ]] || [[ "$WEB_STATUS" == *"Up"* ]]; then
  echo "OK ($WEB_STATUS)"
else
  echo "FAIL ($WEB_STATUS)"
  FAILED=1
fi

# Check indexer is running
echo -n "Indexer: "
IDX_STATUS=$(docker compose -f "$COMPOSE_FILE" ps indexer --format '{{.Status}}' 2>/dev/null || echo "not_found")
if [[ "$IDX_STATUS" == *"Up"* ]]; then
  echo "OK ($IDX_STATUS)"
else
  echo "FAIL ($IDX_STATUS)"
  FAILED=1
fi

# Check proxy can reach the app
echo -n "Proxy (nginx): "
for i in $(seq 1 $MAX_RETRIES); do
  if curl -sf http://localhost:3003/health > /dev/null 2>&1; then
    echo "OK"
    break
  fi
  if [[ $i -eq $MAX_RETRIES ]]; then
    echo "FAIL (proxy unreachable after ${MAX_RETRIES} retries)"
    FAILED=1
  else
    sleep $RETRY_DELAY
  fi
done

echo "========================="

if [[ $FAILED -eq 1 ]]; then
  echo "HEALTH CHECK FAILED"
  docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || true
  echo "--- Recent logs ---"
  docker compose -f "$COMPOSE_FILE" logs --tail=10 api web proxy 2>/dev/null || true
  exit 1
fi

echo "ALL SERVICES HEALTHY"
exit 0
