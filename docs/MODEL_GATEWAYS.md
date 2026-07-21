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
