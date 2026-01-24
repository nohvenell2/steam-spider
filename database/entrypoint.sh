#!/bin/bash
set -e

echo "======================================"
echo "Waiting for PostgreSQL to be ready..."
echo "======================================"

# Wait for PostgreSQL to be ready
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if pg_isready -h postgres -p 5432 -U "${POSTGRES_USER:-steam_user}" > /dev/null 2>&1; then
        echo "✓ PostgreSQL is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Failed to connect to PostgreSQL after $max_attempts attempts"
    exit 1
fi

echo ""
echo "======================================"
echo "Initializing Database Tables..."
echo "======================================"

# Run the initialization script
python init_db.py

if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "✓ Database initialization completed!"
    echo "======================================"
else
    echo ""
    echo "======================================"
    echo "✗ Database initialization failed!"
    echo "======================================"
    exit 1
fi

# Keep container running (optional - remove if you want it to exit after init)
echo ""
echo "Initialization complete. Container will now exit."
