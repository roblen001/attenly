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
- Existing model configurations can enable Graph without being replaced, and a
  live preflight can verify the Entra token, mailbox read query, attachments,
  and optional outbound send before Docker is recreated.
- The env initialization script can generate Gemini-backed report generation,
  embeddings, and smart template-ingest settings.
- GHCR `open-sourcing` images for backend and frontend were pulled and booted
  locally with Docker Compose.
- A disposable published-image stack reached healthy frontend and backend
  readiness locally.
- Docker volume persistence was verified locally with the published-image stack:
  SQLite data and filesystem storage survived container recreation without
  `docker compose down -v`.
- A reusable published-image Compose smoke script exists:
  `python scripts/smoke_self_hosted_compose.py`.
- The default Compose shape now separates interactive web traffic from inbound
  email/report generation with a dedicated `email-worker` service.
- Microsoft Graph was validated locally with a real test tenant: Entra token,
  `Mail.Read`, `Mail.Send`, sender verification, alias delivery, inbound
  report generation, saved report link, and report-ready email.
- Saved-report pages no longer block on reference PDF preloading before the
  report body renders.
- Local-auth Microsoft Graph settings advertise `GRAPH_MAILBOX` as the report
  intake address, so a single-workspace deployment does not require a generated
  Microsoft 365 alias.
- The source-build override builds the shared backend/worker image once, and a
  disposable three-service source install passed health and writable-volume
  checks after that packaging fix.

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
- Regression test the separated worker path:
  - open an existing saved report while the worker is processing
  - confirm the saved report opens quickly; two close attachment-bearing emails
    have already been observed completing successfully in sequence

## Documentation Before Public Announcement

- Replace temporary `open-sourcing` image tag guidance with the first immutable
  release tag.
- Review and tighten the operator docs after the first clean published-image
  install.
- Confirm `security@attenly.ca` receives vulnerability reports before linking
  the security policy from a public release.

## Engineering Follow-Up

- Revisit backend image variants after the first clean published-image install.
- Harden provider interfaces for auth, model, storage, email, and template
  ingest customization.
- Implement full browser OIDC redirect login for enterprise deployments.
