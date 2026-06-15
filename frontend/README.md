# Attenly Frontend

React + TypeScript + Vite frontend for Attenly.

## Default Supabase Auth

```bash
cp .env.example .env.local
npm install
npm run dev
```

Keep these values set:

```bash
VITE_AUTH_PROVIDER=supabase
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

## Local No-Supabase Auth

Use this with the backend local profile. The access token entered on the login
page must match the backend `LOCAL_AUTH_TOKEN`.

```bash
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

`VITE_LOCAL_AUTH_TOKEN` can prefill the login form for local development, but it
is bundled into browser code and is not a secret.

## Docker Runtime Config

The frontend Docker image reads runtime settings from environment variables and
writes them to `/config.js` when the container starts. Use the same `VITE_`
names as local development.

For the open-source compose file, the default API URL is:

```bash
VITE_API_BASE_URL=/api
```

That path is served by nginx and proxied to the backend container.
