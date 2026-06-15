# Attenly

Attenly is an AI-powered document processing and report generation platform for
enterprise, legal, finance, and operations teams.

The current application is built around a proven default stack:

- Supabase for authentication, application data, and document storage
- Gemini for document extraction, quote extraction, templates, and embeddings
- Resend for optional email ingest

The open-source direction is to keep those providers as supported defaults while
making each provider replaceable over time.

## Deployment Profiles

Attenly is being organized around three setup profiles.

| Profile | Status | Best For | Providers |
| --- | --- | --- | --- |
| `default` | Supported now | Fastest working setup | Supabase + Gemini + optional Resend |
| `local` | Supported now | No-Supabase internal pilots | Local token auth + SQLAlchemy/SQLite + filesystem storage + Gemini |
| `enterprise` | Supported for core upload/report flow | Company infrastructure | OpenAI-compatible models + Microsoft Graph outbound + company database/storage |

Companies do not need to replace every dependency before first launch. They can
start with the default profile, prove the app internally, then replace one
provider at a time.

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
TEMPLATE_INGEST_MODEL_NAME=gemini-2.5-pro

APP_URL=http://localhost:5173
API_URL=http://localhost:8080
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
EMBEDDING_MODEL=company-embedding-model
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
TEMPLATE_INGEST_MODEL_NAME=gemini-2.5-pro
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
- `DATABASE_PROVIDER=sqlalchemy` stores app data through SQLAlchemy.
- `DATABASE_URL=sqlite:////data/attenly.db` uses a local SQLite file.
- `STORAGE_PROVIDER=filesystem` stores report documents under `STORAGE_PATH`.
- `OUTBOUND_EMAIL_PROVIDER=none` disables outbound email without startup errors.
- `OUTBOUND_EMAIL_PROVIDER=microsoft_graph` sends outbound mail through Microsoft Graph.
- `INBOUND_EMAIL_PROVIDER=none` disables inbound email webhooks and email job
  processing routes.
- `VITE_AUTH_PROVIDER=local` lets the browser app use the same bearer token
  flow without Supabase Auth.
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
enterprise deployments should still move toward SSO/OIDC instead of a shared
bearer token.

The remaining enterprise adapter work is Microsoft Graph inbound ingest and
production SSO/OIDC auth. OpenAI-compatible template ingestion now supports
multimodal request shapes internally; individual gateways still need a model
endpoint that accepts uploaded file or image input.

### Enterprise Example

For a company with internal models that expose an OpenAI-compatible API,
Microsoft Graph mail, and no shared SQL service yet, use
`.env.enterprise.example`. The core upload/report flow can run with SQLite,
filesystem storage, local token auth, OpenAI-compatible chat/embeddings, and
email disabled or Microsoft Graph outbound email.
Set `TEMPLATE_INGEST_PROVIDER=disabled` if users will build templates in the
editor, or `TEMPLATE_INGEST_PROVIDER=basic` for simple DOCX/HTML conversion.
Use `TEMPLATE_INGEST_PROVIDER=openai_compatible` for OpenAI or an internal
OpenAI-compatible gateway backed by a multimodal model. Use Gemini when you
prefer the default smart multimodal template provider.

## Development Setup

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

When `INBOUND_EMAIL_PROVIDER=none`, the backend leaves the Resend webhook and
email job processor unmounted. Authenticated users can still open Settings; the
email ingest panel reports that the feature is unavailable by configuration.

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

## Contributing

The first open-source milestone is onboarding clarity:

- keep the current default profile working
- remove stale infrastructure requirements
- support the local no-Supabase pilot path
- then refactor providers behind stable interfaces in later branches

## License

License information will be added as part of the open-source preparation work.
