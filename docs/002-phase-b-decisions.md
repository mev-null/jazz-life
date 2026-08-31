# 002. Phase B kickoff decisions (PostgreSQL / clean architecture / orval)

**Status**: Accepted (snapshot as of Phase B-1 completion)
**Date**: 2026-05-10
**Relates to**: [000-pre-adr.md](./000-pre-adr.md) §11 (architecture), §12 (data model), §13 (tech stack), §14 (Docker setup), §16 (development procedure) / [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 (finalization of the write API)

---

## 1. Context

As Phase B-1 (backend implementation of the home feature) got underway, the following assumptions made through Phase A needed to be revisited.

- **DB**: 000-pre-adr.md §13 / §14 specified "SQLite for the MVP, migrate to PostgreSQL in Phase 2."
- **Migrations**: §12 of the same document set out a staged approach: "`create_all()` initially, introduce Alembic in Phase C-4."
- **vinyl_records.id**: §12 of the same document and 001-phase-a-revisions.md §2.3 had settled on "server-side auto-increment (int)."
- **PUT semantics**: 001-phase-a-revisions.md §2.3 specified "the PUT body is the full `VinylRecord`."
- **Type generation tool**: 000-pre-adr.md §13 / §17 assumed type-only generation via `openapi-typescript`.

These were provisional policies as of the end of Phase A; during the Phase B-1 implementation, several items were re-decided from the standpoint of "eliminating future debt ahead of time." This ADR consolidates those decisions.

Without consolidating them, the following problems are anticipated.

- In sessions from Phase B-2 onward, whether each assumption still holds would have to be judged from the source each time.
- Discrepancies between the text of 000-pre-adr.md / 001-phase-a-revisions.md and the implementation would surface, potentially causing rework at the Phase 2 cloud migration.
- Follow-up work (switching the frontend's `make gen`, implementing jacket upload, etc.) could misread the assumptions.

---

## 2. Decision

### 2.1 Adopt PostgreSQL 16 from the start of Phase B (drop the SQLite plan)

Withdraw "SQLite for the MVP" from [000-pre-adr.md](./000-pre-adr.md) §13 / §14 and adopt **PostgreSQL 16 (alpine)** from the start of Phase B-1.

- Add a `db` service to docker-compose, persisted with the named volume `jazz-pgdata`.
- Separate two databases, `jazz` (dev) and `jazz_test` (test), within the same instance via an initdb script (`app/db/init/01-create-test-db.sql`).
- Use `psycopg[binary]` 3.x (synchronous) for connections.

#### Rationale

- `vinyl_records.id` adopts UUID v7 (§2.3). While theoretically possible with SQLite, building on the ecosystem compatible with Postgres's `uuid` type / `gen_random_uuid()` avoids mismatches in future extensions.
- Postgres is expected to remain in use for the Phase 2 cloud deployment; aligning the boundary conditions between development and production (trailing-whitespace comparison, case sensitivity, transaction isolation levels, etc.) from the outset keeps later debugging costs low.
- Postgres's `pg_advisory_xact_lock` is used to serialize `display_order` assignment (§2.5). SQLite has no equivalent mechanism.
- The cost of spinning up a real DB even for local development is hidden by Docker, so SQLite's advantage is small.

### 2.2 3-layer clean architecture

[000-pre-adr.md](./000-pre-adr.md) had no provisions regarding the internal module structure of the backend. Phase B-1 adopts the following 3-layer structure.

```
app/backend/app/
├── core/
│   ├── db.py                    # engine / get_session
│   ├── exceptions.py            # DomainError / NotFoundError
│   └── repositories/            # DB access layer (SQLModel exec, col() style)
├── services/                    # business logic layer (numbering / partial updates / raising DomainError)
├── schemas/                     # Pydantic API DTOs (Read / Create / Update separated)
├── models/                      # SQLModel ORM
└── routers/                     # thin FastAPI API layer (DTO ↔ service conversion, http_errors mapping)
```

#### Rationale and conventions

- The dependency direction is fixed one-way: `routers → services → repositories → models`. Imports in the reverse direction are prohibited.
- Exception mapping is centralized in the `http_errors()` context manager in the routers layer. When a service raises `NotFoundError` it maps to 404; defining additional DomainError subclasses maps them to the corresponding HTTP status.
- Dependency injection is built with FastAPI's `Depends` chain (`get_session → get_*_repository → get_*_service`). Because `get_session` is cached within a single request, multiple repositories share the same session.
- API DTOs are separated into `*Read` / `*Create` / `*Update`. All fields of `*Update` are optional, supporting the partial-update semantics of §2.4.

### 2.3 Change vinyl_records.id to UUID v7

Withdraw "`id: int` (auto increment)" from [000-pre-adr.md](./000-pre-adr.md) §12 and "standardize on server-side auto-increment" from [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3, and adopt **UUID v7**.

- Generation happens on the backend (`uuid7()` from the `uuid6` library). Client-side generation will be considered when offline editing support is added in the future.
- The artists family (`artists.spotify_id`, `concerts.id`, etc.) keeps string PKs. This decision is limited to `vinyl_records.id` and future purely app-internal entities.

#### Rationale

- UUID v7 is time-ordered and sortable, so listings that do not go through `display_order` still get a stable order.
- Avoids id collisions with an eye toward multi-client use and a future sync feature.
- Unlike BIGINT auto-increment, including the id in a URL does not expose an ordinal (a weak reason for a personal app, but a side benefit).

#### Known caveats

- URL copy-pasting and curl checks during development are more cumbersome than with int. This was handled in Phase B-1 by including a dummy UUID (`00000000-0000-7000-8000-000000000000`) in the `.claude/settings.json` allowlist.

### 2.4 Lenient PUT semantics (partial update)

Withdraw "the PUT body is the full `VinylRecord`" from [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 and adopt **partial-update semantics that update only the fields that were sent**.

- Pydantic's `model_dump(exclude_unset=True)` extracts only the "explicitly sent fields."
- Explicitly sending `null` clears the field to null. Fields not sent retain their previous values.
- `updated_at` is always overwritten on the server side. `created_at` is immutable.
- Reassigning `artist_id` is allowed, but the existence of the new `artist_id` is verified; if it does not exist, `NotFoundError` is raised (404).

#### Rationale

- Aligns naturally with the frontend edit modal's design of "send only the changed fields."
- In terms of HTTP semantics PATCH would be the strict choice, but since this API assumes a single client and idempotency is preserved, we went with lenient PUT (partial update). Room is left to migrate to a PATCH conforming to RFC 7396 (JSON Merge Patch).

### 2.5 Serializing display_order assignment (adopt pg_advisory_xact_lock)

As a countermeasure to the race condition in "new additions use `display_order = MAX + 1`" from [000-pre-adr.md](./000-pre-adr.md) §12, acquire `pg_advisory_xact_lock` on the create path in the service layer.

```python
# RecordRepository
def lock_for_display_order(self) -> None:
    self.session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": self._DISPLAY_ORDER_LOCK_KEY},
    )
```

#### Rejected alternatives

- **`SELECT max(display_order) ... FOR UPDATE`**: Postgres rejects FOR UPDATE on an aggregate as a syntax error.
- **`SELECT ... ORDER BY display_order DESC LIMIT 1 FOR UPDATE`**: Under READ COMMITTED isolation, after the lock is released it re-locks "the row that was selected by the original query (the old MAX)." Because it does not re-read the newly COMMITted MAX row, a later transaction assigns the old MAX `+1`, and duplicates occurred in the regression test.

#### Advantages of the advisory lock

- Transaction-scoped and automatically released on COMMIT / ROLLBACK.
- Works even on an empty table (FOR UPDATE variants leave a race on an empty table because there is no row to lock).
- The aggregate query (`SELECT max(...)`) can be used as-is.

#### Key constant

Uses `0x1A22_DE51_0001` (an arbitrary fixed value). If advisory locks are introduced elsewhere in the future, consider consolidating the constants to avoid collisions (currently the sole use).

### 2.6 Introduce Alembic from Phase B-1

Move "introduce Alembic + generate the initial migration" from [000-pre-adr.md](./000-pre-adr.md) §16 Phase C-4 forward to Phase B-1.

- Place the Alembic environment in `app/backend/migrations/`.
- Fix migration file names to the `YYYYMMDD_HHMM_<slug>` format via `file_template` in `alembic.ini`.
- The initial migration (`0001_initial`) defines all 8 tables (artists / artist_aliases / venues / concerts / concert_artists / releases / vinyl_records / sync_status) at once. `releases.read_at` / `concerts.read_at` ([001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.2) are included.
- `entrypoint.sh` runs `alembic upgrade head` on container startup before launching uvicorn.

#### Rationale

- Since multiple tables are defined at the same time as adopting Postgres, operating with `SQLModel.metadata.create_all()` tends to diverge from production.
- It establishes the premise of running `alembic upgrade head` in CI, so schema changes in subsequent PRs can be tracked safely.

### 2.7 Type generation toolchain: openapi-typescript → orval

Replace **`openapi-typescript`** in `make gen` from [000-pre-adr.md](./000-pre-adr.md) §4 / §13 / §16 with **`orval`** at the time of the Phase B-2 frontend connection.

#### Rationale

- `openapi-typescript` generates only type schemas. The React Query (TanStack Query v5) `useQuery` / `useMutation` hooks and the fetch wrapper would all be hand-written.
- `orval` generates **types + HTTP client + React Query hooks** in one go. `queryClient.invalidateQueries` after a mutation can be written type-safely, and missed follow-ups on API changes are caught as type errors.
- Shortens the propagation path from spec changes to frontend implementation.

#### Adopted configuration

- **client mode**: `react-query` + plain `fetch` (no axios dependency added)
- **output mode**: `tags-split` (directories split by FastAPI tag)
- **output location**: `app/frontend/src/api/generated/` (not `gitignore`d)
- **mock generation**: not adopted in this ADR. orval's msw integration is a Phase 2 candidate (consistent with §2.8).

#### Staged migration toward Phase B-2

The frontend replacement is handled as a PR independent of the backend.

- **PR-A (type foundation)**: introduce orval, replace `make gen`, **switch only the types for already-implemented endpoints (artists / records) to the generated source** (the unimplemented releases / concerts / sync_status / auth remain hand-written in `types/api.ts`), and convert mock JSON ids to UUID strings. The OpenAPI spec is committed as `app/backend/openapi.json`, owned by the backend, and the frontend has orval read `../backend/openapi.json`. This keeps API-change diffs contained within backend PRs and out of frontend PRs. The setup in which `make gen` / CI run even without the backend running is unchanged. Behavior stays as-is with `VITE_USE_MOCK=true`.
- **PR-B (real API connection)**: split `upsertVinylRecord` into `createVinylRecord` (POST) / `updateVinylRecord` (PUT), switch `VITE_USE_MOCK` in `.env.example` to `false`, and verify the golden path in the browser.

### 2.8 Keep the mock toggle mechanism

Keep the "mock / real API toggle via `VITE_USE_MOCK`" from [000-pre-adr.md](./000-pre-adr.md) §4 in Phase B-2 and beyond.

- Keep a branching layer equivalent to `client.ts`, which dispatches at the upper level between the real API hooks generated by orval and the existing `mocks/*.json`.
- orval-generated hooks serve only the real API path. The mock path remains `if (USE_MOCK)`.
- Hand-written mock JSON is maintained for the time being. orval's msw feature (auto-generating msw handlers from the spec) is a Phase 2 candidate.

#### Rationale

- Preserves the developer experience of working on the frontend without the backend running.
- Useful for verifying the fallback when the backend is down.
- Complete removal would carry the large cost of "rewriting a large amount of documentation that assumes mocks," which is not worth the benefit.

### 2.9 Test strategy (unit / integration matrix)

CI (`.github/workflows/backend.yml`) runs 3 jobs in parallel.

- **lint-and-typecheck**: `ruff format --check` + `ruff check` + `mypy app`
- **test (unit)**: `pytest tests/unit -v`
- **test (integration)**: `pytest tests/integration -v`

#### Adopted policy

- Both suites use a real PostgreSQL (GitHub Actions services container). Since `tests/unit` also exercises the service layer against the real DB, it is not strictly a unit suite (a cost-based decision not to maintain the distinction from pure mock-based unit tests).
- conftest injects the test session via `app.dependency_overrides[get_session]`.
- Constructing `TestClient(app)` **without** a `with` block avoids triggering FastAPI's lifespan, preventing seed data from being inserted into the dev DB.
- The engine fixture is function-scoped with `drop_all → create_all → drop_all`. If it starts slowing down as the number of tests grows, consider moving to session-scoped + `TRUNCATE ... CASCADE`.

---

## 3. Out of scope

The following items are not covered by this ADR and are left to subsequent PRs / ADRs.

- **frontend orval migration implementation**: implemented independently as PR-A / PR-B following the policy in §2.7.
- **jacket image upload API implementation**: implemented in Phase B-2 per the spec in [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.4.
- **`PATCH /api/records/reorder`**: bulk update for drag-and-drop reordering. Implemented in Phase B-2.
- **releases / concerts API implementation**: Phase B-2 or later.
- **mark-as-read API implementation**: implemented in a subsequent PR per the spec in [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.2.
- **Spotify OAuth / new-release batch**: Phase B-3 or later.
- **AI autofill** (`POST /api/records/lookup`): [000-pre-adr.md](./000-pre-adr.md) §19.2.
- **Multi-user support**: the single-user assumption is maintained for the time being.

---

## 4. Consequences

### Positive

- No DB engine switch is needed at the Phase 2 cloud migration, and behavioral differences from production can be eliminated from the start.
- Adopting UUID v7 avoids id collisions in future multi-client and distributed scenarios.
- The 3-layer separation makes service / repository unit tests easier to set up, and exception mapping is centralized via `http_errors()`.
- Adopting orval allows mutation cache invalidation to be written type-safely, and missed frontend follow-ups on spec changes are caught as type errors.
- Early adoption of Alembic allows schema changes from Phase B-2 onward to be tracked safely in the YYYYMMDD_HHMM_<slug> format.

### Negative / caveats

- docker compose gains one more required service (db), raising startup cost and memory usage (acceptable for personal development).
- UUID v7 makes curl checks and URL copy-pasting more cumbersome than int. Handled by registering a dummy UUID in the `.claude/settings.json` allowlist.
- The volume of orval-generated code grows (not `gitignore`d). Diffs in generated output are included in the scope of PR review.
- The advisory lock key constant `0x1A22_DE51_0001` is a magic number; if advisory locks are introduced elsewhere in the future, consolidated management will need to be considered.
- The related text in [000-pre-adr.md](./000-pre-adr.md) §12 / §13 / §14 / §16 and [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 is superseded by this ADR. The originals are not amended; this ADR is treated as the canonical source to reference.

---

## 5. Supersede notes (mapping of replacements)

| Original | Section | Old policy | New policy (this ADR) |
|---|---|---|---|
| [000-pre-adr.md](./000-pre-adr.md) | §12 vinyl_records | `id: int` (auto increment) | UUID v7 (§2.3) |
| [000-pre-adr.md](./000-pre-adr.md) | §13 / §14 | DB is SQLite, migrate to Postgres in Phase 2 | Adopt PostgreSQL 16 from Phase B-1 (§2.1) |
| [000-pre-adr.md](./000-pre-adr.md) | §12 / §16 C-4 | Operate with `create_all()`, introduce Alembic in Phase C-4 | Operate with Alembic from Phase B-1 (§2.6) |
| [000-pre-adr.md](./000-pre-adr.md) | §4 / §13 / §16 | `make gen` uses `openapi-typescript` | `make gen` uses `orval` (react-query + fetch mode) (§2.7) |
| [001-phase-a-revisions.md](./001-phase-a-revisions.md) | §2.3 id assignment | Server-side auto-increment | Server-side UUID v7 (§2.3) |
| [001-phase-a-revisions.md](./001-phase-a-revisions.md) | §2.3 PUT body | Full `VinylRecord` | Partial-update semantics (`exclude_unset`) (§2.4) |

---

## 6. Phase B-2 implementation checklist

The Phase B-2 work items derived from this ADR are summarized below.

### frontend: orval introduction and type replacement (PR-A)

- [ ] Add `orval` to `app/frontend` as a devDependency (remove `openapi-typescript`)
- [ ] Create `orval.config.ts` (input: `../backend/openapi.json`, client: `react-query`, httpClient: `fetch`, output mode: `tags-split`, output path: `src/api/generated/`)
- [ ] Commit the OpenAPI spec as `app/backend/openapi.json` (owned by the backend; formatted to 2-space indent with jq)
- [ ] Split `app/Makefile` into `make spec` (re-fetch the spec from the backend) and `make gen` (generate from the spec file)
- [ ] Implement a custom mutator for orval (`src/api/mutator.ts`) that reads `API_BASE` from env and performs fetch
- [ ] Remove the already-implemented parts (`Artist` / `VinylRecord`) from `src/types/api.ts` and shrink it to re-export from generated/ (the unimplemented `Release` / `Concert` / `SyncStatus` / `AuthUser` etc. remain hand-written)
- [ ] Convert `id` in `src/api/mocks/*.json` to UUID strings (vinyl_records)
- [ ] Add the `source` / `purchase_currency` fields to `src/api/mocks/*.json` (match the shape of real API responses)
- [ ] Change the `Date.now()`-based id generation in `RecordFormModal` to `crypto.randomUUID()` (since VinylRecord.id is now a string)
- [ ] Keep the `VITE_USE_MOCK` branch in `client.ts` (only the real API side goes through the orval-generated fetcher)
- [ ] `npm run typecheck` is green

### frontend: connect home to the real API (PR-B)

- [ ] Split `upsertVinylRecord` into `createVinylRecord` (POST) / `updateVinylRecord` (PUT)
- [ ] Route the save logic in `RecordFormModal` as "new → create, edit → update"
- [ ] Change `VITE_USE_MOCK` in `app/.env.example` to `false`
- [ ] Start the stack with `make up` and verify the golden path of listing / adding / editing records in the browser
- [ ] Verify that react-query cache invalidation runs correctly and the list refreshes after adding / editing
- [ ] Verify UI behavior for error cases (invalid date, nonexistent artist, 422 / 404 responses)

### backend / docs (groundwork for Out of scope items, sequentially in separate PRs)

- [ ] Implement the jacket upload API (spec in [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.4)
- [ ] Implement `PATCH /api/records/reorder`
- [ ] Implement the releases / concerts API
- [ ] Implement the mark-as-read API (updating `releases.read_at` / `concerts.read_at`)
