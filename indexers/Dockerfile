FROM python:3.11-slim

# Build context is project root (set in docker-compose.yml: context: .)
# WORKDIR is project root so imports work:
#   from config import ...
#   from db.models import ...
#   from indexers.db import ...
WORKDIR /app

# Install system dependencies (keep cron available as secondary process)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Install project root requirements first, then indexer-specific requirements
COPY requirements.txt ./requirements-root.txt
COPY indexers/requirements.txt ./requirements-indexer.txt
RUN pip install --no-cache-dir -r requirements-root.txt -r requirements-indexer.txt

# Copy project files maintaining import paths
COPY config.py ./config.py
COPY db/ ./db/
COPY engine/ ./engine/
COPY reports/ ./reports/
COPY tax/ ./tax/
COPY verify/ ./verify/
COPY defi/ ./defi/
COPY historical_price_service.py ./historical_price_service.py
COPY indexers/ ./indexers/

# Copy Rust binary for fast account index backfill (pre-compiled for x86_64-linux)
COPY indexers/account-indexer-rs/target/x86_64-unknown-linux-gnu/release/account-indexer-rs /usr/local/bin/account-indexer-rs
RUN chmod +x /usr/local/bin/account-indexer-rs

# Ensure db package is importable
RUN touch ./db/__init__.py 2>/dev/null || true

# Legacy cron schedule (kept for reference — main process is indexers.service)
RUN chmod 0644 ./indexers/crontab && \
    crontab ./indexers/crontab && \
    touch /var/log/cron.log

# Run the standalone indexer service as the main process
CMD ["python", "-m", "indexers.service"]
