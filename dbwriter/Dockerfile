# Multi-stage build for optimized image size
FROM python:3.11-slim as builder

# Install system dependencies for building psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 dbwriter

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=dbwriter:dbwriter src/ ./src/

# Create logs directory with proper ownership (after COPY to prevent overwrite)
RUN mkdir -p /app/logs && chown -R dbwriter:dbwriter /app/logs

# Set Python path to include src directory
ENV PYTHONPATH=/app/src

# Switch to non-root user
USER dbwriter

# Run the application
CMD ["python", "-m", "dbwriter.main"]
