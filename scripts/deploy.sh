#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/deploy.sh [--rollback COMMIT_SHA]
#
# Deploys current code to production server via SSH.
# Expects these env vars: DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH
# Optional: DEPLOY_SSH_KEY (path to key file)

# Parse arguments
ROLLBACK_SHA=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --rollback) ROLLBACK_SHA="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# Validate required env vars
for var in DEPLOY_HOST DEPLOY_USER DEPLOY_PATH; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var is not set"; exit 1
  fi
done

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=20"
if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
  SSH_CMD="$SSH_CMD -i $DEPLOY_SSH_KEY"
fi
SSH_TARGET="$DEPLOY_USER@$DEPLOY_HOST"

echo "==> Deploying to $SSH_TARGET:$DEPLOY_PATH"

# Step 1: Pull latest code (or checkout specific commit for rollback)
if [[ -n "$ROLLBACK_SHA" ]]; then
  echo "==> Rolling back to $ROLLBACK_SHA"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git fetch origin && git checkout $ROLLBACK_SHA"
else
  echo "==> Pulling latest from main"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git pull origin main && git clean -fd"
fi

# Step 2: Build new images
# Web uses COMMIT_SHA build arg to bust cache for source changes while keeping npm ci cached
echo "==> Building Docker images"
COMMIT_SHA=$($SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git rev-parse --short HEAD")
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml build --parallel --build-arg COMMIT_SHA=$COMMIT_SHA"

# Step 3: Run migrations (one-shot container)
echo "==> Running database migrations"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up migrate --exit-code-from migrate"

# Step 4: Rolling restart - user-facing services first, background workers last
# Rolling restart order: web, api, indexer
echo "==> Stopping proxy, web, api, and indexer"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml stop proxy web api indexer && docker compose -f docker-compose.prod.yml rm -f proxy web api indexer"

echo "==> Starting api (FastAPI backend)"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d api"

echo "==> Waiting for api health check (20s)"
sleep 20

echo "==> Starting web (Next.js frontend)"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d web"

echo "==> Starting proxy (nginx reverse proxy)"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d proxy"

echo "==> Starting indexer"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d indexer"

echo "==> Waiting for services to stabilize (30s)"
sleep 30

# Step 5: Run health checks
echo "==> Running health checks"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && bash scripts/healthcheck.sh"

echo "==> Deployment complete!"
