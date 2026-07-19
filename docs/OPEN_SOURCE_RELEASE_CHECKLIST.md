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

## Release Blockers

- Push `open-sourcing` and confirm GitHub workflows pass.
- Confirm GHCR publishes both backend and frontend images under the intended
  namespace.
- Test a clean published-image install from a fresh clone or clean machine:

```bash
cp .env.example .env
docker compose up -d --wait
```

- Validate the clean install can:
  - open `http://localhost:5173`
  - authenticate with `LOCAL_AUTH_TOKEN`
  - upload documents
  - generate a report through the configured model endpoint
  - restart without losing SQLite data or stored files

## Documentation Before Public Announcement

- Replace temporary `open-sourcing` image tag guidance with the first immutable
  release tag.
- Review and tighten the operator docs after the first clean published-image
  install.

## Engineering Follow-Up

- Reduce backend image size or document why OCR/model dependencies make the
  first image large.
- Harden provider interfaces for auth, model, storage, email, and template
  ingest customization.
- Implement full browser OIDC redirect login for enterprise deployments.
