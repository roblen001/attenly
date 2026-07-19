# Provider Matrix

This matrix describes the current open-source provider surface. It is intended
to help companies understand which parts are ready for a self-hosted pilot and
which parts are still adapter work.

## Supported Now

| Area | Provider | Env Setting | Notes |
| --- | --- | --- | --- |
| Auth | Local bearer token | `AUTH_PROVIDER=local` | Trusted internal pilot mode. Users enter the configured token in the browser. |
| Auth | External JWT | `AUTH_PROVIDER=external_jwt` | For an IdP, reverse proxy, or API gateway that already issues bearer tokens. Full browser OIDC redirect login is not implemented yet. |
| Database | SQLAlchemy + SQLite | `DATABASE_PROVIDER=sqlalchemy`, `DATABASE_URL=sqlite:////data/attenly.db` | Default Docker self-hosted path. Tables can be auto-created with `DATABASE_AUTO_CREATE_TABLES=true`. |
| Database | Supabase | `DATABASE_PROVIDER=supabase` | Original hosted/default stack. |
| Storage | Filesystem | `STORAGE_PROVIDER=filesystem`, `STORAGE_PATH=/data/storage` | Default Docker self-hosted path. Stored in the `attenly-data` Docker volume. |
| Storage | Supabase Storage | `STORAGE_PROVIDER=supabase` | Original hosted/default stack. |
| LLM | OpenAI-compatible chat | `LLM_PROVIDER=openai_compatible` | Sends prompts to a `/chat/completions` compatible endpoint. |
| LLM | Gemini | `LLM_PROVIDER=gemini` | Original smart extraction provider. |
| Embeddings | OpenAI-compatible embeddings | `EMBEDDING_PROVIDER=openai_compatible` | Sends vectors to an `/embeddings` compatible endpoint. |
| Embeddings | Gemini | `EMBEDDING_PROVIDER=gemini` | Supported by documented profiles. |
| Template ingest | Disabled | `TEMPLATE_INGEST_PROVIDER=disabled` | Recommended for the simplest Docker pilot. |
| Template ingest | Basic | `TEMPLATE_INGEST_PROVIDER=basic` | Simple DOCX/HTML conversion without AI layout reasoning. |
| Template ingest | Gemini | `TEMPLATE_INGEST_PROVIDER=gemini` | Current smart multimodal path. |
| Template ingest | OpenAI-compatible | `TEMPLATE_INGEST_PROVIDER=openai_compatible` | Requires a gateway/model endpoint that supports the needed multimodal request shape. |
| Outbound email | Disabled | `OUTBOUND_EMAIL_PROVIDER=none` | Default self-hosted pilot. |
| Outbound email | Resend | `OUTBOUND_EMAIL_PROVIDER=resend` | Original hosted/default stack. |
| Outbound email | Microsoft Graph | `OUTBOUND_EMAIL_PROVIDER=microsoft_graph` | Uses Microsoft Graph application credentials. |
| Inbound email | Disabled | `INBOUND_EMAIL_PROVIDER=none` | Default self-hosted pilot. |
| Inbound email | Resend | `INBOUND_EMAIL_PROVIDER=resend` | Original inbound webhook flow. |
| Inbound email | Microsoft Graph | `INBOUND_EMAIL_PROVIDER=microsoft_graph` | Polls a configured Microsoft 365 mailbox and creates email jobs. |
| Rich text editor | Self-hosted TinyMCE | `VITE_TINYMCE_MODE=self_hosted` | Default Docker frontend path. |
| Rich text editor | Tiny Cloud | `VITE_TINYMCE_MODE=cloud` | Existing hosted frontend option. |

## Recommended Pilot Profiles

| Goal | Starting File | Key Choices |
| --- | --- | --- |
| Fastest on-prem Docker pilot | `.env.example` | Local auth, SQLite, filesystem storage, OpenAI-compatible models, no email. |
| Local no-Supabase with Gemini | `.env.local.example` | Local auth, SQLAlchemy/SQLite, filesystem storage, Gemini, no email. |
| Company model gateway | `.env.enterprise.example` | SQLAlchemy/SQLite, filesystem storage, OpenAI-compatible chat and embeddings. |
| Existing hosted stack | `.env.default.example` | Supabase, Gemini, optional Resend. |

## Known Gaps

- Full browser OIDC redirect login is not implemented yet. Use
  `AUTH_PROVIDER=external_jwt` only when another component already issues the
  bearer token.
- The backend Docker image currently includes OCR/model dependencies and can be
  large. Future work should consider optional OCR image variants or lazy model
  download.
- Provider interfaces still need to be hardened so custom company logic can be
  added without touching deep application code.
- Published image tags should move from the temporary `open-sourcing` tag to
  immutable version tags before the first public release.
