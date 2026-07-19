# Troubleshooting

## Docker Desktop Is Not Ready

Check Docker:

```bash
docker version
```

If the client responds but the server does not, start or restart Docker Desktop.
On Windows, Docker's Linux engine may need a machine restart after installation
or engine failures.

## Compose Config Does Not Render

If `.env` does not exist yet, create it with:

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model
```

Replace `replace-with-chat-model` and `replace-with-embedding-model` with model
IDs served by your gateway.

Run the self-hosted env preflight first:

```bash
python scripts/check_self_hosted_env.py .env
```

Validate the config before starting containers:

```bash
docker compose --env-file .env config
```

For source builds:

```bash
docker compose -f compose.yml -f compose.build.yml --env-file .env config
```

Common causes:

- `.env` missing
- placeholder values still present
- invalid provider names
- required provider credentials missing

## Backend Is Unhealthy

Check:

```bash
docker compose logs backend
curl http://localhost:5173/api/ready
```

Readiness checks database, storage, and configuration. Common causes:

- `LOCAL_AUTH_TOKEN` still contains the placeholder value
- `LLM_MODEL` or `EMBEDDING_MODEL` still contains placeholder text
- `OPENAI_COMPATIBLE_BASE_URL` is missing or wrong
- Microsoft Graph is enabled without all `GRAPH_*` values
- SQLite or `/data/storage` is not writable

## Frontend Is Unhealthy

Check:

```bash
docker compose logs frontend
curl http://localhost:5173/health
```

The frontend health endpoint should return:

```text
ok
```

If nginx starts but the browser app cannot call the backend, check:

- frontend container is healthy
- backend container is healthy
- `VITE_API_BASE_URL=/api`
- requests are going to `http://localhost:5173/api/...`

## Model Gateway Cannot Be Reached

From Docker, a model server running on the host machine is usually reached with:

```bash
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
```

Use a normal HTTPS URL for a company network gateway:

```bash
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
```

If generation fails:

- verify the model gateway is running
- verify the model names exist
- verify the embedding dimensions match the embedding model
- verify Docker can reach the gateway URL
- increase `OPENAI_COMPATIBLE_TIMEOUT_SECONDS` for slow local models

## Backend Source Build Is Slow

The backend image includes OCR dependencies. By default, source builds also
pre-cache DocTR OCR models so first OCR use is faster.

For CI or health-only local builds, skip model pre-cache:

```bash
ATTENLY_PRECACHE_DOCTR_MODELS=false docker compose -f compose.yml -f compose.build.yml build backend
```

This does not remove OCR support. It defers model download until first OCR use.

See [`BACKEND_IMAGE_SIZE.md`](BACKEND_IMAGE_SIZE.md) for more detail on the
current image-size tradeoff.

## Microsoft Graph Fails

Check the backend logs first:

```bash
docker compose logs backend
```

Common causes:

- tenant ID, client ID, client secret, or mailbox is wrong
- Graph application permissions are missing
- tenant admin consent has not been granted
- mailbox does not exist or the app cannot access it
- internal cron route was called without `X-Cron-Secret`

For inbound polling, the route is:

```text
POST /internal/process-email-jobs
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

## Data Disappeared

`docker compose down` keeps the Docker volume. `docker compose down -v` deletes
it.

Check volumes:

```bash
docker volume ls
```

The default volume is:

```text
attenly_attenly-data
```

If you used a custom Compose project name, Docker prefixes the volume with that
project name.

## Clean Recreate Without Deleting Data

```bash
docker compose down
docker compose up -d --wait
```

## Clean Recreate And Delete Data

Only run this when you intentionally want to remove local data:

```bash
docker compose down -v
docker compose up -d --wait
```
