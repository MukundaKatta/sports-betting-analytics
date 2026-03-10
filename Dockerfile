FROM python:3.11-slim AS base

WORKDIR /app

# System deps for SQLite and health
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy application source
COPY src/ src/
COPY .env.example .env.example

# Create data directory for SQLite
RUN mkdir -p data

# Non-root user for security
RUN useradd -r -s /bin/false sba && chown -R sba:sba /app
USER sba

# Expose web port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "sba.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
