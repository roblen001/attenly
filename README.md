# Attenly

Attenly turns source documents into structured, editable reports with traceable
references. It can run on one company-controlled Docker host, use local or
hosted models, and optionally process reports through a Microsoft 365 mailbox.

The first self-hosted release is designed as a **single-workspace internal
deployment**:

- one deployment access token unlocks one shared workspace;
- SQLite and uploaded documents persist in one Docker volume;
- report generation and embeddings use either an OpenAI-compatible endpoint or
  Gemini;
- email connectors are disabled until an administrator enables one;
- the web service and long-running email worker run separately so reports stay
  responsive while email jobs are processed.

Local usernames/passwords and browser OIDC redirects are not included in this
release. Organizations that need individual identities can use the existing
Supabase profile or place Attenly behind an identity-aware gateway that supplies
validated JWTs. See [Authentication](#authentication).

## Requirements

- Docker Engine or Docker Desktop with Compose v2
- Python 3.10 or newer for the setup and preflight scripts
- a model endpoint, or a Gemini API key
- at least 8 GB of free space for the published Attenly images, plus model and
  document storage; allow at least 20 GB of free space when building the large
  OCR-enabled backend image from source

## Start in a few minutes

Choose one model setup, create `.env`, and start Compose.

### Option A: Ollama or another OpenAI-compatible endpoint

For a small local Ollama setup with chat, embeddings, and multimodal template
ingestion:

```bash
ollama pull qwen3.5:9b
ollama pull embeddinggemma
```

Create the environment file:

```bash
python scripts/init_self_hosted_env.py --provider openai_compatible --model-base-url http://host.docker.internal:11434/v1 --llm-model qwen3.5:9b --embedding-model embeddinggemma:latest --embedding-dimensions 768 --template-ingest-provider openai_compatible --template-ingest-model qwen3.5:9b
```

Use a private HTTPS URL instead of `host.docker.internal` when the model server
runs elsewhere on the company network. Omit `--template-ingest-provider` and
`--template-ingest-model` if smart template uploads are not needed.

The listed Ollama models were checked against the public Ollama library for this
release. Model availability still changes over time; the setup is not tied to
these particular models.

### Option B: Gemini

```bash
python scripts/init_self_hosted_env.py --provider gemini --llm-model gemini-3.5-flash --embedding-model gemini-embedding-2 --embedding-dimensions 768 --template-ingest-provider gemini --template-ingest-model gemini-3.5-flash
```

The script securely prompts for `GEMINI_API_KEY` if it is not passed on the
command line. Prefer the prompt so the key is not saved in shell history.

### Start Attenly

```bash
python scripts/check_self_hosted_env.py .env
docker compose up -d --wait
```

Open <http://localhost:5173>. Enter the `LOCAL_AUTH_TOKEN` from `.env` on the
login page.

To print only that generated token:

Linux or macOS:

```bash
grep '^LOCAL_AUTH_TOKEN=' .env | cut -d= -f2-
```

PowerShell:

```powershell
(Get-Content .env | Where-Object { $_ -like "LOCAL_AUTH_TOKEN=*" }) -replace "LOCAL_AUTH_TOKEN=", ""
```

Treat this token like a workspace password. Do not place it in a `VITE_`
variable: all frontend configuration is readable by browser users.

## What “OpenAI-compatible” means

The models can run entirely on company hardware. Attenly only requires the
gateway to accept the usual OpenAI request/response shapes at:

- `POST <base-url>/chat/completions`
- `POST <base-url>/embeddings`

Set the base URL including `/v1`, for example:

```dotenv
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-gateway-token
LLM_MODEL=company-chat-model
EMBEDDING_MODEL=company-embedding-model
EMBEDDING_DIMENSIONS=768
```

Ollama, vLLM, LM Studio, or a company-built adapter can provide these routes.
See [Model gateways](docs/MODEL_GATEWAYS.md) for the exact contract, Ollama
server setup, network guidance, and verification commands.

## Microsoft 365 email (optional)

Start with the upload/report flow first. To add Microsoft Graph without
changing the existing model settings:

```bash
python scripts/configure_microsoft_graph_env.py .env --graph-tenant-id replace-with-tenant-id --graph-client-id replace-with-client-id --graph-mailbox attenly@company.com
```

The script prompts securely for the client secret. Then validate the Entra app,
Graph permissions, and mailbox:

```bash
python scripts/check_microsoft_graph_connection.py .env
docker compose up -d --force-recreate --wait
```

For a real outbound test:

```bash
python scripts/check_microsoft_graph_connection.py .env --send-test-to you@company.com
```

The Entra application needs application permissions `Mail.Read` and
`Mail.Send`, with administrator consent. Use a dedicated licensed mailbox.
Verified senders email documents directly to `GRAPH_MAILBOX`; generated
`u_...` addresses are internal routing identifiers and do not need Microsoft
365 aliases in the single-workspace profile.

See [Connectors](docs/CONNECTORS.md) for the complete Entra setup and the sender
verification/report workflow.

## Operations

Check status and logs:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f email-worker
```

Stop without deleting data:

```bash
docker compose down
```

Delete the deployment data volume only when data loss is intended:

```bash
docker compose down -v
```

Changing `.env` requires container recreation:

```bash
docker compose up -d --force-recreate --wait
```

Source code changes require a rebuild:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build --wait
```

The default stack publishes only the frontend port. Nginx proxies `/api` to the
private backend service. `backend` and `email-worker` share the `attenly-data`
volume, which contains `/data/attenly.db` and `/data/storage`.

Back up the volume before upgrades. A simple Docker-volume backup procedure is
documented in [Self-hosting](docs/SELF_HOSTING.md).

To change the browser port, regenerate the environment file with, for example,
`--frontend-port 5174`, or set `ATTENLY_FRONTEND_PORT=5174` in `.env`.

## Authentication

| Mode | Intended use | Current behavior |
| --- | --- | --- |
| `local` | Trusted internal pilot | One shared bearer token and workspace identity |
| `external_jwt` | Company gateway or IdP integration | Validates an HMAC secret or issuer/audience/JWKS; the user pastes/provides the token |
| `supabase` | Existing hosted or multi-user deployment | Supabase browser authentication and provider-backed persistence |

The default local profile is not user-account management. Every person using
the same token can see the same agents and reports. Do not expose it directly to
the public internet. Put production deployments behind HTTPS, firewall rules,
and the organization’s normal access controls.

## Configuration and customization

Provider selection is environment-driven. Companies can switch model,
embedding, storage, authentication, and email providers without editing the
report-generation code. The current support matrix and extension boundaries are
documented in [Provider matrix](docs/PROVIDER_MATRIX.md).

Important example files:

- `.env.example` — recommended single-workspace Docker profile
- `.env.enterprise.example` — external JWT and company endpoint example
- `.env.default.example` — original Supabase-hosted profile
- `.env.local.example` — expanded local profile reference

Never commit `.env`. It is ignored by Git and excluded from Docker build
contexts.

## Development and validation

Run the backend through Docker to match the release environment:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build --wait
```

Frontend checks:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Profile and packaging checks:

```bash
python scripts/verify_open_source_profiles.py
python scripts/check_self_hosted_env.py .env.example
python scripts/smoke_self_hosted_compose.py
```

See [Contributing](CONTRIBUTING.md) for the branch policy and validation
expectations.

## Documentation

- [Self-hosting guide](docs/SELF_HOSTING.md)
- [Model gateways](docs/MODEL_GATEWAYS.md)
- [Microsoft Graph and other connectors](docs/CONNECTORS.md)
- [Provider matrix](docs/PROVIDER_MATRIX.md)
- [Docker architecture](docs/DOCKER_ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security policy](SECURITY.md)

## Security

- Use HTTPS and restrict the frontend to trusted networks/users.
- Use a long random `LOCAL_AUTH_TOKEN` and rotate it if exposed.
- Keep model and connector credentials server-side in `.env` or an external
  secret manager.
- Review uploaded documents and model-provider data policies before processing
  sensitive information.
- Uploaded files are validated, but this release does not include an antivirus
  engine. Integrate malware scanning at the gateway or storage boundary when
  required by company policy.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Attenly is licensed under the [GNU Affero General Public License v3.0 only](LICENSE).
If you modify Attenly and let users interact with that modified version over a
network, the AGPL requires you to offer those users the corresponding source
code under the same license.
