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
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_NO_CACHE_DIR=0 python -m pip install --upgrade pip setuptools wheel && \
    PIP_NO_CACHE_DIR=0 pip wheel \
      pip==26.1.2 setuptools==83.0.0 wheel==0.47.0 -w /wheels && \
    PIP_NO_CACHE_DIR=0 \
    pip wheel -r requirements.txt -w /wheels

# --- Runtime stage ---
FROM python:3.11-slim-bookworm AS runtime
WORKDIR /app
ARG ATTENLY_PRECACHE_DOCTR_MODELS=true

# Conservative threading to avoid OOM; you can tune later
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=8080 \
    MPLBACKEND=Agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TORCH_NUM_THREADS=1 \
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
RUN pip install --no-index --find-links /wheels \
      pip==26.1.2 setuptools==83.0.0 wheel==0.47.0 \
      -r requirements.txt && \
    rm -rf /wheels

# Fail the image build if the pinned WeasyPrint/PyDyf pair cannot render a PDF.
RUN python -c "from weasyprint import HTML; pdf = HTML(string='<p>PDF smoke test</p>').write_pdf(presentational_hints=True, optimize_images=True); assert pdf.startswith(b'%PDF-'), 'WeasyPrint did not produce a PDF'"

# ---- Optionally pre-download DocTR models during build (as root) ----
# Use smallest/fastest CPU pair:
#   det_arch='db_mobilenet_v3_large'
#   reco_arch='crnn_mobilenet_v3_small'
RUN mkdir -p /cache/attenly/doctr && \
    if [ "$ATTENLY_PRECACHE_DOCTR_MODELS" = "true" ]; then \
      DOCTR_CACHE_DIR=/cache/attenly/doctr \
      OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 TORCH_NUM_THREADS=1 \
      CUDA_VISIBLE_DEVICES="" \
      python -c "\
import os; \
os.environ['CUDA_VISIBLE_DEVICES']=''; \
os.environ['DOCTR_CACHE_DIR']='/cache/attenly/doctr'; \
from doctr.models import ocr_predictor; \
print('Pre-caching DocTR models (small/fast)...'); \
_ = ocr_predictor(det_arch='db_mobilenet_v3_large', reco_arch='crnn_mobilenet_v3_small', pretrained=True); \
print('DocTR models cached successfully');"; \
    else \
      echo "Skipping DocTR model pre-cache; models will be downloaded on first OCR use."; \
    fi

# ---- Create non-root user and writable cache AFTER deps are installed ----
RUN useradd -u 10001 -m appuser \
 && mkdir -p /cache/attenly /data/storage \
 && chown -R appuser:appuser /cache /data /app

# Copy app source with the runtime owner (after deps to maximize cache)
COPY --chown=appuser:appuser . .

USER appuser

# Healthcheck (adjust path if needed)
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Start FastAPI via Uvicorn: 1 worker, low keep-alive, optional concurrency cap
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", \
     "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16", \
     "--workers", "1", "--timeout-keep-alive", "5"]
