# ── Stage 1: Build ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (Docker cache optimization).
# src/ must be present too: the build backend needs the package directory
# to produce the wheel, so copying only pyproject.toml fails the build.
COPY pyproject.toml ./
COPY src/ src/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ── Stage 2: Runtime ──────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r pr_agent && useradd -r -g pr_agent -d /app -s /sbin/nologin pr_agent

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./

# Create cache directory
RUN mkdir -p /app/data && chown -R pr_agent:pr_agent /app

# Switch to non-root user
USER pr_agent

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Run migrations then start the server.
# `python -m alembic` is used instead of the bare console script so the
# entrypoint does not depend on PATH within the image.
CMD ["sh", "-c", "python -m alembic upgrade head && python -m pr_review_agent.app"]
