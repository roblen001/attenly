# Open Source Release Checklist

This checklist tracks the remaining work before Attenly should be treated as a
public open-source release instead of an open-source preparation branch.

## Completed Locally

- Docker Compose golden path exists in `compose.yml`.
- Source-build override exists in `compose.build.yml`.
- The default `.env.example` targets local auth, SQLite, filesystem storage,
  OpenAI-compatible models, and no email connector.
- Frontend and backend containers run together behind one browser URL.
- Backend is not published directly to the host by the default Compose file.
- Runtime frontend config no longer exposes `VITE_LOCAL_AUTH_TOKEN`.
- Backend readiness validates database, filesystem storage, and configuration.
- Docker volume persistence has been verified locally with the `attenly-test`
  project.
- A self-hosting guide exists for the Docker pilot, model gateway settings,
  Microsoft Graph connector settings, local auth, and Docker volume behavior.
- The repository license is `AGPL-3.0-only`.
- Docker architecture, connector, model gateway, and troubleshooting docs exist.
- CI includes a source-build Compose health smoke test with a non-secret
  self-hosted Docker env.
- Backend source builds can skip DocTR model pre-cache for faster health-only CI.
- Backend image-size tradeoffs are documented.
- A self-hosted env preflight script catches common setup mistakes before
  Docker startup.
- A self-hosted env initialization script generates `.env` with a local auth
  token and required model settings.
- The env initialization script can also generate Microsoft Graph or Resend
  email connector settings.
- GHCR `open-sourcing` images for backend and frontend were pulled and booted
  locally with Docker Compose.
- A disposable published-image stack reached healthy frontend and backend
  readiness locally.
- Docker volume persistence was verified locally with the published-image stack:
  SQLite data and filesystem storage survived container recreation without
  `docker compose down -v`.
- A reusable published-image Compose smoke script exists:
  `python scripts/smoke_self_hosted_compose.py`.

## Release Blockers

- Confirm GitHub workflows pass for the pushed `open-sourcing` branch.
- Test a clean published-image install from a fresh clone or clean machine on a
  free frontend port:

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model
docker compose up -d --wait
```

- Validate the clean install's real business flow with an actual model endpoint:
  - open `http://localhost:5173`
  - authenticate with `LOCAL_AUTH_TOKEN`
  - upload documents
  - generate a report through the configured model endpoint
- Test the Microsoft Graph connector path with real Entra credentials if the
  first public pilot should include Microsoft 365 email.

## Documentation Before Public Announcement

- Replace temporary `open-sourcing` image tag guidance with the first immutable
  release tag.
- Review and tighten the operator docs after the first clean published-image
  install.

## Engineering Follow-Up

- Revisit backend image variants after the first clean published-image install.
- Harden provider interfaces for auth, model, storage, email, and template
  ingest customization.
- Implement full browser OIDC redirect login for enterprise deployments.
