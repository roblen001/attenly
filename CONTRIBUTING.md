# Contributing to Attenly

Attenly welcomes focused issues and pull requests that improve the self-hosted
experience, security, documentation, provider compatibility, and reliability.

## Pull Request Workflow

- Create a focused feature branch from `main` unless a maintainer or issue asks
  you to use another integration branch.
- Open a pull request against `main` and explain the user-visible behavior,
  configuration changes, and validation performed.
- Keep unrelated formatting or refactoring out of the same pull request.
- Do not commit generated databases, local environment files, model weights,
  logs, uploaded documents, credentials, or other private deployment data.
- Maintainers decide when changes are ready to merge and release.

## Project Priorities

The self-hosted release prioritizes a simple on-prem deployment:

- Docker Compose starts the backend and frontend together.
- Local auth works with a configured bearer token.
- SQLite and filesystem storage live in a Docker volume.
- Model providers are selected through environment variables.
- Connectors can be disabled by default and enabled explicitly.

Keep changes focused on those goals. Avoid large refactors unless they make the
self-hosted path simpler, safer, or make provider boundaries clearer.

## Validation

Before opening a pull request, run the checks that match the change.

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
npm run lint
npm run build
npm audit --audit-level=high
```

Before a release, audit `backend/requirements.txt` with `pip-audit` in an
isolated environment and run backend unit/smoke tests against the built image.

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
