# =========================
# Dockerfile (FastAPI + WeasyPrint/OCR + OpenCV, slim & safe)
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
# Build wheels for requirements AND their transitive deps (no --no-deps)
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
    DOCTR_CACHE_DIR=/cache/attenly/doctr

# Runtime libs: WeasyPrint/Cairo/Pango + fonts + OpenCV deps (libGL etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libharfbuzz0b libfontconfig1 \
    libmagic1 shared-mime-info fonts-dejavu curl \
    libgl1 libsm6 libxext6 libxrender1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

# ---- Install Python deps from prebuilt wheels as root (offline) ----
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links /wheels -r requirements.txt && \
    rm -rf /wheels

# ---- Pre-download DocTR models during build (as root) ----
# This prevents runtime downloads and memory spikes on first OCR request
# Using db_mobilenet_v3_large for faster OCR on CPU instances
RUN mkdir -p /cache/attenly/doctr && \
    DOCTR_CACHE_DIR=/cache/attenly/doctr python -c "\
import os; \
os.environ['CUDA_VISIBLE_DEVICES'] = ''; \
from doctr.models import ocr_predictor; \
print('Pre-caching DocTR models (optimized for speed)...'); \
_ = ocr_predictor(det_arch='db_mobilenet_v3_large', reco_arch='parseq', pretrained=True); \
print('DocTR models cached successfully')"

# ---- Create non-root user and writable cache AFTER deps are installed ----
RUN useradd -u 10001 -m appuser \
 && mkdir -p /cache/attenly \
 && chown -R appuser:appuser /cache /app

# Copy app source (after deps to maximize cache)
COPY . .
RUN chown -R appuser:appuser /app

USER appuser

# Healthcheck (adjust path if needed)
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Start FastAPI via Uvicorn: 1 worker, low keep-alive, optional concurrency cap
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--workers", "1", "--timeout-keep-alive", "5"]
