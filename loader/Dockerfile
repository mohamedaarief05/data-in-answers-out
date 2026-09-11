# Pinned Python 3.11 base image (DO NOT USE 'latest')
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies if needed and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/app/

# Set correct ownership for non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Environment variables expected by the loader:
# KAFKA_BOOTSTRAP_SERVERS (e.g. kafka:9092)
# KAFKA_TOPIC (default: csv-rows)
# KAFKA_GROUP_ID (default: loader-group)
# NEO4J_URI (e.g. bolt://neo4j:7687)
# NEO4J_USERNAME (e.g. neo4j)
# NEO4J_PASSWORD (e.g. password)
# NEO4J_DATABASE (default: neo4j)

CMD ["python", "-m", "app.main"]
