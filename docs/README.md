# Design documents

This directory is the design record of the project: the original requirements document and the Architecture Decision Records (ADRs) written while building it. Documents are numbered in the order they were written; later ADRs state explicitly which earlier sections they supersede, and the originals are never rewritten.

**Language.** [ADR-002](./002-phase-b-decisions.md) and [ADR-006](./006-records-user-scope-schema.md) are fully in English. The other documents are in Japanese with an English summary block at the top; the summaries below are the same text. [DEVELOPMENT.md](./DEVELOPMENT.md) (developer guide) is in English.

**Numbering gaps.** 004 was a short-lived reorder ADR that was withdrawn; 008–011 were never used. A few personal notes (product vision, UI philosophy, a places/venues design) are referenced in passing by some ADRs but are not part of the public repository.

## Reading order for a first visit

1. [002](./002-phase-b-decisions.md) — the architecture as it actually is (PostgreSQL, 3-layer backend, orval contract, UUID v7, lenient PUT).
2. [006](./006-records-user-scope-schema.md) and [007](./007-releases-user-scope.md) — the catalog / ownership split that makes the app multi-user.
3. [005](./005-railway-deploy-prep.md) — environment-driven deployment and the OAuth trade-offs.
4. [013](./013-digging-tab-and-concert-removal.md) → [016](./016-audio-recognition-on-the-hunt.md) — how the product changed after real use.

## Index

| # | Document | Status | Language |
|---|---|---|---|
| 000 | [Requirements v1.7](./000-pre-adr.md) | baseline (partly superseded) | JA + summary |
| 001 | [Phase A revisions](./001-phase-a-revisions.md) | Accepted | JA + summary |
| 002 | [Phase B kickoff decisions](./002-phase-b-decisions.md) | Accepted | **EN** |
| 003 | [Artist management: three layers and the experience lifecycle](./003-artist-management.md) | Proposed | JA + summary |
| 005 | [Railway deploy preparation (env-driven)](./005-railway-deploy-prep.md) | Proposed (implemented) | JA + summary |
| 006 | [Split records into catalog + user_collections](./006-records-user-scope-schema.md) | Accepted | **EN** |
| 007 | [Releases: catalog + per-user read state, follow-scoped feed](./007-releases-user-scope.md) | Accepted | JA + summary |
| 012 | [On This Day — daily picks](./012-daily-picks.md) | Proposed (not implemented) | JA + summary |
| 013 | [Feed → Digging, hunt list, concert UI removal](./013-digging-tab-and-concert-removal.md) | Accepted | JA + summary |
| 014 | [Pin UI moved to the detail modal](./014-record-pin-ui-relocation.md) | Accepted | JA + summary |
| 015 | [Auto-pin, pin limit 6, owned-only view all](./015-pin-auto-and-limit.md) | Accepted | JA + summary |
| 016 | [Audio recognition — the Listen tab](./016-audio-recognition-on-the-hunt.md) | Accepted | JA + summary |
| 017 | [Shelf welcome toast](./017-shelf-welcome-toast.md) | Accepted | JA + summary |
| 018 | [Cost minimization by service distribution](./018-cost-minimization-service-distribution.md) | Proposed | JA + summary |

## Summaries

### 000 — Requirements v1.7

The original requirements document for the MVP (v1.7, 2026-05-10): a personal "collection + feed" dashboard for a jazz listener with three screens — **Home** (a visual matrix of owned vinyl that flips over to show notes), **Feed** (new releases and Japan concerts for followed artists) and **Artists** (Spotify follow sync, manual entries, name aliases). It fixes the mock-first development approach (Phase A frontend mock → Phase B backend → Phase C scraping/integration), the hybrid type-contract strategy (hand-written types first, OpenAPI-generated types later), the initial data model (`artists`, `artist_aliases`, `releases`, `vinyl_records`, `venues`, `concerts`, `sync_status`), the Docker layout, the authentication approach and a risk register. Several sections are superseded by later ADRs — notably 002 (PostgreSQL, clean architecture, orval), 005 (auth allow-list, env handling) and 013 (Feed → Digging, concerts removed).

### 001 — Phase A revisions

A snapshot of the decisions made while building the Phase A frontend mock: `vinyl_records` gains `original_release_date` (`"YYYY"` or `"YYYY-MM"`) and `favorite_tracks`; `rating` and `purchase_price` stay in the schema but are hidden in the UI; feed read/unread state is kept in `localStorage` in the mock with a plan for `read_at` columns or a `feed_read_state` table; the write API is fixed as `POST /api/records`, `PUT /api/records/{id}` and `PUT /api/records/{id}/jacket` with server-side id assignment; jacket images are stored on the local filesystem and resized with Pillow; artist images fall back to an initials avatar. Ends with a Phase B checklist. Partly superseded by ADR-002 (UUID v7, lenient PUT) and ADR-007 (read state as its own table).

### 002 — Phase B kickoff decisions *(English)*

The re-evaluation at the start of backend work: PostgreSQL 16 from day one (the SQLite plan is dropped); a 3-layer clean architecture (`routers → services → core/repositories`) with one-way dependencies; UUID v7 primary keys; lenient PUT (partial update via `exclude_unset`); `display_order` assignment serialized with `pg_advisory_xact_lock`; Alembic from the first migration; orval instead of `openapi-typescript` (types **and** react-query hooks, generated from a committed `openapi.json` owned by the backend); the mock toggle is kept; a unit/integration test matrix. Includes supersede notes against 000/001 and the Phase B-2 checklist.

### 003 — Artist management: three layers and the experience lifecycle

Part 1 sets the product philosophy in seven principles — records come first and artists are a by-product; time, not a follow limit, prunes the list (follows without activity for two years fade); ownership is permanent while interest is fluid; only deliberate actions (adding a record, opening an artist page) update a relationship; Home shows only physically owned records; the artist page is where Feed meets Collection; the degree of physicality decides the granularity of notes — and it explicitly rejects algorithmic recommendation. Part 2 splits artists into a master catalog (`artists`), per-user `user_follows` (follow + pin + `archived_flag` decay) and `vinyl_records` with an `owned`/`wanted` status, adds concert attendance tables, and lists APIs and flows. Part 3 is the PR plan with code patterns (auto-follow on record creation, the 5-pin constraint, the "touch" logic). Appendices record rationale, alternatives considered, deliberately deferred decisions and open questions.

### 005 — Railway deploy preparation (env-driven)

Prepares the first production deployment without forking the code: every environment difference becomes an env var (`CORS_ALLOW_ORIGINS`, `COOKIE_SECURE` / `COOKIE_SAMESITE` with a validator that enforces `Secure` for `SameSite=None`, `FRONTEND_BASE_URL`, `SPOTIFY_REDIRECT_URI`, `VITE_API_BASE`, `VITE_ALLOWED_HOSTS`); `DATABASE_URL` is normalized from `postgres://` to `postgresql+psycopg://`; the frontend Dockerfile becomes multi-stage (Vite dev server vs. nginx-served static build); the app-side Spotify allow-list is removed in favour of the Spotify dashboard's *Users and Access* list; migrations keep running from the container entrypoint; the backend must run as a single replica because OAuth state is process-local; `/docs` can be hidden with `EXPOSE_OPENAPI_DOCS=false`. The env checklist from §3.7 now lives in [DEVELOPMENT.md](./DEVELOPMENT.md).

### 006 — Split records into catalog + user_collections *(English)*

Makes records multi-user safe: `vinyl_records` becomes a shared catalog (Spotify-sourced rows de-duplicated by a partial unique index on `spotify_album_id`; manual rows may repeat) and a new `user_collections` table holds per-user ownership (status, purchase info, notes, display order, pins) with `UNIQUE(user_id, vinyl_record_id)`. A child table `record_favorite_tracks` stores structured favourite tracks. The API shape is unchanged (`id` is `user_collections.id`), a manual record can later be promoted to a Spotify one, and the migration plan discards pre-deploy dev data.

### 007 — Releases: catalog + per-user read state, follow-scoped feed

Applies the ADR-006 pattern to releases: `releases` stays a shared catalog synced from Spotify, and a new `release_read_states (user_id, release_spotify_id, read_at)` table holds per-user read state — a row means "read". `GET /api/releases` now returns only releases of artists the current user follows (`archived_flag = false`), joined with that user's read state, while the URL and response shape (`is_read` / `read_at`) are unchanged. The old "preserve `is_read` on upsert" logic disappears and a hand-written migration drops the old columns. A generic `feed_read_state(kind, item_id)` table is rejected for lack of foreign-key integrity. Lists repository/service changes and the tests that pin the behaviour.

### 012 — On This Day — daily picks *(proposed, not implemented)*

A proposal for a quiet "Now On Air" ticker showing a classic album released on today's date decades ago. A daily batch selects from a curated `featured_albums.json` (matching month and day), persists the pick to a `daily_picks` table (unique per date) so picks are reproducible and accumulate as material for a future "monthly personal magazine", and exposes `GET /api/daily-pick`. Phase 1 is text only (no 30-second preview). Open questions cover the candidate source, behaviour on days without a match (stay silent), tie-breaking (oldest wins), placement relative to the Feed's "today" label and click behaviour.

### 013 — Feed → Digging, hunt list, concert UI removal

Renames the Feed tab to **Digging** with two sub-tabs: **On the hunt** (a cross-artist list of wanted records, sorted A–Z by artist with an index rail, or by date added) and **Releases**. `GET /api/records` gains `status` (`owned` | `wanted`) and `sort` (`artist` | `added`) query parameters; filtering and sorting are backend responsibilities, grouping is presentation. Concert UI is removed entirely from the frontend (backend models are kept, no migration); release read state stays. Supersedes ADR-000's "Feed = releases + concerts" and its 3-tab layout. Motivated by real-world use: wanting a shopping list ordered the way record shops shelve their bins.

### 014 — Pin UI moved to the detail modal

Removes pin toggles, badges and drag-and-drop reordering from the "view all" grid so it becomes a pure browsing grid; moves the pin toggle into the record detail modal (owned records only, in the metadata section rather than over the cover art); and makes Home show only pinned owned records (limit 8 at the time, in backend `pin_order`) with explicit empty states. Frontend-only. The `PUT /api/records/pins/order` endpoint and the `pin_order` column are kept but become dormant.

### 015 — Auto-pin, pin limit 6, owned-only view all

Lowers the pin limit from 8 to 6 (matching the mobile Home preview) in both backend and mock; auto-pins a record the moment it becomes owned (creation with `status=owned`, or a wanted → owned transition) if a slot is free — never on ordinary edits and never for wanted records; and makes "view all" owned-only via a status filter so counts and pagination exclude wanted records. When the shelf is full, the add form shows an inline hint that the new record will not appear on Home. The backend is the source of truth; no API shape change.

### 016 — Audio recognition — the Listen tab

Adds a third Digging tab, **Listen**: the browser records about 12 seconds with `MediaRecorder`, `POST /api/recognize` forwards the clip to AudD (`return=spotify`) and returns a normalized `RecognitionResult` (track, album, Spotify album/artist ids, cover), which prefills the existing add-record form with `status=wanted`; unknown artists are upserted first. AudD was chosen over shazamio (terms of service, needs ffmpeg), RapidAPI Shazam (raw PCM input) and ACRCloud (overkill for a few calls a day). Tabs are URL-driven (`/digging/:tab`) with per-tab lazy fetching; microphone permission is requested only on tap and released afterwards; "no match" offers Cancel / Try again. A missing API token yields 503, an upstream failure 502.

### 017 — Shelf welcome toast

When a record becomes owned ("To the shelf": a new owned record or a wanted → owned transition), show a quiet toast at the top of the screen — "Welcome to the collection — your Nth record." — using the existing toast provider and no new libraries. The count is fetched fresh via `GET /api/records?status=owned&limit=1` (`total`) and omitted if unknown, never wrong. Celebrations appear at the top, warnings at the bottom; no automatic navigation. Frontend-only, mock parity kept.

### 018 — Cost minimization by service distribution *(proposed)*

A plan to leave Railway's three always-on services for free tiers: frontend to Cloudflare Pages (or Netlify/Vercel), backend to a scale-to-zero host (Render free tier or Fly.io), Postgres to Neon — with only env values changing, thanks to ADR-005's env-driven design. Release sync stays a manual, authenticated `POST /api/releases/sync` (no cron, no APScheduler — the scheduler dependency was never wired up), which suits scale-to-zero. Audio recognition (AudD) is isolated as the single remaining paid decision, with three options: switch to ACRCloud's free tier, keep paying AudD, or gate the feature. Accepts cold starts and keeps a single replica.
