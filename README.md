# Healthomatix

Healthomatix is a tenant-aware clinic workflow foundation with a FastAPI API,
Alembic migrations, and Next.js clinic and patient portals. It is a development
and synthetic-data demonstration, not a production clinical system and not a
claim of HIPAA compliance.

## Workspace

- `apps/web` — Next.js clinic and patient portals with server-managed OIDC sessions.
- `apps/mobile` — Expo patient shell with five primary navigation destinations.
- `packages/api-client` — OpenAPI specification, generated TypeScript types,
  and shared typed API client.
- `backend` — FastAPI, SQLAlchemy models, Alembic, and API tests.
- `docs` — architecture decisions, API contracts, security boundaries,
  wireframes, and phased backlog.

## Local development

Requirements: Python 3.11+, Node.js 22.13+, and npm. PostgreSQL is the intended
production database. The API defaults to a local SQLite development database.

1. Use `.env.example` as the environment-variable reference. Next.js reads
   `apps/web/.env.local`; the backend reads process environment variables and
   does not load `.env` files automatically. Keep `SCHEDULING_ENABLED=false`
   unless running an approved synthetic demo.
2. In PowerShell, create and activate the backend environment:

   ```powershell
   Set-Location backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[test]"
   $env:DATABASE_URL = "sqlite:///./healthomatix-dev.db"
   python -m alembic upgrade head
   python -m uvicorn app.main:app --reload
   ```

3. In another terminal, from the repository root:

   ```powershell
   Set-Location apps\web
   Copy-Item ..\..\.env.example .env.local
   Set-Location ..\..
   npm install
   npm run web:dev
   ```

Use `npm run mobile:typecheck` to check the Expo patient shell. Start it with
`npm --workspace @healthomatix/mobile run start`. The app is a preview and has
no sign-in flow. Its token-storage adapter uses Expo SecureStore and is not
connected to authentication.

Regenerate the mounted API contract and client types with
`npm run api:generate`; verify checked-in output is current with
`npm run api:check`. Run these commands after changing FastAPI routes or
schemas.

The API health endpoint is `http://localhost:8000/api/v1/health`; interactive
OpenAPI documentation is available at `http://localhost:8000/docs`. Run
backend tests with `Set-Location backend; python -m pytest tests -q` and web
type-check/build with `npm run web:lint` and `npm run web:build`. Apply
database migrations with `npm run backend:migrate`.

## Authentication and synthetic scheduling

API identity uses OIDC bearer tokens. Set `OIDC_ISSUER`, `OIDC_AUDIENCE`, and
`OIDC_JWKS_URL` to a trusted HTTPS provider; the API fails closed when these
values are missing. The web portals sign in with the OIDC authorization-code
flow plus PKCE. Register `{APP_BASE_URL}/auth/callback` with the identity
provider and set `OIDC_CLIENT_ID`, `APP_BASE_URL`, `SESSION_SECRET`, and
`HEALTHOMATIX_API_URL` in `apps/web/.env.local` (see `.env.example`).
Tokens stay in an encrypted HttpOnly cookie and never reach browser script.
This flow has not been verified against a production identity provider; use
synthetic accounts only.
Platform administration is separately allowlisted with semicolon-separated
`https-issuer|subject` pairs in `PLATFORM_ADMIN_IDENTITIES`; this does not grant
tenant membership or patient-record access. Support requests remain pending
and do not create an access grant.

For a local synthetic-only scheduling demonstration, start the API with
`SCHEDULING_ENABLED=true` after applying migrations. The API still requires
OIDC authentication and active tenant/provider/patient authorization. Automated
tests use synthetic fixtures and dependency overrides. Appointment notification
events remain in a pending outbox; there is no delivery integration.

Never put real patient information, credentials, tokens, or production secrets
in fixtures, screenshots, logs, or this repository. Review
[Authentication and PHI boundaries](./docs/auth-and-phi-boundaries.md) and the
[release gates](./docs/phase-1-backlog.md) before any deployment.
