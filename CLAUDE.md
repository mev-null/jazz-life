# CLAUDE.md

Read by Claude Code at the start of every session. It condenses what an agent must know before touching this repository; the human-facing version of the same material is [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## What this is

jazz-life ("Analog Life") — a personal dashboard for a jazz record collection: a shelf of owned records, a hunt list, new releases from followed artists (Spotify), and a "listen" mode that identifies the record playing and adds it to the hunt list. FastAPI + SQLModel + PostgreSQL backend, React 19 + TypeScript frontend, API contract generated from the backend's OpenAPI spec.

Requirements and decisions live in [docs/](docs/README.md). The requirements document (000) and the Phase B decisions (002) partly overlap; **when they conflict, 002 wins**. Later ADRs state which earlier sections they supersede.

## Read first

1. [docs/README.md](docs/README.md) — index of the requirements document and all ADRs, with the recommended reading order.
2. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — layout, setup paths (dev container / plain Docker / mock mode), environment variables, command cheat sheet, deployment notes.
3. `app/Makefile`, `app/backend/Makefile`, `app/frontend/Makefile` — `make help` lists every target.

## Rules that are not negotiable

- **Layering (backend).** `routers → services → core/repositories`, one direction only. Routers convert HTTP; business rules (id assignment, partial update, pins, auto-follow, sync) live in services and raise `DomainError`; only `routers/_handlers.py` maps them to `HTTPException`.
- **The API contract.** The backend owns `app/backend/openapi.json`. After any change to a router, schema or their docstrings run `cd app && make spec && make gen` and commit the spec **and** `app/frontend/src/api/generated/` with the change. CI fails otherwise. Docstrings on routers and schemas become OpenAPI descriptions — keep them accurate and in English.
- **The mock switch.** Every frontend API call goes through `app/frontend/src/api/client.ts`; `VITE_USE_MOCK=true` must keep working (it is the public demo). Mock JSON in `src/api/mocks/` stays shaped like the real responses.
- Never add `src/api/generated/` or `openapi.json` to `.gitignore` (ADR-002 §2.7).
- Backend `models/` import from `sqlmodel` only; let Alembic name migration files.
- Tailwind v4 via `@tailwindcss/vite` — do not create `tailwind.config` / `postcss.config`.
- One PR = one feature × one layer (backend or frontend). A single-PR feature is allowed when it is only meaningful as a unit; say so in the description.
- No hook bypasses (`--no-verify`). No secrets in the repository — `app/.env` (git-ignored) or Codespaces secrets.

## Verify before you say it is done

- Backend changed: `cd app/backend && uv run ruff format . && make check` (ruff check + mypy + pytest). Integration tests need Postgres (`cd app && make db`) and `TEST_DATABASE_URL`.
- Frontend changed: `cd app/frontend && npm run typecheck`; if the API shape changed, `cd app && make spec && make gen` first.
- Whole stack: `cd app && make up && curl http://127.0.0.1:8000/healthz`.
- CI mirrors this: `.github/workflows/backend.yml` (ruff format/check, mypy, pytest unit + integration, OpenAPI freshness) and `frontend.yml` (typecheck, orval freshness).

## Tooling in this directory

- `.claude/skills/pr-summary/` — `/pr-summary` drafts a PR description (intent + changed files) from the diff against `main` and warns when a branch mixes layers or features.
- `.claude/settings.json` — project-level permission allow-list for routine commands (docker compose, make targets, uv, npm, local curl checks). Machine-specific paths belong in `settings.local.json`, which is git-ignored.
