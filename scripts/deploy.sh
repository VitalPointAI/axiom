#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/deploy.sh [--rollback COMMIT_SHA]
#
# Deploys current code to production server via SSH.
# Expects these env vars: DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH
# Optional: DEPLOY_SSH_KEY (path to key file)
#
# Smart build: only rebuilds services whose source files changed.
# - web: only if web/, Dockerfile (web target), or package*.json changed
# - api/indexer: only if api/, indexers/, engine/, verify/, db/, config.py, etc. changed
# This cuts deploy time from 60-90 min to 2-5 min for backend-only changes.

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
  # Rollback always rebuilds everything
  BUILD_WEB=true
  BUILD_BACKEND=true
else
  echo "==> Pulling latest from main"
  # Capture the before SHA so we can diff
  BEFORE_SHA=$($SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git rev-parse HEAD")
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git pull origin main && git clean -fd"
  AFTER_SHA=$($SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git rev-parse HEAD")

  if [[ "$BEFORE_SHA" == "$AFTER_SHA" ]]; then
    echo "==> No changes to deploy (already up to date)"
    exit 0
  fi

  # Determine which services need rebuilding based on changed files
  CHANGED_FILES=$($SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git diff --name-only $BEFORE_SHA $AFTER_SHA")
  echo "==> Changed files since last deploy:"
  echo "$CHANGED_FILES" | head -20

  BUILD_WEB=false
  BUILD_BACKEND=false

  while IFS= read -r file; do
    case "$file" in
      web/*|Dockerfile|package*.json|.dockerignore)
        BUILD_WEB=true ;;
      api/*|indexers/*|engine/*|verify/*|db/*|config.py|requirements*.txt|Dockerfile)
        BUILD_BACKEND=true ;;
      docker-compose*.yml)
        BUILD_WEB=true; BUILD_BACKEND=true ;;
      scripts/*|.github/*)
        BUILD_BACKEND=true ;;
    esac
  done <<< "$CHANGED_FILES"
fi

# Step 2: Prune old Docker images and build cache to free disk space
echo "==> Pruning Docker images and build cache (older than 72h)"
$SSH_CMD "$SSH_TARGET" "docker image prune -af --filter 'until=72h' && docker builder prune -af --filter 'until=72h'" || true

# Step 3: Smart build - only rebuild what changed
COMMIT_SHA=$($SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && git rev-parse --short HEAD")

# Authenticate to GHCR for pulling pre-built images
if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "==> Authenticating to GHCR"
  $SSH_CMD "$SSH_TARGET" "echo $GHCR_TOKEN | docker login ghcr.io -u $GHCR_USER --password-stdin" 2>/dev/null || true
fi

# Web: pull pre-built image from GHCR (built in CI, not on server)
if [[ "$BUILD_WEB" == "true" ]]; then
  echo "==> Pulling pre-built web image from GHCR"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml pull web" || {
    echo "==> GHCR pull failed, falling back to local build"
    $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml build web"
  }
fi

# Backend: build on server (fast — Python images, no npm)
if [[ "$BUILD_BACKEND" == "true" ]]; then
  echo "==> Building backend images: api indexer"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml build --build-arg COMMIT_SHA=$COMMIT_SHA api indexer"
fi

if [[ "$BUILD_WEB" != "true" && "$BUILD_BACKEND" != "true" ]]; then
  echo "==> No service rebuilds needed (only docs/planning changed)"
  exit 0
fi

# Step 4: Run migrations (one-shot container)
# Always rebuild migrate image when backend changes — it shares the indexer Dockerfile
# and contains the migration files. Without rebuilding, new migrations won't be detected.
if [[ "$BUILD_BACKEND" == "true" ]]; then
  echo "==> Building and running database migrations"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml build migrate && docker compose -f docker-compose.prod.yml up migrate --exit-code-from migrate"
fi

# Step 5: Rolling restart - only restart what was rebuilt
echo "==> Stopping changed services"

if [[ "$BUILD_WEB" == "true" && "$BUILD_BACKEND" == "true" ]]; then
  # Full restart
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

elif [[ "$BUILD_BACKEND" == "true" ]]; then
  # Backend only — don't touch web or proxy
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml stop api indexer && docker compose -f docker-compose.prod.yml rm -f api indexer"

  echo "==> Starting api (FastAPI backend)"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d api"
  echo "==> Waiting for api health check (10s)"
  sleep 10

  echo "==> Starting indexer"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d indexer"

elif [[ "$BUILD_WEB" == "true" ]]; then
  # Web only — don't touch api or indexer
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml stop proxy web && docker compose -f docker-compose.prod.yml rm -f proxy web"

  echo "==> Starting web (Next.js frontend)"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d web"

  echo "==> Starting proxy (nginx reverse proxy)"
  $SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d proxy"
fi

# Step 6: Ensure ALL services are up (catches containers lost from previous failed deploys)
echo "==> Ensuring all services are running"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && docker compose -f docker-compose.prod.yml up -d postgres api web proxy indexer"

# Step 6b: Sync and reload the host-run account indexer systemd unit.
# The unit file lives in the repo at deploy/systemd/axiom-account-indexer.service.
# We copy it into /etc/systemd/system, reload the daemon so systemd picks up any
# changes, and restart the service so it runs against the latest shell script +
# binary. This must run OUTSIDE the Docker services because the account indexer
# runs on the host (Docker bridge networking is ~200x slower for neardata.xyz).
echo "==> Syncing axiom-account-indexer systemd unit"
$SSH_CMD "$SSH_TARGET" "
  if [ -f $DEPLOY_PATH/deploy/systemd/axiom-account-indexer.service ]; then
    sudo cp $DEPLOY_PATH/deploy/systemd/axiom-account-indexer.service /etc/systemd/system/axiom-account-indexer.service
    sudo systemctl daemon-reload
    # Note: 'systemctl is-enabled' returns 'enabled' or 'disabled' on stdout.
    # Using exact match to avoid grep matching 'disabled' as a substring of 'enabled'.
    if [ \"\$(systemctl is-enabled axiom-account-indexer.service 2>/dev/null)\" = \"enabled\" ]; then
      sudo systemctl restart axiom-account-indexer.service
      echo 'axiom-account-indexer service restarted'
    else
      echo 'axiom-account-indexer unit file synced (service not yet enabled - run: sudo systemctl enable --now axiom-account-indexer)'
    fi
  else
    echo 'WARN: deploy/systemd/axiom-account-indexer.service not found in repo, skipping'
  fi
" || echo "WARN: systemd sync step failed (likely missing sudoers entry) — indexer not restarted"

echo "==> Waiting for services to stabilize (20s)"
sleep 20

# Step 7: Run health checks
echo "==> Running health checks"
$SSH_CMD "$SSH_TARGET" "cd $DEPLOY_PATH && bash scripts/healthcheck.sh"

echo "==> Deployment complete!"
