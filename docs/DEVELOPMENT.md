# Development guide

Everything you need to run, change and verify jazz-life locally. Design rationale lives in the ADRs ([README.md](./README.md)); this document is the practical side.

## 1. Layout

```
jazz-life/
├── .devcontainer/           dev container / Codespaces definition (workspace image + docker-in-docker)
├── .github/workflows/       backend.yml (ruff · mypy · pytest unit/integration · openapi freshness)
│                            frontend.yml (typecheck · orval regeneration freshness)
├── docs/                    requirements, ADRs, this guide, media/
└── app/                     everything that runs; docker compose working directory
    ├── docker-compose.yml           db / backend / frontend
    ├── docker-compose.override.yml  dev overrides (bind mounts, --reload, Vite HMR)
    ├── .env.example                 all environment variables with comments
    ├── Makefile                     stack-level targets: db · up · down · logs · spec · gen · migrate · deploy-*
    ├── db/init/                     Postgres initdb script (creates jazz_test)
    ├── backend/
    │   ├── Makefile                 dev · run · check · test · lint · fmt · typecheck · migrate …
    │   ├── pyproject.toml, uv.lock  managed with uv
    │   ├── openapi.json             OpenAPI spec owned by the backend; regenerate with `make spec`; committed
    │   ├── migrations/              Alembic (file names YYYYMMDD_HHMM_<slug>)
    │   ├── entrypoint.sh            `alembic upgrade head` then exec the server
    │   └── app/
    │       ├── main.py              FastAPI app, CORS, routers, lifespan seed
    │       ├── server.py            dual-stack (IPv4 + IPv6) launcher used in production images
    │       ├── routers/             thin HTTP layer; DomainError → HTTPException in _handlers.py
    │       ├── services/            domain rules (id assignment, partial update, pins, auto-follow, sync)
    │       ├── core/                settings, db, exceptions, repositories/ (DB access)
    │       ├── schemas/             Pydantic DTOs (what the OpenAPI spec is generated from)
    │       └── models/              SQLModel tables
    └── frontend/
        ├── Makefile                 dev · dev-mobile · typecheck · gen
        ├── orval.config.ts          input ../backend/openapi.json → output src/api/generated/
        ├── vercel.json              mock-mode demo build
        └── src/
            ├── api/client.ts        the ONLY module that decides mock vs. real API (VITE_USE_MOCK)
            ├── api/generated/       orval output (types + react-query hooks); committed, never edited by hand
            ├── api/mocks/           demo fixtures; shape must match the real API responses
            ├── types/api.ts         re-exports generated types (+ a few hand-written ones for unimplemented areas)
            ├── pages/               HomePage · DiggingPage · ArtistsPage · LoginPage
            └── components/          records/ · feed/ · artists/ · tour/ · layout/
```

Dependency direction in the backend is strictly one-way: `routers → services → core/repositories`. Routers never contain business logic; services never import FastAPI.

## 2. Prerequisites

- Docker (Desktop or Engine) with Compose v2.
- For host-side tooling and IDE support: [uv](https://docs.astral.sh/uv/) + Python 3.11, Node.js 20+.
- A Spotify app (only for the real sign-in flow; the demo mode needs nothing): create one at <https://developer.spotify.com/dashboard>, add `http://127.0.0.1:8000/api/auth/callback` under *Redirect URIs*, and add your own Spotify account under *Users and Access* (apps in Development Mode only authenticate allow-listed users).
- Optional: an [AudD](https://dashboard.audd.io/) API token for the Listen tab. Without it `POST /api/recognize` returns 503 and the rest of the app works normally.

## 3. Setup paths

### 3a. Dev container / GitHub Codespaces

`.devcontainer/devcontainer.json` builds a workspace image (Python 3.11 + Node 20 + uv + make) with docker-in-docker, forwards ports 8000 / 5173 / 5432, sets the public defaults as `containerEnv`, and declares the secrets it expects: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `JWT_SECRET`, `REFRESH_TOKEN_KEY`, `AUDD_API_TOKEN`.

1. In Codespaces, register those names as [user secrets](https://github.com/settings/codespaces) and grant the repository access (locally, export them in your shell before opening the container).
2. Open the container. `postStartCommand` starts only the database (`docker compose up -d db`).
3. Start the two services in separate terminals: `cd app/backend && make dev` and `cd app/frontend && make dev`.

### 3b. Plain Docker

```bash
cp app/.env.example app/.env       # fill in the Spotify + JWT/Fernet values
cd app
make db                            # Postgres only
cd backend && make dev             # backend in the foreground with --reload (terminal 1)
cd frontend && make dev            # Vite dev server with HMR (terminal 2)
# or, everything detached:
cd app && make up
```

Endpoints: <http://127.0.0.1:8000/healthz>, <http://127.0.0.1:8000/docs> (Swagger UI, while `EXPOSE_OPENAPI_DOCS=true`), <http://127.0.0.1:5173>.

**Open the frontend via `127.0.0.1`, not `localhost`.** Spotify no longer accepts `http://localhost` redirect URIs, so the callback is registered on `127.0.0.1:8000`; the session cookie set by the callback is only sent back if the frontend is served from the same host name.

### 3c. Demo / mock mode

```bash
cd app/frontend && npm ci && VITE_USE_MOCK=true npm run dev
```

`VITE_USE_MOCK=true` makes `src/api/client.ts` serve everything from an in-memory store seeded by `src/api/mocks/*.json`; the login page shows *Enter demo* instead of the Spotify button. The mock reproduces the backend's rules (pin limit → 409, auto-pin, lenient PUT, sort order, background sync acknowledgement) so UI work can happen without the backend. Refreshing the page resets the data. `app/frontend/vercel.json` builds exactly this mode for the hosted demo.

## 4. Environment variables

All variables, with defaults and generation commands, are documented in [`app/.env.example`](../app/.env.example). Summary:

| Variable | Purpose |
|---|---|
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Spotify app credentials |
| `SPOTIFY_REDIRECT_URI` | must match the dashboard entry exactly; local default `http://127.0.0.1:8000/api/auth/callback` |
| `JWT_SECRET` | session JWT signing key, 32+ characters |
| `REFRESH_TOKEN_KEY` | Fernet key; Spotify refresh tokens are encrypted with it before being stored |
| `AUDD_API_TOKEN` | optional; audio recognition |
| `DATABASE_URL`, `TEST_DATABASE_URL` | `postgresql+psycopg://…`; `postgres://` is normalized automatically |
| `FRONTEND_BASE_URL` | where the OAuth callback redirects |
| `CORS_ALLOW_ORIGINS` | CSV of allowed origins |
| `COOKIE_SECURE`, `COOKIE_SAMESITE` | `false`/`lax` locally; `true`/`none` for a cross-origin deployment (validated at startup) |
| `EXPOSE_OPENAPI_DOCS` | `true` locally and in CI; `false` in production |
| `VITE_API_BASE`, `VITE_USE_MOCK`, `VITE_ALLOWED_HOSTS` | frontend; baked in at build time |

Settings are validated on startup (`app/backend/app/core/settings.py`): a short `JWT_SECRET`, an invalid Fernet key, or `COOKIE_SAMESITE=none` without `COOKIE_SECURE=true` fail fast instead of at the first OAuth callback.

## 5. Command cheat sheet

Stack (`cd app`):

| Command | What it does |
|---|---|
| `make db` | start Postgres only |
| `make up` / `make down` / `make logs` / `make ps` | whole stack, detached |
| `make spec` | import the FastAPI app and write `backend/openapi.json` (no server or DB needed) |
| `make gen` | run orval: `backend/openapi.json` → `frontend/src/api/generated/` |
| `make migrate name="…"` | Alembic autogenerate + upgrade inside the backend container |

Backend (`cd app/backend`, host `uv`):

| Command | What it does |
|---|---|
| `make dev` | backend container in the foreground with `--reload` |
| `make run` | uvicorn directly on the host |
| `make sync-dev` | `uv sync` with dev dependencies (also needed for IDE completion) |
| `make check` | `ruff check` + `mypy app` + `pytest` (note: **not** `ruff format --check`; run `make fmt` first) |
| `make test` / `make lint` / `make fmt` / `make typecheck` | individual steps |
| `make migration MSG="…"` / `make migrate` / `make migrate-down` | Alembic |
| `make shell` / `make logs` / `make db-shell` | container access |
| `make dev-mobile` | Codespaces only: rebind to the public forwarded URLs to test on a phone |

Frontend (`cd app/frontend`):

| Command | What it does |
|---|---|
| `make dev` | frontend container in the foreground (HMR) |
| `npm run dev` / `npm run build` / `npm run preview` | Vite on the host |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run gen` | orval |

## 6. The API contract rule

The backend owns the contract. Whenever a router, schema or docstring changes:

```bash
cd app && make spec && make gen
cd frontend && npm run typecheck
```

and commit `app/backend/openapi.json` **and** `app/frontend/src/api/generated/` together with the change. CI enforces both: `backend.yml` regenerates the spec and diffs it against the committed file; `frontend.yml` reruns orval and fails if `src/api/generated/` changes. `make spec` formats with Python's `json.dumps(indent=2)` rather than `jq` because `jq` 1.6 and 1.7 print floats differently (`5.0` vs `5`), which produced byte-level mismatches between local and CI.

Docstrings on routers and schemas are part of the public spec (they become OpenAPI `description`s), so keep them accurate and in English.

## 7. Tests

- `tests/unit/` — service-level tests with fakes; no database. `uv run pytest tests/unit`
- `tests/integration/` — FastAPI `TestClient` against a real Postgres. Needs `TEST_DATABASE_URL` (default in compose: `postgresql+psycopg://jazz:jazz@db:5432/jazz_test`; from the host use `localhost`) and a running `db` (`cd app && make db`). `uv run pytest tests/integration`
- CI runs both suites as a matrix, plus `ruff format --check`, `ruff check` and `mypy app`.
- Frontend: `npm run typecheck` (there are no unit tests; the mock mode and the tour double as a manual smoke test).

Before opening a PR: `cd app/backend && uv run ruff format . && make check`, then `cd app/frontend && npm run typecheck`.

## 8. Conventions

- All frontend API calls go through `src/api/client.ts`; components never call `fetch` or the generated fetchers directly. Keep the mock branch working whenever you add a call, and keep `src/api/mocks/*.json` shaped like the real responses (UUID string ids, `source`, `purchase_currency`, …).
- Never add `src/api/generated/` or `openapi.json` to `.gitignore` (ADR-002 §2.7).
- Backend models import from `sqlmodel` only (no direct `from sqlalchemy import …` in `models/`).
- Let Alembic name migration files (`alembic.ini` `file_template`); write migrations by hand only when data has to be discarded or moved (see ADR-006 §3.3).
- Tailwind v4 is configured through the `@tailwindcss/vite` plugin — there is no `tailwind.config` or `postcss.config`, and there should not be one.
- Keep backend and frontend changes in separate PRs unless a feature is only meaningful as one unit; say so in the PR description and include the regenerated spec and client.
- Do not bypass hooks (`--no-verify`).
- Secrets never go into the repository: use `app/.env` (git-ignored) or Codespaces secrets.

## 9. Deployment notes

The same code runs everywhere; only env values differ ([ADR-005](./005-railway-deploy-prep.md)). Current production layout is Railway (backend service, nginx-served frontend service, managed Postgres); [ADR-018](./018-cost-minimization-service-distribution.md) proposes moving to free tiers.

### Railway

- Each service's `rootDirectory` (`app/backend`, `app/frontend`) is set in the Railway dashboard; `railway.toml` in each directory pins the Dockerfile builder and limits auto-deploys to that directory. `cd app && make deploy` (or `deploy-backend` / `deploy-frontend`) pushes with the Railway CLI; deploy the backend first when its URL changes because `VITE_API_BASE` is baked into the frontend build.
- The frontend image (`target: prod`) serves `dist/` with nginx and proxies `/api/` to the backend over Railway's private network so that cookies stay same-origin; nginx re-resolves the backend host on every request (`resolver … valid=10s`) because the private IP changes on redeploy. The backend image starts through `app/server.py`, which binds a dual-stack socket (Railway's edge is IPv4, its private network IPv6).
- **Replicas must stay at 1**: OAuth state is held in process memory.
- Set `EXPOSE_OPENAPI_DOCS=false` in production.
- Env checklist for the backend service:

  ```
  SPOTIFY_CLIENT_ID
  SPOTIFY_CLIENT_SECRET
  JWT_SECRET                (32+ chars)
  REFRESH_TOKEN_KEY         (Fernet key)
  DATABASE_URL              (injected by the Postgres plugin; postgres:// is accepted)
  SPOTIFY_REDIRECT_URI      https://<backend-domain>/api/auth/callback  — register the exact string in the Spotify dashboard
  FRONTEND_BASE_URL         https://<frontend-domain>
  CORS_ALLOW_ORIGINS        https://<frontend-domain>
  COOKIE_SECURE=true
  COOKIE_SAMESITE=none      (only when frontend and backend are on different origins)
  EXPOSE_OPENAPI_DOCS=false
  AUDD_API_TOKEN            (optional)
  ```

  and for the frontend service (build-time): `VITE_API_BASE=https://<backend-domain>`, `VITE_USE_MOCK=false`, plus `BACKEND_INTERNAL_HOST` / `BACKEND_INTERNAL_PORT` for the nginx proxy.

- Invite control is the Spotify dashboard's *Users and Access* list; the app has no allow-list of its own (ADR-005 §2.8).

### Demo on Vercel

`app/frontend/vercel.json` sets `VITE_USE_MOCK=true` at build time and rewrites every path to `index.html`. Point a Vercel project at `app/frontend` and it needs no other configuration.

## 10. Adding a feature end to end

1. Write or update the ADR if the change is a decision (schema, API shape, product behaviour).
2. Backend: model → migration → repository → service (raise `DomainError`s) → schema → router → tests (unit for rules, integration for HTTP).
3. `cd app && make spec && make gen`.
4. Frontend: extend `client.ts` (real + mock branches) → components/pages → `npm run typecheck`.
5. Run the checks in §7 and commit spec + generated client with the change.
