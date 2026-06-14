# Attenly

Attenly is an AI-powered document processing and report generation platform for
insurance, underwriting, legal, and operations teams.

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
| `enterprise` | Planned | Company infrastructure | OpenAI-compatible models + Microsoft Graph + company database/storage |

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

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_KEY=your_supabase_service_role_or_anon_key

GEMINI_API_KEY=your_gemini_api_key

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
and an external database. It still uses Gemini for AI until the
OpenAI-compatible model adapter lands.

### 1. Prepare Backend Environment Variables

```bash
cp .env.local.example .env
```

Set these values:

```bash
LOCAL_AUTH_TOKEN=generate-a-long-random-token
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=sqlite:////data/attenly.db
STORAGE_PATH=/data/storage
OUTBOUND_EMAIL_PROVIDER=none
INBOUND_EMAIL_PROVIDER=none
```

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
- `OUTBOUND_EMAIL_PROVIDER=resend` or omitted when email is disabled
- `INBOUND_EMAIL_PROVIDER=resend` or omitted when email is disabled

The backend also has an initial provider-safe runtime slice:

- `AUTH_PROVIDER=local` accepts a configured internal bearer token.
- `DATABASE_PROVIDER=sqlalchemy` stores app data through SQLAlchemy.
- `DATABASE_URL=sqlite:////data/attenly.db` uses a local SQLite file.
- `STORAGE_PROVIDER=filesystem` stores report documents under `STORAGE_PATH`.
- `OUTBOUND_EMAIL_PROVIDER=none` disables outbound email without startup errors.
- `OUTBOUND_EMAIL_PROVIDER=microsoft_graph` sends outbound mail through Microsoft Graph.
- `INBOUND_EMAIL_PROVIDER=none` disables inbound email webhooks.
- `VITE_AUTH_PROVIDER=local` lets the browser app use the same bearer token
  flow without Supabase Auth.

The `local` profile can now run the backend and browser app without Supabase.
It is best for trusted internal pilots, demos, and API testing. Production
enterprise deployments should still move toward SSO/OIDC instead of a shared
bearer token.

The full `enterprise` profile is still planned because OpenAI-compatible LLM
calls, OpenAI-compatible embeddings, Microsoft Graph inbound ingest, and
production enterprise auth are not complete yet.

### Enterprise Example

For a company with on-prem models that expose an OpenAI-compatible API, Microsoft
Graph mail, and no shared SQL service yet, the intended future configuration is
shown in `.env.enterprise.example`.

That full profile is not implemented end-to-end yet. Today, companies can use
the local profile with SQLite, filesystem storage, local token auth, disabled
email, or Microsoft Graph outbound email. The remaining enterprise work is the
OpenAI-compatible model/embedding adapter, Microsoft Graph inbound ingest, and
production-grade SSO/OIDC auth.

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
- Rotate Supabase, Gemini, and Resend keys if they are exposed.
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
