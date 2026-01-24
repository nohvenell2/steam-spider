# ============================================
# Single stage - Minimal runtime image
# ============================================
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies (postgresql-client for pg_isready)
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary application files
COPY src/ ./src/
COPY init_db.py ./
COPY entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
