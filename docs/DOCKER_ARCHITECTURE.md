# Docker Architecture

The default self-hosted deployment is one Docker Compose project with two
services and one persistent volume.

## Services

| Service | Role | Host Exposure |
| --- | --- | --- |
| `frontend` | Nginx serves the React app, runtime config, TinyMCE, `/health`, and proxies `/api` to the backend. | Publishes `ATTENLY_FRONTEND_PORT`, default `5173`. |
| `backend` | FastAPI app for auth, uploads, report generation, storage, email jobs, and provider integrations. | Exposed only inside the Compose network on port `8080`. |

Browser traffic should enter through the frontend:

```text
browser -> http://localhost:5173 -> frontend nginx -> /api -> backend:8080
```

The backend is intentionally not published to the host by `compose.yml`.

## Persistent Data

The `attenly-data` Docker volume is mounted at `/data` in the backend
container.

Default paths:

```bash
DATABASE_URL=sqlite:////data/attenly.db
STORAGE_PROVIDER=filesystem
STORAGE_PATH=/data/storage
```

Container recreation keeps the volume. `docker compose down` keeps the volume.
`docker compose down -v` deletes the volume.

## Runtime Configuration

The backend reads `.env` through Compose `env_file`.

The frontend does not bake environment-specific config into the image. At
container startup, `frontend/docker-entrypoint.sh` writes:

```text
/usr/share/nginx/html/config.js
```

That file contains browser-safe runtime settings such as:

- `VITE_API_BASE_URL`
- `VITE_AUTH_PROVIDER`
- TinyMCE mode/script settings

It must not contain secrets. `LOCAL_AUTH_TOKEN` stays backend-only.

## Published Images vs Source Build

Published image path:

```bash
docker compose up -d --wait
```

Local source-build path:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build --wait
```

`compose.build.yml` only adds build contexts and forces Compose to build local
images.

The backend source build pre-caches DocTR OCR models by default. For CI or fast
health-only builds, skip that pre-cache:

```bash
ATTENLY_PRECACHE_DOCTR_MODELS=false docker compose -f compose.yml -f compose.build.yml build backend
```

When pre-cache is skipped, the app can still start. OCR models are downloaded on
first OCR use instead.

See [`BACKEND_IMAGE_SIZE.md`](BACKEND_IMAGE_SIZE.md) for why the backend image
is large and how to think about future image variants.

## Health Checks

Frontend:

```text
GET /health -> ok
```

Backend readiness:

```text
GET /ready
```

Backend readiness checks:

- configured database provider
- filesystem storage writability when `STORAGE_PROVIDER=filesystem`
- config validation

Compose waits for backend readiness before starting the frontend.
