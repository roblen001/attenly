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
and [adding a mailbox alias](https://learn.microsoft.com/microsoft-365/admin/email/add-another-email-alias-for-a-user).

### Add Graph to an existing local-model `.env`

If your local Ollama models already work, preserve those settings and only add
the Graph connector:

```bash
python scripts/configure_microsoft_graph_env.py .env --graph-tenant-id YOUR_TENANT_ID --graph-client-id YOUR_CLIENT_ID --graph-mailbox attenly@YOUR_TENANT.onmicrosoft.com
```

The command prompts for the client secret without showing it or placing it in
shell history. It preserves the current auth and model values, generates an
internal cron secret when needed, and defaults generated Attenly aliases to the
mailbox's domain.

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
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model --email-provider microsoft_graph --graph-tenant-id replace-with-tenant-id --graph-client-id replace-with-client-id --graph-client-secret replace-with-client-secret --graph-mailbox attenly@company.com
```

This generates `LOCAL_AUTH_TOKEN` and `INTERNAL_CRON_SECRET`. Use
`--outbound-email-provider` and `--inbound-email-provider` instead of
`--email-provider` when you only want one direction enabled. Replace the
`replace-with-*` values before running the command.

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
```

The Graph app needs application mail permissions for the configured mailbox.
For inbound polling, call:

```text
POST /internal/process-email-jobs
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

This polls Graph, stores valid attachments through the configured storage
provider, creates email jobs, and processes pending jobs.

To poll without processing queued jobs:

```text
POST /internal/poll-inbound-email
Header: X-Cron-Secret: <INTERNAL_CRON_SECRET>
```

Keep internal routes behind network controls. `INTERNAL_CRON_SECRET` is not a
substitute for public internet exposure controls.

### Route the generated Attenly address to the Graph mailbox

After Docker starts, open **Settings > Email Ingest** and enable email ingest.
Attenly displays an address such as:

```text
u_abc123@example.onmicrosoft.com
```

Microsoft 365 must deliver that exact address to `GRAPH_MAILBOX`. For a
one-user test:

1. Copy the generated address from Attenly.
2. In Microsoft 365 admin center, open **Users > Active users** and select the
   Graph mailbox.
3. Open **Manage username and email**, add the generated address as an alias,
   and save.
4. Allow time for the alias to propagate before sending the test attachment.

For a multi-user production deployment, configure the company's mail routing so
every generated address at `EMAIL_INGEST_DOMAIN` reaches the polled mailbox
while preserving the original recipient address. Creating aliases manually is
only appropriate for this small test.

### End-to-end connector test

1. Recreate the backend so it loads the updated `.env`:

   ```bash
   docker compose pull backend
   docker compose up -d --force-recreate backend
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
6. Add Attenly's generated address as an alias on `GRAPH_MAILBOX`, as described
   above.
7. Send a new email from the verified sender to the generated address. Include
   one small PDF and put the report instruction in the message body.
8. Trigger one poll-and-process cycle:

   ```bash
   python scripts/trigger_microsoft_graph_poll.py .env
   ```

9. Confirm the returned Graph summary shows one accepted message and the job
   summary shows one successful job. Confirm the report appears in Attenly and
   the sender receives the report-ready email.

The production deployment needs a scheduler to call the process route every
one or two minutes. A manual trigger is sufficient for this acceptance test.

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
python scripts/init_self_hosted_env.py --llm-model replace-with-chat-model --embedding-model replace-with-embedding-model --email-provider resend --resend-api-key replace-with-resend-key --resend-webhook-secret replace-with-webhook-secret
```

## Current Connector Gaps

- No in-app Microsoft setup wizard.
- No automatic Entra app registration.
- No full browser Microsoft sign-in flow yet.
- Connector credentials are environment-managed, not UI-managed.
- Production deployments should place internal cron routes behind a private
  network, VPN, gateway, or scheduler with restricted access.
