# =========================
# Dockerfile (FastAPI + WeasyPrint/OCR friendly, slim & safe)
# =========================

# --- Build stage ---
FROM python:3.11-slim-bookworm AS builder
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps only (no runtime bloat)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc pkg-config \
    libffi-dev libcairo2-dev libpango1.0-dev libgdk-pixbuf-2.0-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# IMPORTANT: build wheels for requirements AND their transitive deps
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip wheel -r requirements.txt -w /wheels

# --- Runtime stage ---
FROM python:3.11-slim-bookworm AS runtime
WORKDIR /app

# Conservative threading to avoid OOM; you can tune later
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=8080 \
    MPLBACKEND=Agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    ATTENLY_CACHE_DIR=/cache/attenly

# Only the runtime libs actually needed by WeasyPrint/Cairo/Pango + fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libharfbuzz0b libfontconfig1 \
    libmagic1 shared-mime-info fonts-dejavu curl \
  && rm -rf /var/lib/apt/lists/*

# Non-root user and writable cache dir
RUN useradd -u 10001 -m appuser \
 && mkdir -p /cache/attenly \
 && chown -R appuser:appuser /cache
USER appuser

# Install Python deps from prebuilt wheels ONLY (offline/reproducible)
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links /wheels -r requirements.txt && \
    rm -rf /wheels

# Copy app source (after deps to maximize cache)
COPY . .

# Healthcheck (adjust path if needed)
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Start FastAPI via Uvicorn: 1 worker, low keep-alive, optional concurrency cap
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--workers", "1", "--timeout-keep-alive", "5", "--limit-concurrency", "2"]
