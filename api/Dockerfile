FROM python:3.11-slim

# Build context is project root (same pattern as indexers/Dockerfile)
# so db/, config.py, indexers/, engine/, reports/, verify/ are all available
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files maintaining import paths
COPY config.py ./config.py
COPY db/ ./db/
COPY indexers/ ./indexers/
COPY engine/ ./engine/
COPY reports/ ./reports/
COPY api/ ./api/

# Ensure packages are importable
RUN touch ./db/__init__.py 2>/dev/null || true
RUN touch ./api/__init__.py 2>/dev/null || true

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
