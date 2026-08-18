# Connector Guide

Connectors are optional. The base self-hosted Docker profile disables email
connectors so the app can start without third-party credentials.

## Disabled Email Mode

Default:

```bash
OUTBOUND_EMAIL_PROVIDER=none
INBOUND_EMAIL_PROVIDER=none
```

Use this for the first pilot unless email is part of the test. The backend will
not mount inbound webhook/job routes when inbound email is disabled.

## Microsoft Graph

Microsoft Graph support uses application credentials and a configured mailbox.
This is admin-configured, not a user OAuth setup wizard.

This connector does not add Microsoft login to Attenly. It lets the backend
read attachment-bearing messages from one Microsoft 365 mailbox and send
verification/report emails as that mailbox. Local token auth can remain enabled.

### Test tenant and mailbox

Graph is the API; there is no separate "Graph account." For a realistic test,
you need a Microsoft Entra tenant with an Exchange Online mailbox. Use one of:

- a [Microsoft 365 E5 developer sandbox](https://learn.microsoft.com/office/developer-program/microsoft-365-developer-program-get-started),
  if your Microsoft account qualifies
- a [Microsoft 365 Business trial](https://www.microsoft.com/microsoft-365/business/microsoft-365-business-standard-one-month-trial)
  with Exchange Online
- an isolated test tenant supplied by your organization

A personal Outlook.com mailbox or an Entra-only tenant is not enough for this
app-only mailbox test. The fastest sandbox choice is the instant developer
sandbox because it includes Outlook and pre-created test users. Microsoft only
offers E5 sandboxes to qualifying Developer Program members; if the dashboard
does not offer one, use the Business trial or an organizational test tenant.

Required Entra/Azure setup:

- create a single-tenant app registration; no redirect URI is needed
- record its **Directory (tenant) ID** and **Application (client) ID**
- create a client secret and copy its **Value**, not its Secret ID
- under **API permissions**, add Microsoft Graph **Application permissions**:
  `Mail.Read` for inbound mail and `Mail.Send` for outbound mail
- grant tenant-wide admin consent
- create or choose an Exchange Online mailbox Attenly will poll and send as

Use a dedicated app registration for the Microsoft Graph email connector rather
than the Attenly browser-SSO registration. Graph email requires privileged
application permissions, while SSO needs no Microsoft Graph permissions.
Separate registrations keep credentials, permissions, rotation, and incident
response independent.

Do not select Delegated permissions. Attenly uses the OAuth client-credentials
flow, so no Microsoft user is signed in while the backend polls the mailbox.

The Entra permissions above are suitable for an isolated test tenant but are
tenant-wide. For production, replace them with equivalent Exchange Online
Application RBAC assignments scoped to the Attenly mailbox. Do not retain the
same unscoped Entra permission after granting it through Application RBAC:
Microsoft treats the two grants as additive, which would defeat the mailbox
scope.
See Microsoft's guides for
[app registration](https://learn.microsoft.com/entra/identity-platform/howto-create-service-principal-portal),
[mailbox-scoped Application RBAC](https://learn.microsoft.com/exchange/permissions-exo/application-rbac),
and [mailbox email addresses](https://learn.microsoft.com/exchange/recipients-in-exchange-online/manage-user-mailboxes/add-or-remove-email-addresses).

### Add Graph to an existing local-model `.env`

If your local Ollama models already work, preserve those settings and only add
the Graph connector:

```bash
python scripts/configure_microsoft_graph_env.py .env --graph-tenant-id YOUR_TENANT_ID --graph-client-id YOUR_CLIENT_ID --graph-mailbox attenly@YOUR_TENANT.onmicrosoft.com
```

The command prompts for the client secret without showing it or placing it in
shell history. It preserves the current auth and model values, generates an
internal cron secret when needed, and defaults Attenly's internal routing
addresses to the mailbox's domain.

Validate the credentials before recreating Docker:

```bash
python scripts/check_self_hosted_env.py .env
python scripts/check_microsoft_graph_connection.py .env
```

The live Graph check is read-only by default. To also send one real test email:

```bash
python scripts/check_microsoft_graph_connection.py .env --send-test-to you@example.com
```

It reports separate results for the Entra token, `Mail.Read`, mailbox access,
and `Mail.Send`.

Generate a Graph-ready `.env` for both outbound email and inbound mailbox
polling:

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model --email-provider microsoft_graph --graph-tenant-id replace-with-tenant-id --graph-client-id replace-with-client-id --graph-mailbox attenly@company.com
```

The initializer securely prompts for `GRAPH_CLIENT_SECRET` without echoing it,
then generates `LOCAL_AUTH_TOKEN` and `INTERNAL_CRON_SECRET`. Use
`--outbound-email-provider` and `--inbound-email-provider` instead of
`--email-provider` when you only want one direction enabled. Replace the
`replace-with-*` values before running the command. Passing secrets as command
arguments is supported for automation but can expose them in shell history and
process listings.

Equivalent outbound email settings:

```bash
OUTBOUND_EMAIL_PROVIDER=microsoft_graph
GRAPH_TENANT_ID=your-tenant-id
GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_MAILBOX=attenly@company.com
```

Equivalent inbound mailbox polling settings:

```bash
INBOUND_EMAIL_PROVIDER=microsoft_graph
GRAPH_TENANT_ID=your-tenant-id
GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_MAILBOX=attenly@company.com
INTERNAL_CRON_SECRET=generate-a-long-random-secret
GRAPH_POLL_BATCH_SIZE=10
GRAPH_POLL_LOOKBACK_SECONDS=300
EMAIL_JOB_EXECUTION_MODE=worker
EMAIL_WORKER_POLL_INTERVAL_SECONDS=30
EMAIL_WORKER_MAX_JOBS_PER_CYCLE=1
```

The Graph app needs application mail permissions for the configured mailbox.
In the Docker self-hosted profile, Compose starts an `email-worker` service
that polls the mailbox and processes accepted jobs automatically. The web
backend stays focused on interactive app requests.

Watch it with:

```bash
docker compose logs -f email-worker
```

To request an immediate poll manually, call:

```text
POST /internal/process-email-jobs
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

With `EMAIL_JOB_EXECUTION_MODE=worker`, the route returns after polling and the
worker handles queued jobs. Set `EMAIL_JOB_EXECUTION_MODE=inline` only for a
legacy single-process deployment where no worker service is running.

To poll without processing queued jobs:

```text
POST /internal/poll-inbound-email
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

Keep internal routes behind network controls. `INTERNAL_CRON_SECRET` is not a
substitute for public internet exposure controls.

### Use the configured Graph mailbox

After Docker starts, open **Settings > Email Ingest** and enable email ingest.
In the recommended `AUTH_PROVIDER=local` single-workspace deployment, Attenly
displays the configured `GRAPH_MAILBOX`, such as:

```text
attenly@example.onmicrosoft.com
```

Send attachment-bearing emails directly to that mailbox. No generated
Microsoft 365 alias is required for this deployment shape. The message remains
in the `GRAPH_MAILBOX` Inbox because Attenly polls that Inbox rather than
receiving a separate mailbox or webhook copy.

Use the address displayed as **Report Intake Mailbox**. If someone sends to an
internal `u_...` endpoint that has not been configured as an Exchange address,
Microsoft 365 returns an **Unknown To address** or **recipient not found**
delivery failure before Attenly can see the message. That bounce indicates a
Microsoft mail-routing problem, not an unhealthy Attenly container.

Exchange Online can expose an alias-delivered message through Graph with only
the mailbox's primary address in both `toRecipients` and the standard message
headers. In `AUTH_PROVIDER=local` mode, Attenly safely handles this Microsoft
normalization by routing mail delivered to `GRAPH_MAILBOX` to the configured
local workspace's internal email endpoint. The settings page therefore shows
the deliverable Graph mailbox instead of that internal endpoint. The
verified-sender check still applies.
Use a dedicated mailbox for Attenly so unrelated attachment-bearing mail from a
verified sender is not treated as an Attenly submission.

For a multi-user production deployment, configure the company's mail routing so
every generated address at `EMAIL_INGEST_DOMAIN` reaches the polled mailbox
while preserving the original recipient address. This is an administrator-level
mail-routing design, not a task for each business user. Do not depend on the
single-workspace fallback to distinguish multiple users because Graph may no
longer provide Attenly with an alias after Exchange normalizes it.

### End-to-end connector test

1. Recreate the backend so it loads the updated `.env`:

   ```bash
   docker compose pull
   docker compose up -d --force-recreate --wait
   ```

   If you are testing unpublished source changes, build the backend with
   `compose.build.yml` instead of pulling an older published image.

2. Confirm the app and model connection still work by opening a saved agent or
   processing a small uploaded document.
3. In **Settings > Email Ingest**, enable email ingest and choose a default
   agent.
4. Add the mailbox's primary address (or another address you control) as a
   verified sender.
5. Open the verification email and click its localhost verification link from
   the same computer running Attenly.
6. Send a new email from the verified sender directly to `GRAPH_MAILBOX`. Include
   one small PDF. The default agent selected in step 3 determines the report
   workflow; the sender does not need to include instructions in the message body.
7. Either wait for the next worker poll or trigger one immediate poll:

   ```bash
   python scripts/trigger_microsoft_graph_poll.py .env
   ```

   The default localhost URL may use HTTP. If you pass an external `--api-url`,
   it must use HTTPS so `INTERNAL_CRON_SECRET` is not sent in plaintext.

8. Watch `docker compose logs -f email-worker`. Confirm the Graph summary shows
   one accepted message and the worker logs show one successful job. Confirm
   the report appears in Attenly and the sender receives the report-ready
   email.

The production Docker deployment does not need an external scheduler for normal
Graph polling. A manual trigger is still useful for acceptance testing.

## Resend

Resend remains supported for the original hosted/default profile.

Outbound:

```bash
OUTBOUND_EMAIL_PROVIDER=resend
RESEND_API_KEY=your_resend_api_key
```

Inbound webhook:

```bash
INBOUND_EMAIL_PROVIDER=resend
RESEND_API_KEY=your_resend_api_key
RESEND_WEBHOOK_SECRET=your_resend_webhook_secret
```

Use Resend when you want a hosted email provider rather than Microsoft 365
mailbox polling.

You can also generate a Resend-enabled env file:

```bash
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model --email-provider resend
```

The initializer securely prompts for the Resend API key and webhook secret.

## Current Connector Gaps

- No in-app Microsoft setup wizard.
- No automatic Entra app registration.
- Browser SSO is configured separately through `AUTH_PROVIDER=oidc`; the Graph
  connector app itself does not sign users in.
- Connector credentials are environment-managed, not UI-managed.
- Production deployments should place internal cron routes behind a private
  network, VPN, gateway, or scheduler with restricted access.
