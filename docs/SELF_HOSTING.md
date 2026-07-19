# Self-Hosting Guide

This guide describes the simplest company pilot path: one Docker Compose stack,
local token auth, SQLite plus filesystem storage in a Docker volume, and a
model endpoint selected through environment variables.

## 1. Start From the Docker Profile

Copy the example environment file:

```bash
cp .env.example .env
```

At minimum, replace these values:

```bash
LOCAL_AUTH_TOKEN=replace-with-a-long-random-token
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=replace-with-chat-model
EMBEDDING_MODEL=replace-with-embedding-model
```

Then start the stack:

```bash
docker compose up -d --wait
```

Open `http://localhost:5173` and enter `LOCAL_AUTH_TOKEN`.

Optional preflight before starting Docker:

```bash
python scripts/check_self_hosted_env.py .env
```

This catches common missing or placeholder values before containers start.

## 2. Storage Model

The default Compose stack uses one Docker volume:

```bash
DATABASE_URL=sqlite:////data/attenly.db
STORAGE_PROVIDER=filesystem
STORAGE_PATH=/data/storage
```

This keeps app data and generated files under `/data` inside the backend
container, backed by the `attenly-data` Docker volume. Recreating containers
does not remove the volume.

Do not use `docker compose down -v` unless you intend to delete local data.

## 3. Model Gateway Options

Attenly uses OpenAI-compatible endpoints for the default self-hosted Docker
path:

```bash
LLM_PROVIDER=openai_compatible
EMBEDDING_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_COMPATIBLE_API_KEY=
LLM_MODEL=company-chat-model
EMBEDDING_MODEL=company-embedding-model
```

Use `host.docker.internal` when the model gateway is running on the host
machine, such as Ollama, LM Studio, vLLM, or an internal gateway exposed from
the workstation.

Use a normal HTTPS URL when the gateway is already reachable on the company
network:

```bash
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-gateway-token
```

Template ingestion is disabled in the simplest profile:

```bash
TEMPLATE_INGEST_PROVIDER=disabled
```

Enable it only after the core upload/report flow works. Smart template ingestion
requires a multimodal model endpoint.

## 4. Connector Options

Email connectors are off by default:

```bash
OUTBOUND_EMAIL_PROVIDER=none
INBOUND_EMAIL_PROVIDER=none
```

Use this mode for the first local pilot unless email ingestion is part of the
test.

For Microsoft Graph outbound email:

```bash
OUTBOUND_EMAIL_PROVIDER=microsoft_graph
GRAPH_TENANT_ID=your-tenant-id
GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_FROM_EMAIL=attenly@company.com
```

For Microsoft Graph inbound email polling:

```bash
INBOUND_EMAIL_PROVIDER=microsoft_graph
GRAPH_TENANT_ID=your-tenant-id
GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_MAILBOX=attenly@company.com
INTERNAL_CRON_SECRET=generate-a-long-random-secret
```

Inbound polling is triggered through the internal route documented in
`README.md`. Keep that route behind internal network controls.

## 5. Auth Options

The simplest pilot uses local token auth:

```bash
AUTH_PROVIDER=local
LOCAL_AUTH_TOKEN=replace-with-a-long-random-token
```

This is intended for a trusted internal pilot. The token is equivalent to a
password.

For a company deployment where another component already issues bearer tokens,
use external JWT validation:

```bash
AUTH_PROVIDER=external_jwt
EXTERNAL_JWT_ISSUER=https://idp.company.internal
EXTERNAL_JWT_AUDIENCE=attenly
EXTERNAL_JWT_JWKS_URL=https://idp.company.internal/.well-known/jwks.json
```

Full browser OIDC redirect login is not implemented yet. External JWT mode
expects a token to already exist.

## 6. Validation Checklist

After startup, verify:

```bash
curl http://localhost:5173/health
curl http://localhost:5173/api/ready
```

Expected:

- frontend health returns `ok`
- backend readiness reports healthy database, storage, and configuration
- only the frontend port is published to the host
- uploaded files and generated reports survive container recreation

For a local source build:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build --wait
```

For cleanup without deleting the data volume:

```bash
docker compose down
```

For cleanup that deletes local data:

```bash
docker compose down -v
```

## 7. License Notice

Attenly is licensed as `AGPL-3.0-only`. Internal use and internal modification
are allowed under the license. If you distribute Attenly or offer a modified
version over a network, you must provide the corresponding source code under
AGPL terms unless you have a separate commercial license from the project owner.
