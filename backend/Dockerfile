# =========================
# Dockerfile (FastAPI + WeasyPrint/OCR friendly)
# =========================

# --- Build stage ---
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Prevent Python from writing .pyc files / buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System build deps for common scientific/graphics libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    libmagic1 \
    libmagic-dev \
    libglib2.0-dev \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    libharfbuzz-dev \
    libfontconfig1-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy and build wheels to make runtime smaller & reproducible
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip wheel --wheel-dir /wheels -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Base runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=8080 \
    MPLBACKEND=Agg \
    QT_QPA_PLATFORM=offscreen \
    DISPLAY=:99

# Runtime libs for WeasyPrint/Pango/Cairo + magic + fonts + healthcheck curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    libharfbuzz0b \
    libfontconfig1 \
    libgl1 \
    libgomp1 \
    fonts-dejavu \
    curl \
    # X11 libs only if needed by other parts of your app; harmless to keep:
    libx11-6 \
    libxext6 \
    libxrender1 \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get clean

# Create non-root user
RUN adduser --disabled-password --gecos "" --shell /bin/false appuser

# Install Python deps from prebuilt wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels /wheels/* \
 && rm -rf /wheels

# Copy your application code
COPY . .

# Permissions then drop privileges
RUN chown -R appuser:appuser /app
USER appuser

# Expose app port
EXPOSE 8080

# Healthcheck (relies on curl we installed above)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Start FastAPI via Uvicorn (adjust module:app if different)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
