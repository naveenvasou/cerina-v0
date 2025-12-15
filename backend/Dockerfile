# ============================================
# Cerina Backend - Production Dockerfile
# ============================================
# Multi-stage build for a lean, secure image

# -------------------- Build Stage --------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# -------------------- Production Stage --------------------
FROM python:3.12-slim AS production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 cerina && \
    useradd --uid 1000 --gid cerina --shell /bin/bash --create-home cerina

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
# Note: We copy to /app/backend to preserve the module structure
COPY . /app/backend/

# Set Python path so imports like 'from backend.graph import ...' work
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Change ownership to non-root user
RUN chown -R cerina:cerina /app

# Switch to non-root user
USER cerina

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
EXPOSE $PORT

# Note: Cloud Run ignores Docker HEALTHCHECK - configure HTTP health checks in Cloud Run console instead

# Run the application
# Using shell form to expand $PORT variable at runtime
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
