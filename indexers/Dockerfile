FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy indexer scripts
COPY *.py ./
COPY crontab /etc/cron.d/indexers

# Set up cron
RUN chmod 0644 /etc/cron.d/indexers && \
    crontab /etc/cron.d/indexers && \
    touch /var/log/cron.log

# Create entrypoint script
RUN echo '#!/bin/bash\n\
printenv | grep -E "DATABASE_URL|API_KEY" >> /etc/environment\n\
cron && tail -f /var/log/cron.log' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
