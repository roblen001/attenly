# Contributing to Attenly

Attenly is being prepared for open-source self-hosting. The current integration
branch for open-source work is `open-sourcing`.

## Branch Policy

- Do not base open-source work on `main`.
- Create feature branches from `open-sourcing`.
- Merge completed open-source branches back into `open-sourcing`.
- The project owner will decide when `open-sourcing` is merged into `main`.

For Codex-assisted changes, use a `codex/` branch name unless a maintainer asks
for a different branch name.

## Local Development Priorities

The current milestone is a simple on-prem pilot:

- Docker Compose starts the backend and frontend together.
- Local auth works with a configured bearer token.
- SQLite and filesystem storage live in a Docker volume.
- Model providers are selected through environment variables.
- Connectors can be disabled by default and enabled explicitly.

Keep changes focused on those goals. Avoid large refactors unless they make the
self-hosted path simpler or make provider boundaries clearer.

## Validation

Before opening or merging an open-source branch, run the checks that match the
change.

For provider profile/configuration changes:

```bash
python scripts/verify_open_source_profiles.py
```

For backend runtime smoke checks, run the relevant scripts from `scripts/`.
At minimum, changes touching SQLAlchemy, local auth, usage limits, persistence,
or Microsoft Graph should run the corresponding smoke script.

For frontend changes:

```bash
cd frontend
npm ci
npm run build
```

For Docker onboarding changes:

```bash
docker compose --env-file .env.example config
docker compose -f compose.yml -f compose.build.yml --env-file .env.example config
docker compose -f compose.yml -f compose.build.yml --env-file .env.docker-test up -d --build --wait
```

Use `.env.docker-test` only for local testing. It is ignored by Git and must not
be committed.

## Secrets

- Do not commit real API keys, auth tokens, tenant IDs, mailbox credentials, or
  model gateway credentials.
- Do not bake secrets into Docker images.
- Frontend `VITE_` values are visible to browser users and must not be treated
  as secrets.
- Local auth tokens are equivalent to passwords and should be long random
  values.

## Provider Changes

When adding or changing a provider, update:

- the relevant `.env.*.example` file
- `README.md`
- `docs/PROVIDER_MATRIX.md`
- `scripts/verify_open_source_profiles.py` when configuration validation should
  cover the provider

Prefer environment-driven provider selection over hard-coded branches that make
self-hosted installs edit application code.
