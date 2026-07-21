# Model Gateway Guide

The default self-hosted profile uses an OpenAI-compatible model gateway. This
keeps Attenly independent from any single model vendor.

## Required Settings

```bash
LLM_PROVIDER=openai_compatible
EMBEDDING_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=300
LLM_MODEL=replace-with-chat-model
EMBEDDING_MODEL=replace-with-embedding-model
EMBEDDING_DIMENSIONS=1536
```

Use `OPENAI_COMPATIBLE_API_KEY=` blank only for trusted local endpoints that do
not require authentication.

The default model timeout is five minutes so difficult reasoning and
multimodal template requests can finish. The frontend proxy waits up to ten
minutes, leaving time for the backend to return a useful timeout response.
External proxies can impose shorter limits that Attenly cannot override. For
example, [RunPod's public HTTP proxy](https://docs.runpod.io/pods/configuration/expose-ports)
has a 100-second connection limit; use a secured direct endpoint or SSH tunnel
for five-minute requests.

## Local Gateway on the Docker Host

Use `host.docker.internal` when the gateway runs on the same workstation as
Docker Desktop:

```bash
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
```

Common local gateway examples include Ollama, LM Studio, vLLM, and internal
OpenAI-compatible adapters.

The model names must match the names served by that gateway.

## Ollama on a Company Linux Server

Ollama can run on the same server as Attenly or on a separate GPU server. In
Ollama terminology, `pull` downloads a model to disk, while `run` loads it into
RAM/VRAM and performs a request. An idle model can leave GPU memory without
being deleted; Ollama loads it again automatically on the next request.

Install Ollama using the current
[official Linux instructions](https://docs.ollama.com/linux), then download the
models. This pair is a practical small example rather than a requirement:

```bash
ollama pull qwen3.5:9b
ollama pull embeddinggemma
ollama list
```

- `qwen3.5:9b` is the chat, reasoning, and vision model in this example.
- `embeddinggemma:latest` is the embedding model and returns 768-dimensional
  vectors.

Warm the models and inspect GPU residency:

```bash
ollama run qwen3.5:9b "Reply only with OK"
ollama run embeddinggemma:latest "warmup"
ollama ps
```

Ollama normally removes idle models from RAM/VRAM after five minutes; this does
not delete them. To reduce cold starts, configure the Ollama server process
with a longer idle period. On a systemd installation, run
`sudo systemctl edit ollama` and add:

```ini
[Service]
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

Then apply the service change:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Only set `OLLAMA_MAX_LOADED_MODELS=2` when the server has enough RAM/VRAM for
both models. `OLLAMA_HOST=0.0.0.0:11434` makes Ollama reachable from containers
and other machines, but Ollama does not provide application authentication for
this listener. Restrict port 11434 to the Attenly host with a private network or
firewall. For production, prefer a TLS/authenticated reverse proxy or internal
model gateway rather than exposing Ollama directly to the internet.

Use this base URL when Ollama runs on the same host as Attenly Docker:

```bash
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:11434/v1
```

Use private DNS or a private IP when Ollama runs on another company server:

```bash
OPENAI_COMPATIBLE_BASE_URL=http://ollama.internal.company:11434/v1
```

Generate the complete Attenly environment for the example models:

```bash
python scripts/init_self_hosted_env.py --provider openai_compatible --model-base-url http://host.docker.internal:11434/v1 --llm-model qwen3.5:9b --embedding-model embeddinggemma:latest --embedding-dimensions 768 --template-ingest-provider openai_compatible --template-ingest-model qwen3.5:9b
```

Replace the base URL with the private server URL when Ollama is remote. The
generated `.env` uses a five-minute model-request timeout. Start Attenly and
verify the backend can see Ollama:

```bash
python scripts/check_self_hosted_env.py .env
docker compose up -d --wait
docker compose exec -T backend curl -fsS http://host.docker.internal:11434/v1/models
```

If Ollama is remote, use its private URL in the last command. The
[Ollama OpenAI compatibility guide](https://docs.ollama.com/api/openai-compatibility)
documents the `/v1` API implemented by Ollama.

## Bring Your Own OpenAI-Compatible Endpoint

An endpoint is "OpenAI-compatible" when it accepts the same route names and
core JSON request/response shapes. It does not need to call OpenAI, use OpenAI
models, or expose company logic to Attenly. A company can put routing, model
selection, retrieval, policy enforcement, logging, or other custom logic
behind the endpoint.

Set the base URL to the prefix before the operation name:

```bash
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-gateway-token
```

With that base URL, Attenly expects:

| Purpose | Required route | Minimum request | Minimum successful response |
| --- | --- | --- | --- |
| Reports and questions | `POST /v1/chat/completions` | `model`, `messages` | `choices[0].message.content` |
| Document embeddings | `POST /v1/embeddings` | `model`, `input` as a string array | `data[]` entries containing `index` and `embedding` |
| Model discovery | `GET /v1/models` | None | Recommended for diagnostics; not required by normal Attenly requests |

The chat route should accept ordinary user messages plus `temperature`.
Attenly may also send `response_format={"type":"json_object"}` and retries
without it when a gateway rejects that option with a normal client error. The
embedding route must return one numeric vector for every input, in input order;
set `EMBEDDING_DIMENSIONS` to the actual vector length.

When `OPENAI_COMPATIBLE_API_KEY` is set, Attenly sends it as:

```text
Authorization: Bearer replace-with-gateway-token
```

Return JSON with a normal 2xx HTTP status for successful requests and a useful
JSON error with a 4xx/5xx status for failures. Do not return an HTML proxy error
page from these API routes.

Smart template ingestion additionally requires a multimodal endpoint. Attenly
tries `POST /v1/responses` with an original file when available, then compatible
file/image content through `POST /v1/chat/completions`. At minimum, a custom
multimodal chat endpoint should accept OpenAI-style content parts containing
`type: "text"` and `type: "image_url"`, including base64 data URLs, and return
the result in `choices[0].message.content`. If the endpoint is text-only, use:

```bash
TEMPLATE_INGEST_PROVIDER=basic
```

Configure any custom endpoint with the initializer:

```bash
python scripts/init_self_hosted_env.py --provider openai_compatible --model-base-url https://models.company.internal/v1 --model-api-key replace-with-gateway-token --llm-model company-chat-model --embedding-model company-embedding-model --embedding-dimensions 768
```

Add `--template-ingest-provider openai_compatible --template-ingest-model
company-multimodal-model` only when the gateway supports the multimodal contract
above. Keep model selection and custom logic inside the gateway; switching
Attenly to a different gateway or model then only requires `.env` changes and a
backend container recreation, not application-code changes.

## Company Network Gateway

Use a normal HTTPS URL for a company gateway:

```bash
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-gateway-token
LLM_MODEL=company-document-model
EMBEDDING_MODEL=replace-with-embedding-model
```

The backend container must be able to reach this URL from inside Docker.

## Gemini

Use Gemini when you want Google-hosted report generation, embeddings, and
multimodal template ingestion:

```bash
python scripts/init_self_hosted_env.py --provider gemini --llm-model gemini-3.5-flash --embedding-model gemini-embedding-2 --embedding-dimensions 768 --template-ingest-provider gemini --template-ingest-model gemini-3.5-flash
```

Equivalent env settings:

```bash
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=replace-with-gemini-key
LLM_MODEL=gemini-3.5-flash
EMBEDDING_MODEL=gemini-embedding-2
TEMPLATE_INGEST_PROVIDER=gemini
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash
EMBEDDING_DIMENSIONS=768
```

## Template Ingestion

For the simplest pilot:

```bash
TEMPLATE_INGEST_PROVIDER=disabled
```

For simple DOCX/HTML conversion without AI layout reasoning:

```bash
TEMPLATE_INGEST_PROVIDER=basic
```

For smart template upload with an OpenAI-compatible endpoint:

```bash
TEMPLATE_INGEST_PROVIDER=openai_compatible
TEMPLATE_INGEST_MODEL=company-multimodal-model
```

For smart template upload with Gemini:

```bash
TEMPLATE_INGEST_PROVIDER=gemini
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash
```

Smart template ingestion needs a strong multimodal model. Do not enable it
until the core upload/report flow works.

## Common Model Setup Problems

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| Backend is unhealthy at startup | Placeholder model/env values remain in `.env`. | `docker compose logs backend` |
| Report generation fails quickly | Chat model name is not served by the gateway. | Verify `LLM_MODEL` with the gateway. |
| Embedding step fails | Embedding model name or dimensions do not match the gateway. | Verify `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS`. |
| Container cannot reach model server | Wrong host URL from Docker's network. | Try `host.docker.internal` for host-local servers. |
| Requests time out | Model is too slow for the configured timeout, or an external proxy has a shorter limit. | Keep `OPENAI_COMPATIBLE_TIMEOUT_SECONDS=300` and check the gateway/proxy limit. |
