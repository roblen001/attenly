# Docker Architecture

The default self-hosted deployment is one Docker Compose project with three
services and one persistent volume.

## Services

| Service | Role | Host Exposure |
| --- | --- | --- |
| `frontend` | Nginx serves the React app, runtime config, TinyMCE, `/health`, and proxies `/api` to the backend. | Publishes `ATTENLY_FRONTEND_PORT`, default `5173`. |
| `backend` | FastAPI app for auth, uploads, report viewing, storage, and provider-backed interactive requests. | Exposed only inside the Compose network on port `8080`. |
| `email-worker` | Background process that polls inbound email and processes queued email report jobs. | No host port. |

Browser traffic should enter through the frontend:

```text
browser -> http://localhost:5173 -> frontend nginx -> /api -> backend:8080
```

The backend is intentionally not published to the host by `compose.yml`.
The `email-worker` also stays private. It uses the same image and environment
as the backend, but it runs `python -m app.workers.email_worker` instead of
Uvicorn.

## Persistent Data

The `attenly-data` Docker volume is mounted at `/data` in the backend and
`email-worker` containers.

Default paths:

```bash
DATABASE_URL=sqlite:////data/attenly.db
STORAGE_PROVIDER=filesystem
STORAGE_PATH=/data/storage
```

Container recreation keeps the volume. `docker compose down` keeps the volume.
`docker compose down -v` deletes the volume.

SQLite runs with WAL mode and a busy timeout so the web process and
`email-worker` can share the same local database during a pilot. For heavier
production use, move `DATABASE_URL` to a managed SQL database.

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
images. It builds the shared backend image once; both `backend` and
`email-worker` reference that image tag so they run identical code without
duplicate build/export work.

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

Email worker health:

```text
python -m app.workers.email_worker --healthcheck
```

The worker writes a heartbeat file while it runs. The health check allows a
long heartbeat age so five-minute model/template jobs are not treated as a
failure.

Compose waits for backend readiness before starting the frontend and worker.

## Email Job Execution

The Docker self-hosted path defaults to:

```bash
EMAIL_JOB_EXECUTION_MODE=worker
EMAIL_WORKER_POLL_INTERVAL_SECONDS=30
EMAIL_WORKER_MAX_JOBS_PER_CYCLE=1
```

This means inbound Microsoft Graph or Resend jobs run outside the web backend.
The Settings page, saved reports, and ordinary API requests should remain
usable while an emailed report is being generated.

To watch background email work:

```bash
docker compose logs -f email-worker
```

`EMAIL_JOB_EXECUTION_MODE=inline` is available only for legacy deployments that
do not run the worker service and instead call `/internal/process-email-jobs`
from an external scheduler.
