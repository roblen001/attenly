# Backend Image Size

The backend image can be large because it includes document processing and OCR
dependencies, including Python OCR/model libraries and native runtime packages.

Current source-build validation produces a backend image of approximately 6 to
7 GB, depending on the Docker platform and build cache.

## Why It Is Large

The backend image includes support for:

- FastAPI runtime
- SQLAlchemy/local persistence
- PDF and document processing
- WeasyPrint/Cairo/Pango native libraries
- OpenCV runtime libraries
- DocTR/OCR dependencies
- optional pre-cached OCR models

This keeps the first self-hosted image operational without requiring companies
to assemble OCR dependencies manually.

## Build-Time Model Pre-Cache

By default, source builds pre-cache the small/fast DocTR OCR model pair during
the backend image build. That makes first OCR use faster, but it increases build
time and image size.

For health-only CI or faster local source builds:

```bash
ATTENLY_PRECACHE_DOCTR_MODELS=false docker compose -f compose.yml -f compose.build.yml build backend
```

With pre-cache disabled, the app still starts. OCR models are downloaded on
first OCR use instead.

## Current Recommendation

The current release uses one backend image so companies do not need to assemble
OCR dependencies or choose between image variants during installation.

Possible future optimizations include:

- a default backend image without pre-cached OCR models
- an OCR-enabled image tag
- lazy OCR dependency/model download
- moving heavy document/OCR processing into an optional worker image

Any future image split should include a tested installation path for every
published variant.
