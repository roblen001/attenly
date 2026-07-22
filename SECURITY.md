# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to `security@attenly.ca` with
the subject `Attenly security report`. Include the affected version, impact,
reproduction steps, and a minimal proof of concept when possible.

Please do not publish the issue before a fix or coordinated disclosure date is
available, access data that is not yours, use social engineering, or run tests
that could disrupt another person’s deployment.

We will acknowledge reports as soon as reasonably possible and keep the
reporter informed while the issue is assessed. Response and remediation times
depend on severity and maintainer availability; this project does not promise a
fixed security-response SLA.

## Supported versions

Security fixes are made on the latest tagged `1.0.x` release. The
`open-sourcing` branch is a development branch and may change before a tag is
published. Older and untagged versions may need to upgrade before receiving a
fix.

## Current security model

- The default self-hosted profile uses one shared bearer token. It is suitable
  for a trusted internal workspace, not public multi-user account management.
- `external_jwt` validates configured issuer, audience, algorithm, and signing
  material. Full browser OIDC redirect login is not implemented.
- The Supabase profile uses Supabase authentication and row-level policies.
- The default Compose stack publishes only the frontend port; Nginx proxies API
  traffic to the private backend container.
- Backend and worker containers run as a non-root user. Secrets are supplied at
  runtime and excluded from Docker build contexts.
- Uploads have size, extension, MIME, and basic content checks. Attenly does not
  include a full antivirus engine; deploy malware scanning separately when
  required.
- HTML and CSS produced during template ingestion are sanitized before use.
- Browser and API responses include baseline clickjacking, MIME-sniffing,
  referrer, and content-security headers.
- Application rate limiting is process-local. Use a reverse proxy, firewall, or
  gateway for deployment-wide abuse controls.

## Operator responsibilities

- Terminate TLS at a trusted reverse proxy and restrict access to intended
  networks and users.
- Generate long random local, cron, webhook, and JWT secrets. Rotate any secret
  that may have been exposed.
- Keep `.env` out of source control and prefer a platform secret manager for
  production.
- Back up and protect the Docker volume. Encryption at rest depends on the host
  filesystem, database, and storage provider selected by the operator.
- Review the data-handling terms of every configured model and connector.
  Documents sent to a hosted provider leave the local deployment.
- Keep Attenly images, the host OS, Docker, model gateways, and reverse proxies
  patched.
- Use a dedicated Microsoft 365 mailbox and grant only the documented Graph
  permissions when enabling email ingestion.
- Place antivirus/content-disarm controls at the mail, gateway, or storage
  boundary if company policy requires them.

## Secret handling

- Never put server secrets in `VITE_` variables; frontend configuration is
  visible to browser users.
- Never include API keys in bug reports, screenshots, Compose output, or logs.
- `.env`, private keys, local databases, logs, and local assistant settings are
  ignored or excluded from container build contexts.
- If a secret was committed, deleting the line in a later commit is not enough:
  rotate the secret immediately and remove it from Git history when necessary.

## No compliance certification

Attenly is not certified as SOC 2, HIPAA, GDPR, or any other compliance regime.
Organizations are responsible for evaluating and configuring the complete
deployment—including identity, network, models, storage, backups, retention,
and monitoring—for their legal and regulatory obligations.

Last updated: July 2026.
