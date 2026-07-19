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

Required Entra/Azure setup:

- create an app registration
- create a client secret
- grant Microsoft Graph application permissions
- grant tenant admin consent
- configure or choose the mailbox Attenly will use

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
