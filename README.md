# Attenly

Attenly is an AI-powered document processing and report generation platform for
enterprise, legal, finance, and operations teams.

The current application supports a self-hosted Docker path as well as its
original hosted-provider stack. The simplest on-prem pilot uses:

- local bearer-token authentication
- SQLite and filesystem storage in one Docker volume
- an OpenAI-compatible model endpoint, including compatible local gateways
- no email connector unless one is explicitly enabled

The open-source direction is to keep those providers as supported defaults while
making each provider replaceable over time.

For the current provider support surface, see
[`docs/PROVIDER_MATRIX.md`](docs/PROVIDER_MATRIX.md). For the remaining release
checklist, see
[`docs/OPEN_SOURCE_RELEASE_CHECKLIST.md`](docs/OPEN_SOURCE_RELEASE_CHECKLIST.md).
For a company-facing Docker pilot guide, see
[`docs/SELF_HOSTING.md`](docs/SELF_HOSTING.md).
Operational details are split into
[`docs/DOCKER_ARCHITECTURE.md`](docs/DOCKER_ARCHITECTURE.md),
[`docs/MODEL_GATEWAYS.md`](docs/MODEL_GATEWAYS.md),
[`docs/CONNECTORS.md`](docs/CONNECTORS.md), and
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Deployment Profiles

Attenly is being organized around three setup profiles.

| Profile | Status | Best For | Providers |
| --- | --- | --- | --- |
| `default` | Supported now | Fastest working setup | Supabase + Gemini + optional Resend |
| `local` | Supported now | No-Supabase internal pilots | Local token auth + SQLAlchemy/SQLite + filesystem storage + Gemini |
| `enterprise` | Supported for core upload/report flow | Company infrastructure | OpenAI-compatible models + SQLAlchemy/filesystem + optional Microsoft Graph email |

The local token is intended for a trusted single-user pilot. Proper local user
accounts are planned before the self-hosted beta is described as company-ready.

The original hosted deployment can keep using a static frontend host such as
Cloudflare Pages, a managed backend host such as Koyeb, and Tiny Cloud for the
rich text editor. The open-source Docker path is portable: the backend and
frontend containers can run anywhere, and the frontend image can self-host
TinyMCE without a Tiny Cloud API key.

## Quick Start: Docker Compose Local Profile

Use this path when you want the backend and frontend running together with
local token auth, a SQLite database file, filesystem storage, and no Supabase.

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model
```

Replace `replace-with-chat-model` and `replace-with-embedding-model` before
running the command. This creates `.env`, generates `LOCAL_AUTH_TOKEN`, and
keeps the default model gateway URL at `http://host.docker.internal:11434/v1`.
Use `--model-base-url` when your model gateway is somewhere else.

For Gemini models, including Gemini smart template ingestion:

```bash
python scripts/init_self_hosted_env.py --provider gemini --llm-model gemini-3.5-flash --embedding-model gemini-embedding-2 --embedding-dimensions 768 --template-ingest-provider gemini --template-ingest-model gemini-3.5-flash
```

This sets Gemini for report generation, embeddings, and multimodal template
upload interpretation. The script prompts for `GEMINI_API_KEY` if you do not
pass `--gemini-api-key`; prefer the prompt for local testing so the key does not
land in shell history.

If `localhost:5173` is already in use, generate the env file with a different
frontend port:

```bash
python scripts/init_self_hosted_env.py --frontend-port 5174 --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model
```

For a Microsoft 365 pilot with Graph email enabled from the start:

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model --email-provider microsoft_graph --graph-tenant-id replace-with-tenant-id --graph-client-id replace-with-client-id --graph-client-secret replace-with-client-secret --graph-mailbox attenly@company.com
```

`--email-provider microsoft_graph` enables both outbound email and inbound
mailbox polling. Use `--outbound-email-provider` and `--inbound-email-provider`
instead if you only want one direction enabled. Replace the `replace-with-*`
values before running the command.

If you prefer to edit the file manually:

```bash
cp .env.example .env
```

Then replace these example values:

```bash
LOCAL_AUTH_TOKEN=generate-a-long-random-token
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=your-key-if-required
LLM_MODEL=company-document-model
EMBEDDING_MODEL=replace-with-embedding-model
```

For Gemini manual setup instead, set:

```bash
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=replace-with-gemini-key
TEMPLATE_INGEST_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash
EMBEDDING_MODEL=gemini-embedding-2
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash
EMBEDDING_DIMENSIONS=768
```

Before starting Docker, check the env file:

```bash
python scripts/check_self_hosted_env.py .env
```

Then start the published images:

```bash
docker compose up -d --wait
```

Open `http://localhost:5173` and enter the same value you set for
`LOCAL_AUTH_TOKEN`.

If `.env` was generated by `init_self_hosted_env.py`, retrieve the generated
token with:

```powershell
(Get-Content .env | Where-Object { $_ -like "LOCAL_AUTH_TOKEN=*" }) -replace "LOCAL_AUTH_TOKEN=", ""
```

The compose file stores SQLite data and uploaded files in the `attenly-data`
Docker volume. The frontend container uses a same-origin `/api` proxy to the
backend, so browser users only need the frontend URL. The open-source frontend
container also self-hosts TinyMCE at `/tinymce/tinymce.min.js`; no Tiny Cloud
API key is required for this Docker path.

See [`docs/SELF_HOSTING.md`](docs/SELF_HOSTING.md) for model gateway, Microsoft
Graph connector, local auth, and Docker volume guidance.
See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) if Docker starts but a
service is unhealthy or a model/connector cannot be reached.

To run an automated published-image smoke test without keeping containers or
volumes afterward:

```bash
python scripts/smoke_self_hosted_compose.py
```

To build from this checkout instead of pulling published images:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build --wait
```

During open-source preparation the compose file defaults to the
`open-sourcing` image tag. Versioned releases will use immutable tags rather
than relying on `latest`. Forks, company mirrors, or private registries can
override the images without editing the file:

```bash
ATTENLY_IMAGE_NAMESPACE=your-ghcr-owner
ATTENLY_IMAGE_TAG=open-sourcing
```

or:

```bash
ATTENLY_BACKEND_IMAGE=registry.company.com/attenly-backend:2026.06
ATTENLY_FRONTEND_IMAGE=registry.company.com/attenly-frontend:2026.06
```

## Quick Start: Default Profile

Use this path if you want the app to run the same way it works today.

### 1. Prepare Environment Variables

Copy the default example:

```bash
cp .env.default.example .env
```

Fill in:

```bash
APP_PROFILE=default
AUTH_PROVIDER=supabase
DATABASE_PROVIDER=supabase
STORAGE_PROVIDER=supabase
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
TEMPLATE_INGEST_PROVIDER=gemini

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_KEY=your_supabase_service_role_or_anon_key

GEMINI_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-3.5-flash
EMBEDDING_MODEL=gemini-embedding-2
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash

APP_URL=http://localhost:5173
PUBLIC_API_URL=http://localhost:5173/api
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Email ingest is optional. Add these only if you use Resend inbound email:

```bash
RESEND_API_KEY=re_your_resend_api_key
RESEND_WEBHOOK_SECRET=your_resend_webhook_secret
INTERNAL_CRON_SECRET=generate-a-long-random-secret
OUTBOUND_EMAIL_PROVIDER=resend
INBOUND_EMAIL_PROVIDER=resend
```

Redis is not required for the current app.

The open-source Docker frontend self-hosts TinyMCE by default. Existing hosted
frontend deployments, such as Cloudflare Pages, can keep Tiny Cloud by setting:

```bash
VITE_TINYMCE_MODE=cloud
VITE_TINYMCE_API_KEY=your_tinymce_cloud_api_key
```

### 2. Run the Backend Container

If you are using a published image:

```bash
docker pull ghcr.io/attenly/attenly-backend:latest

docker run --name attenly-backend \
  --env-file .env \
  -p 8080:8080 \
  ghcr.io/attenly/attenly-backend:latest
```

If you are building from this repository:

```bash
docker build -t attenly-backend:local backend

docker run --name attenly-backend \
  --env-file .env \
  -p 8080:8080 \
  attenly-backend:local
```

Health check:

```bash
curl http://localhost:8080/health
```

Readiness check:

```bash
curl http://localhost:8080/ready
```

### 3. Run the Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Quick Start: Local No-Supabase Profile

Use this path for an internal pilot that avoids Supabase auth, Supabase storage,
and an external database. It uses Gemini by default, or you can switch the AI
settings to an OpenAI-compatible internal endpoint.

### 1. Prepare Backend Environment Variables

```bash
cp .env.local.example .env
```

Set these values:

```bash
LOCAL_AUTH_TOKEN=generate-a-long-random-token
DATABASE_URL=sqlite:////data/attenly.db
STORAGE_PATH=/data/storage
OUTBOUND_EMAIL_PROVIDER=none
INBOUND_EMAIL_PROVIDER=none
```

With inbound email set to `none`, the backend does not mount inbound webhook or
email job-processing routes, and the Settings page shows email ingest as
unavailable instead of prompting users to configure Resend.

For Gemini, set:

```bash
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
```

For an OpenAI-compatible internal model endpoint, set:

```bash
LLM_PROVIDER=openai_compatible
EMBEDDING_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=https://models.company.internal/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-internal-model-token
LLM_MODEL=company-document-model
EMBEDDING_MODEL=replace-with-embedding-model
```

Leave `OPENAI_COMPATIBLE_API_KEY` blank only if your internal gateway does not
require authentication.

Uploaded template ingestion is separate from normal report extraction. It asks
AI to understand layout, formatting, tables, headings, placeholders, and
document intent, so complex DOCX/PDF templates need a high-capability
multimodal model. If users will build templates directly in the editor, keep it
disabled:

```bash
TEMPLATE_INGEST_PROVIDER=disabled
```

For simple DOCX/HTML conversion without AI layout reasoning:

```bash
TEMPLATE_INGEST_PROVIDER=basic
```

For the current supported smart template ingestion path:

```bash
TEMPLATE_INGEST_PROVIDER=gemini
TEMPLATE_INGEST_MODEL_NAME=gemini-3.5-flash
```

For OpenAI or an OpenAI-compatible gateway, use the same base URL and API key
settings as the core model adapter:

```bash
TEMPLATE_INGEST_PROVIDER=openai_compatible
TEMPLATE_INGEST_MODEL=gpt-4.1
OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
OPENAI_COMPATIBLE_API_KEY=your_openai_or_gateway_key
```

OpenAI-compatible template ingestion is a hard multimodal task, so use a strong
model endpoint that can reason over uploaded PDFs/DOCX/HTML and preserve
layout. The app keeps endpoint-shape details inside the adapter instead of
requiring extra setup flags.

### 2. Run the Backend Container with a Data Volume

```bash
docker pull ghcr.io/attenly/attenly-backend:latest

docker run --name attenly-backend \
  --env-file .env \
  -p 8080:8080 \
  -v attenly-data:/data \
  ghcr.io/attenly/attenly-backend:latest
```

### 3. Run the Frontend in Local Auth Mode

```bash
cd frontend
cp .env.example .env.local
```

Set:

```bash
VITE_AUTH_PROVIDER=local
VITE_API_BASE_URL=http://localhost:8080
VITE_LOCAL_AUTH_USER_ID=local-admin
VITE_LOCAL_AUTH_EMAIL=local-admin@example.com
VITE_LOCAL_AUTH_DISPLAY_NAME=Local Admin
```

Then start the frontend:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`, enter the same token you set as
`LOCAL_AUTH_TOKEN`, and continue to the app. You can optionally set
`VITE_LOCAL_AUTH_TOKEN` to prefill the login form for development, but frontend
environment values are visible in the browser bundle and are not secrets.

For Docker Compose, the frontend image reads these same `VITE_` settings at
container startup instead of baking them into the build. The default compose
value is `VITE_API_BASE_URL=/api`, which routes browser calls through the
frontend nginx proxy to the backend container.

## Provider Roadmap

The current open-source cleanup keeps the default providers working and documents
the target adapter model.

### Default Providers

The default profile uses the providers the app was originally built to support:

- `APP_PROFILE=default`
- `AUTH_PROVIDER=supabase`
- `DATABASE_PROVIDER=supabase`
- `STORAGE_PROVIDER=supabase`
- `LLM_PROVIDER=gemini`
- `EMBEDDING_PROVIDER=gemini`
- `TEMPLATE_INGEST_PROVIDER=gemini`
- `OUTBOUND_EMAIL_PROVIDER=resend` or omitted when email is disabled
- `INBOUND_EMAIL_PROVIDER=resend` or omitted when email is disabled

The backend also has an initial provider-safe runtime slice:

- `AUTH_PROVIDER=local` accepts a configured internal bearer token.
- `AUTH_PROVIDER=external_jwt` trusts bearer tokens from an existing IdP,
  reverse proxy, or API gateway using either a shared HMAC secret or JWKS URL.
- `DATABASE_PROVIDER=sqlalchemy` stores app data through SQLAlchemy.
- `DATABASE_URL=sqlite:////data/attenly.db` uses a local SQLite file.
- `STORAGE_PROVIDER=filesystem` stores report documents under `STORAGE_PATH`.
- `OUTBOUND_EMAIL_PROVIDER=none` disables outbound email without startup errors.
- `OUTBOUND_EMAIL_PROVIDER=microsoft_graph` sends outbound mail through Microsoft Graph.
- `INBOUND_EMAIL_PROVIDER=none` disables inbound email webhooks and email job
  processing routes.
- `INBOUND_EMAIL_PROVIDER=microsoft_graph` polls a Microsoft 365 mailbox through
  Microsoft Graph and creates email jobs without Resend.
- `VITE_AUTH_PROVIDER=local` lets the browser app use the same bearer token
  flow without Supabase Auth.
- `VITE_AUTH_PROVIDER=external_jwt` lets users paste an externally issued JWT
  into the same token login flow while the backend validates the token.
- `VITE_TINYMCE_MODE=self_hosted` loads TinyMCE from the frontend container
  instead of Tiny Cloud.
- `LLM_PROVIDER=openai_compatible` sends extraction and quote prompts to an
  OpenAI-compatible `/chat/completions` endpoint.
- `EMBEDDING_PROVIDER=openai_compatible` sends vector embeddings to an
  OpenAI-compatible `/embeddings` endpoint.
- `TEMPLATE_INGEST_PROVIDER=disabled` leaves uploaded template conversion off.
- `TEMPLATE_INGEST_PROVIDER=basic` enables simple DOCX/HTML conversion without
  AI and does not support PDF/layout reasoning.
- `TEMPLATE_INGEST_PROVIDER=gemini` enables the current smart template upload
  path and should use a strong multimodal model.
- `TEMPLATE_INGEST_PROVIDER=openai_compatible` enables smart template upload
  through an OpenAI-compatible multimodal model endpoint.

The `local` profile can now run the backend and browser app without Supabase.
It is best for trusted internal pilots, demos, and API testing. Production
enterprise deployments can use `AUTH_PROVIDER=external_jwt` when an existing
IdP, reverse proxy, or API gateway already issues bearer tokens. Full browser
OIDC redirect login is still a later adapter.

When leaving Supabase Auth, also use `DATABASE_PROVIDER=sqlalchemy` and
`STORAGE_PROVIDER=filesystem`. The current Supabase database/storage paths rely
on Supabase JWTs for user-scoped operations.

Usage limits now work with either Supabase RPCs or SQLAlchemy. The app
hard-blocks smart AI work once a user reaches their monthly limit. SQLAlchemy
profiles store limits in `user_quotas` and detailed operation history in
`usage_logs`; admins can raise or lower `user_quotas.monthly_limit_cad` for a
user without changing application code. Unknown or internal models use
`DEFAULT_MODEL_INPUT_COST_PER_MILLION_CAD` and
`DEFAULT_MODEL_OUTPUT_COST_PER_MILLION_CAD` for accounting.

SQLAlchemy profiles also include the email ingest data model:
`email_ingest_endpoints`, `verified_senders`, `email_jobs`, and
`email_poll_state`. The user-facing email settings service can now manage those
records without Supabase. The email job processor now uses provider-specific
job stores plus configured storage/report persistence, so SQLAlchemy and
filesystem installs can process jobs. Microsoft Graph inbound polling can now
create jobs from a company mailbox.

The remaining non-email enterprise adapter work is full browser OIDC login.
OpenAI-compatible template ingestion now supports multimodal request shapes
internally; individual gateways still need a model endpoint that accepts
uploaded file or image input.

### Enterprise Example

For a company with internal models that expose an OpenAI-compatible API and no
shared SQL service yet, use
`.env.enterprise.example`. The core upload/report flow can run with SQLite,
filesystem storage, local token auth, OpenAI-compatible chat/embeddings, and
email disabled or Microsoft Graph email. For production auth, switch to
`AUTH_PROVIDER=external_jwt` when your company already has an IdP, reverse
proxy, or API gateway that issues JWT bearer tokens. The Docker frontend can
self-host TinyMCE, so this path does not require a Tiny Cloud API key.
SQLite profiles auto-create SQLAlchemy tables by default with
`DATABASE_AUTO_CREATE_TABLES=true`.
Set `TEMPLATE_INGEST_PROVIDER=disabled` if users will build templates in the
editor, or `TEMPLATE_INGEST_PROVIDER=basic` for simple DOCX/HTML conversion.
Use `TEMPLATE_INGEST_PROVIDER=openai_compatible` for OpenAI or an internal
OpenAI-compatible gateway backed by a multimodal model. Use Gemini when you
prefer the default smart multimodal template provider.

## Development Setup

From the repository root, verify the documented open-source profile combinations
without contacting any external provider:

```bash
python scripts/verify_open_source_profiles.py
```

CI runs this provider profile verifier on pull requests and pushes to `main`
or `open-sourcing`. It also runs the frontend production build, validates the
open-source compose config, and builds the frontend Docker image.

Docker image publishing is handled separately by the `Publish Docker Images`
workflow. It publishes backend and frontend images to GHCR on `main`,
`open-sourcing`, version tags, or manual dispatch. By default it publishes under
the GitHub repository owner; set a `GHCR_NAMESPACE` repository variable to use a
different package namespace such as an official organization.

After installing backend dependencies, smoke test the local-auth SQLite runtime
routes:

```bash
python scripts/smoke_backend_runtime.py
```

The CI-friendly SQLAlchemy persistence smoke checks custom agents, saved
reports, and filesystem document storage without starting the web app:

```bash
python scripts/smoke_sqlalchemy_persistence.py
```

### Backend

```bash
cd backend
python -m venv attenly-backend
attenly-backend\Scripts\activate
pip install -r requirements.txt
copy ..\.env.default.example .env
python -m app.main
```

On macOS/Linux, activate the environment with:

```bash
source attenly-backend/bin/activate
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Supabase Setup

The default profile requires a Supabase project.

Apply the SQL files in `supabase/migrations` and configure the storage bucket
using `supabase/storage_setup.sql`.

At minimum, configure:

- Supabase Auth
- Supabase database migrations
- Supabase Storage bucket for report documents
- Supabase service role key for backend system operations

## Email Ingest

Email ingest is optional. The core upload and report workflows can run without
Resend.

When `INBOUND_EMAIL_PROVIDER=none`, the backend leaves inbound email routes
unmounted. Authenticated users can still open Settings; the email ingest panel
reports that the feature is unavailable by configuration.

To use the current Resend-based email ingest:

```bash
RESEND_API_KEY=re_your_resend_api_key
RESEND_WEBHOOK_SECRET=your_resend_webhook_secret
EMAIL_INGEST_DOMAIN=mail.your-company.com
EMAIL_FROM_DOMAIN=mail.your-company.com
EMAIL_FROM_ADDRESS=noreply@mail.your-company.com
INTERNAL_CRON_SECRET=generate-a-long-random-secret
```

Point the Resend inbound webhook at:

```text
POST /webhooks/email-inbound
```

Process pending email jobs by calling:

```text
POST /internal/process-email-jobs
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

SQLAlchemy profiles now have local tables for email aliases, verified senders,
email jobs, and poll state. The background processor can claim and complete
jobs through SQLAlchemy and filesystem-backed report persistence.

To use Microsoft Graph inbound polling, configure:

```bash
INBOUND_EMAIL_PROVIDER=microsoft_graph
GRAPH_TENANT_ID=your-tenant-id
GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_MAILBOX=attenly@company.com
INTERNAL_CRON_SECRET=generate-a-long-random-secret
```

The Graph app registration needs Microsoft Graph application mail read
permission for the mailbox. Call the same cron endpoint:

```text
POST /internal/process-email-jobs
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

When Graph inbound is enabled, that endpoint first polls the configured mailbox,
stores valid attachments through the configured storage provider, creates email
jobs, and then processes pending jobs. Use `POST /internal/poll-inbound-email`
with the same header to poll without processing queued jobs.

## Security Notes

- Keep secrets in environment variables or a secret manager.
- Do not bake secrets into Docker images.
- Use HTTPS in production.
- Restrict `CORS_ORIGINS` to known frontend origins.
- Rotate Supabase, Gemini, OpenAI-compatible, Graph, and Resend keys if they are exposed.
- Treat local auth as a trusted internal pilot mode. The bearer token is
  equivalent to a password and should be rotated if exposed.
- Do not treat `VITE_LOCAL_AUTH_TOKEN` as a secret. Frontend `VITE_` values are
  bundled into browser code, so that setting is only a convenience prefill.
- Redis is not required by the current runtime.

## Troubleshooting

See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) for common local
Docker issues, including port conflicts, unhealthy containers, Microsoft Graph
setup failures, and Gemini embedding `403 Forbidden` errors during file upload.

## Contributing

The first open-source milestone is onboarding clarity:

- keep the current default profile working
- remove stale infrastructure requirements
- support the local no-Supabase pilot path
- then refactor providers behind stable interfaces in later branches

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch policy, validation commands,
and provider-change expectations.

## License

Attenly is licensed under the GNU Affero General Public License v3.0 only
(`AGPL-3.0-only`). See [`LICENSE`](LICENSE).

AGPL allows internal use and modification, but if someone distributes Attenly or
offers a modified version over a network, they must provide the corresponding
source code under AGPL terms. Proprietary resale, white-label distribution, or
managed hosting without those AGPL obligations requires a separate commercial
license from the project owner.
