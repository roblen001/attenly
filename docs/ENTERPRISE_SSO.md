# Enterprise SSO

Attenly supports generic OpenID Connect browser login, with Microsoft Entra as
the first documented target. Authentication uses Authorization Code + PKCE
through the backend-for-frontend (BFF): provider tokens remain on the server,
and the browser receives only an opaque `HttpOnly` Attenly session cookie.

## Resulting access model

- One self-hosted deployment maps to one Attenly organization and one Entra
  tenant.
- A verified user is JIT-provisioned on first login. The durable identity is
  generic issuer + subject, with Entra tenant (`tid`) + object (`oid`) stored as
  the canonical Entra cross-check. Email and display name are not identity keys.
- `Attenly.User` and `Attenly.Admin` app roles authorize login. Admin takes
  precedence if both are assigned.
- Files, uploads, saved reports, usage, and email settings are private to the
  signed-in user.
- Custom agents are visible and runnable by active organization members. The
  creator or an organization admin can edit/delete an agent.
- A local block overrides the identity provider and revokes all of that user's
  active Attenly sessions immediately.

### User and admin permissions

These are Attenly application roles. Entra defines and assigns the role values,
includes them in the verified ID token, and Attenly enforces the corresponding
permissions.

| Capability | `Attenly.User` | `Attenly.Admin` |
| --- | :---: | :---: |
| Sign in and use Attenly | Yes | Yes |
| Create custom agents | Yes | Yes |
| Discover and run organization-shared agents | Yes | Yes |
| Edit or delete an agent they created | Yes | Yes |
| Edit or delete another member's agent | No | Yes |
| Open **Settings > Users** and list organization users | No | Yes |
| Block or unblock another user | No | Yes |
| View or export system-wide performance metrics | No | Yes |
| Access their own private files, uploads, reports, usage, and email settings | Yes | Yes |
| Access another user's private files, uploads, reports, usage, or email settings | No | No |

Assigning `Attenly.Admin` by itself is sufficient for login; an administrator
does not also need `Attenly.User`. If both are assigned, admin takes precedence.
An Entra directory role such as Global Administrator does not grant Attenly
administrator access—the user or group must be assigned the `Attenly.Admin`
application role for this enterprise application.

Document/report sharing, SAML, SCIM, Graph group synchronization, and local
passwords are not part of this implementation.

## 1. Create the Microsoft Entra application

Use a dedicated app registration for Attenly SSO. In the
[Microsoft Entra admin center](https://entra.microsoft.com):

1. Open **Entra ID > App registrations > All applications**. Select an existing
   Attenly SSO registration, or select **New registration** and choose
   **Accounts in this organizational directory only** (single tenant).
2. On **Overview**, copy the following fields:

   | Entra field | Attenly setting |
   | --- | --- |
   | **Directory (tenant) ID** | `OIDC_TENANT_ID` |
   | **Application (client) ID** | `OIDC_CLIENT_ID` |

   Do not use the app registration's **Object ID** for either setting.
3. Open **Manage > Authentication > Add a platform > Web** and add a redirect
   URI matching the public Attenly URL exactly:

   ```text
   https://attenly.company.internal/api/auth/oidc/callback
   ```

   Select **Web**, not **Single-page application**.
4. Open **Manage > Certificates & secrets > Client secrets**, select **New
   client secret**, and copy the secret's **Value** immediately. Use that value
   for `OIDC_CLIENT_SECRET`; the **Secret ID** is not a credential. Never put
   the value in a `VITE_` variable or commit it to Git.
5. Open **Manage > App roles > Create app role** and define two roles whose
   **Value** fields are exactly:

   - `Attenly.User`
   - `Attenly.Admin`

   Allow users/groups as the member type. Names and descriptions can follow
   your internal convention; Attenly evaluates the role values.
6. Open the corresponding service principal by selecting **Managed application
   in local directory** from the app-registration Overview page. Alternatively,
   open **Entra ID > Enterprise applications > All applications** and select
   the entry with the same **Application ID**.
7. In the Enterprise Application, open **Manage > Properties**, set
   **Assignment required?** to **Yes**, and save.
8. Open **Manage > Users and groups > Add user/group**. Select each permitted
   user or group, select either **Attenly User** or **Attenly Admin**, and assign
   it.

**App registrations** is where redirect URIs, client secrets, client IDs, and
app-role definitions are managed. **Enterprise applications** is where access
requirements and user/group assignments are managed. They are two views of the
same application, but they expose different settings.

Attenly also requires a valid app-role claim, so an unassigned tenant/global
administrator cannot bypass assignment merely because of their directory role.
No Microsoft Graph API permissions are required for login.

Use a separate Entra app registration for Microsoft Graph email integration.
The Graph connector uses application permissions such as `Mail.Read` and
`Mail.Send`, while SSO does not need them. Keeping the registrations separate
reduces privilege and allows their credentials and lifecycles to be managed
independently. If reusing an older Graph test registration temporarily, review
its **API permissions** and remove anything the combined deployment does not
need.

## 2. Configure Attenly

Copy `.env.enterprise.example` to `.env`, then replace every placeholder:

```dotenv
ENV=production
APP_PROFILE=enterprise
APP_URL=https://attenly.company.internal
CORS_ORIGINS=https://attenly.company.internal

AUTH_PROVIDER=oidc
OIDC_TENANT_ID=replace-with-your-entra-tenant-id
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/replace-with-your-entra-tenant-id/v2.0/.well-known/openid-configuration
OIDC_EXPECTED_ISSUER=https://login.microsoftonline.com/replace-with-your-entra-tenant-id/v2.0
OIDC_CLIENT_ID=replace-with-your-attenly-app-client-id
OIDC_CLIENT_SECRET=replace-with-your-entra-client-secret
OIDC_CLIENT_AUTH_METHOD=client_secret_post
OIDC_CALLBACK_URL=https://attenly.company.internal/api/auth/oidc/callback
OIDC_ALLOWED_ORIGINS=https://attenly.company.internal
OIDC_SCOPES=openid profile email
OIDC_ALLOWED_ID_TOKEN_ALGORITHMS=RS256
OIDC_ROLES_CLAIM=roles
OIDC_USER_ROLE=Attenly.User
OIDC_ADMIN_ROLE=Attenly.Admin
OIDC_ORGANIZATION_SLUG=company
OIDC_ORGANIZATION_NAME=Company
OIDC_SESSION_TTL_HOURS=12
OIDC_LOGIN_TTL_SECONDS=600
OIDC_COOKIE_SECURE=true
OIDC_SESSION_COOKIE_NAME=__Host-attenly_session
OIDC_LOGIN_COOKIE_NAME=__Host-attenly_oidc_flow

DATABASE_PROVIDER=sqlalchemy
DATABASE_URL=sqlite:////data/attenly.db
DATABASE_AUTO_CREATE_TABLES=true
STORAGE_PROVIDER=filesystem
STORAGE_PATH=/data/storage
```

For local HTTP development only, set `OIDC_ALLOW_INSECURE_HTTP=true` and
`OIDC_COOKIE_SECURE=false`. Use `http://localhost:5173` for `APP_URL` and
`OIDC_ALLOWED_ORIGINS`, and register this exact development callback:

```dotenv
OIDC_CALLBACK_URL=http://localhost:5173/api/auth/oidc/callback
OIDC_SESSION_COOKIE_NAME=attenly_session
OIDC_LOGIN_COOKIE_NAME=attenly_oidc_flow
```

For an existing local Docker env file, the helper below preserves its model,
email, database, and storage settings while configuring all local OIDC values.
It prompts for the secret without displaying it and validates the result:

```powershell
python scripts/configure_oidc_env.py .env.docker-test
```

Enter these values when prompted:

| Prompt | Value from Entra |
| --- | --- |
| Directory (tenant) ID | **Overview > Directory (tenant) ID** |
| Application (client) ID | **Overview > Application (client) ID** |
| Client secret Value | **Certificates & secrets > Client secrets > Value** |

Do not enter the Object ID or Secret ID. Do not paste the client secret into
chat, screenshots, shell history, or a browser-side `VITE_` setting.

To prepare the file for manual editing instead, run:

```powershell
python scripts/configure_oidc_env.py .env.docker-test --prepare
```

Only the three `PASTE_ENTRA_*` values then need to be replaced. The file is
already ignored by Git.

Validate, build, and start the local source deployment with the same env file:

```powershell
python scripts/check_self_hosted_env.py .env.docker-test
docker compose --env-file .env.docker-test -f compose.yml -f compose.build.yml up -d --build --force-recreate --wait
```

Open <http://localhost:5173>. When source or environment settings change, rerun
the Docker command so the containers receive the new configuration and code.

Production validation rejects an insecure cookie. The bundled Vite development
server proxies `/api` to the backend on `http://127.0.0.1:8000` and strips the
public `/api` prefix, matching the production Nginx route layout.

Compose already passes `AUTH_PROVIDER` to the frontend. The browser needs no
OIDC client ID, client secret, or Microsoft token. With source development
outside Compose, set `VITE_AUTH_PROVIDER=oidc` and `VITE_API_BASE_URL=/api`.

The standard Compose commands below expect the configuration at `.env`. If you
keep it under another name, set `ATTENLY_ENV_FILE` inside that file to the same
path and pass it to Compose for interpolation as well. For example, a file named
`.env.enterprise` should contain `ATTENLY_ENV_FILE=.env.enterprise` and be run
with `docker compose --env-file .env.enterprise up -d --wait`. This prevents the
frontend and backend from loading different authentication providers.

Run the preflight before starting:

```bash
python scripts/check_self_hosted_env.py .env
docker compose up -d --wait
```

## 3. Validate login and isolation

Test with two assigned users:

1. Sign in as user A and upload a harmless test document.
2. Sign in as user B in another browser profile. User B must not see A's file,
   saved report, usage, or email settings.
3. Have user A create an agent. User B should see and run it but should not be
   able to edit/delete it.
4. Sign in as an `Attenly.Admin`. The admin should be able to manage the shared
   agent and open **Settings > Users**.
5. Block user B. Their next request must fail immediately, including from an
   already-open browser tab. Unblocking permits a new login but does not restore
   a revoked old session.

## Operations and lifecycle

- Keep the backend port private behind the bundled frontend proxy. The image
  accepts forwarded client headers only from loopback and RFC1918 proxy peers;
  adjust that allowlist for a different trusted container/network range rather
  than trusting every source. If a load balancer sits in front of Nginx,
  configure Nginx real-IP handling for that load balancer's exact CIDRs so
  login throttles and audit IPs do not collapse to the load balancer address.
  Continue overwriting, rather than appending, public client-supplied forwarding
  headers at the final trusted proxy hop.
- Removing an Entra assignment or app role prevents the next SSO login. Use the
  Attenly local block for immediate revocation of an existing Attenly session.
- Role promotion/demotion is synchronized from the verified app-role claim on
  the next login. A local block is never cleared by JIT login.
- Only hashes of opaque Attenly session tokens are stored. Login state is
  short-lived, one-time, and server-side. Provider access/ID tokens are not
  persisted.
- Back up `/data/attenly.db` and `/data/storage` together. Existing SQLite
  databases are upgraded idempotently with the nullable organization/creator
  agent columns while preserving legacy agents. Fresh databases also receive
  the declared foreign keys.
- Changing an existing deployment from local or external authentication to
  OIDC does not automatically transfer legacy agent ownership to a newly
  provisioned OIDC user or organization. The rows remain in the database, but
  they are not shown to the new OIDC accounts until an operator performs an
  explicit, backed-up ownership migration.
- Existing PostgreSQL deployments require a versioned schema migration before
  enabling OIDC; the bundled compatibility upgrader is intentionally SQLite
  only.

For a different OIDC provider, use its tenant-specific discovery URL and map
`OIDC_ROLES_CLAIM`, `OIDC_USER_ROLE`, and `OIDC_ADMIN_ROLE` to its claims. Keep
issuer+subject stable, use an HTTPS callback, and validate the provider in a
staging deployment before production rollout.
