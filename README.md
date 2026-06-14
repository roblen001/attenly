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
| `local` | Backend supported now | Local backend/API trials without Supabase | Local auth + SQLAlchemy/SQLite + filesystem storage + Gemini |
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

The `local` backend profile is now useful for API-level testing without
Supabase. The browser frontend still uses Supabase auth, so full no-Supabase
end-to-end app startup needs the frontend local-auth adapter.

The full `enterprise` profile is still planned because OpenAI-compatible LLM
calls, OpenAI-compatible embeddings, Microsoft Graph inbound ingest, and
frontend enterprise auth are not complete yet.

### Enterprise Example

For a company with on-prem models that expose an OpenAI-compatible API, Microsoft
Graph mail, and no shared SQL service yet, the intended future configuration is
shown in `.env.enterprise.example`.

That profile is not implemented end-to-end yet. If selected today, the backend
will fail startup with clear configuration errors for the provider pieces that
are still planned.

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
- Redis is not required by the current runtime.

## Contributing

The first open-source milestone is onboarding clarity:

- keep the current default profile working
- remove stale infrastructure requirements
- document local and enterprise provider targets
- then refactor providers behind stable interfaces in later branches

## License

License information will be added as part of the open-source preparation work.
