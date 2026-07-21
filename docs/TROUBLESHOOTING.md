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

## Frontend Port Is Already Allocated

If startup fails with a message like `Bind for 0.0.0.0:5173 failed: port is
already allocated`, another local process is using the default frontend port.

Regenerate `.env` with a free port and restart:

```bash
python scripts/init_self_hosted_env.py --force --frontend-port 5174 --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model
docker compose up -d --wait
```

Then open `http://localhost:5174`.

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
- use `OPENAI_COMPATIBLE_TIMEOUT_SECONDS=300` for difficult local reasoning or
  multimodal requests
- check external gateway limits; RunPod's public HTTP proxy cannot carry a
  five-minute request, so use a private/direct endpoint or SSH tunnel

## File Upload Fails With Gemini Embedding 403

If files upload in the browser but document processing fails with backend logs
like `gemini-embedding-2:batchEmbedContents` and `403 Forbidden`, the upload
itself worked. The failure happened when Attenly tried to embed the extracted
document chunks for search/retrieval.

If the error says `API key not valid` or `API_KEY_INVALID`, the model names are
not the root cause. Create a new Gemini API key in Google AI Studio, update
`.env`, and recreate the containers. Rotate any key that appeared in logs,
screenshots, chat, or shell history.

If report generation logs say `gemini-2.5-flash is no longer available to new
users`, update `.env` to use the current Gemini default:

```bash
LLM_MODEL=gemini-3.5-flash
```

For a full Gemini Docker pilot, the expected model settings are:

```bash
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768
TEMPLATE_INGEST_PROVIDER=gemini
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash
```

If the error says `GenerativeService.BatchEmbedContents are blocked`, rebuild
from the current source. Current Gemini embedding code uses
`models.embedContent` instead of the blocked synchronous batch method.

Check these first:

- Rotate the Gemini key if it appeared in logs, screenshots, chat, or terminal
  output.
- Confirm `.env` has `EMBEDDING_PROVIDER=gemini`,
  `EMBEDDING_MODEL=gemini-embedding-2`, and `EMBEDDING_DIMENSIONS=768`.
- Confirm the key was created for Gemini API access in Google AI Studio.
- If the key is restricted, allow the Gemini API / Generative Language API.
- If Google returns 403 outside Attenly too, create a new key or check project
  access/billing/region restrictions.

You can test the key directly from PowerShell without printing it:

```powershell
$env:GEMINI_API_KEY = "replace-with-new-key"
$body = @{
  content = @{ parts = @(@{ text = "hello from attenly" }) }
  output_dimensionality = 768
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod `
  -Method Post `
  -Uri "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent" `
  -Headers @{
    "x-goog-api-key" = $env:GEMINI_API_KEY
    "Content-Type" = "application/json"
  } `
  -Body $body

$response.embedding.values.Count
```

The expected output is `768`. If that direct test fails with 403, fix the
Gemini key/project before retesting Attenly.

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
- Graph **Application** permissions (`Mail.Read` and, for outbound email,
  `Mail.Send`) are missing or were mistakenly added as Delegated permissions
- tenant admin consent has not been granted
- mailbox does not exist or the app cannot access it
- the generated Attenly address was not added/routed as an alias to the mailbox
- internal cron route was called without `X-Cron-Secret`

Run the live preflight outside Docker to separate Microsoft configuration from
container configuration:

```bash
python scripts/check_microsoft_graph_connection.py .env
```

Add `--send-test-to you@example.com` to make one real outbound request. The
script never prints the client secret or access token.

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
