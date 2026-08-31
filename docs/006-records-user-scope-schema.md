# ADR-006: Split records into catalog + user_collections

**Status**: Accepted | **Date**: 2026-05-13
**Related**: [ADR-000](./000-pre-adr.md) §F-H2 / §7 (back-cover metaphor), [ADR-001](./001-phase-a-revisions.md) §2.1 (original intent of favorite_tracks), [ADR-002](./002-phase-b-decisions.md) §2.1 (adoption of PostgreSQL), [ADR-003](./003-artist-management.md) §1.2 Principle 7 (the degree of physicality determines the granularity of notes), [ADR-005](./005-railway-deploy-prep.md) §2.10 (operational guard)

---

## 1. Context

A critical problem surfaced during deploy preparation in [ADR-005](./005-railway-deploy-prep.md):

- The current `vinyl_records` table **has no user_id column**. `RecordService.list_all / update_partial / delete` do not filter by user.
- Because ADR-005 §2.8 decided to "consolidate invite control into Users and Access on the Spotify Developer Dashboard", **multiple users registered on the Dashboard can share and tamper with the same records**.
- Simply adding `vinyl_records.user_id` would be enough to make records user-scoped, but it leaves little design room for "adding per-user extension tables such as `record_favorite_tracks` in the future".
- User request: **split album metadata and ownership into two layers**. A "catalog that can be deduped against Spotify" and a "user's collection" have different responsibilities. In the future we want to use `user_collections.id` as an FK target and grow per-user derived tables (favorite tracks, etc.) from it.

Operational guard for this ADR (ADR-005 §2.10): register **only your own Spotify account** on the Spotify Dashboard. Do not invite multiple users until the implementation of this ADR lands.

---

## 2. Decision

### 2.1 Split into a two-layer schema

```
artists (existing, unchanged)
   ↑
   │ artist_id
   │
vinyl_records (catalog: album metadata)
  - rows with source='spotify': spotify_album_id NOT NULL, deduped across all users
  - rows with source='manual':  spotify_album_id NULL, duplicates allowed
   ↑
   │ vinyl_record_id
   │
user_collections (ownership: per-user ownership relation)
  - UNIQUE(user_id, vinyl_record_id) rejects "owning the same catalog row twice"
```

### 2.2 Spotify dedup via partial UNIQUE INDEX

On `vinyl_records.spotify_album_id`:

```sql
CREATE UNIQUE INDEX uq_vinyl_records_spotify_album_id_not_null
  ON vinyl_records (spotify_album_id)
  WHERE spotify_album_id IS NOT NULL;
```

With the Postgres partial UNIQUE INDEX,

- `source='spotify'` rows (`spotify_album_id` NOT NULL) are forced to 1 album = 1 row across all users
- `source='manual'` rows (`spotify_album_id` NULL) may be duplicated (NULLs are not included in the partial index)

### 2.3 Manual records allow duplicates

We allow the same handwritten title (such as "Self-Recorded Live 2026-01-15") to be registered by different users, or multiple times by the same user. Since `manual` rows have no `spotify_album_id`, catalog dedup does not apply and **a new vinyl_records row is created every time**.

### 2.4 Preventing double ownership in user_collections

```sql
CREATE UNIQUE INDEX uq_user_collections_user_vinyl_record
  ON user_collections (user_id, vinyl_record_id);
```

With this, when the same user POSTs the same Spotify album twice, the catalog is deduped and collapsed into a single `vinyl_records.id`, so we can return a 4xx as a UNIQUE violation on the user_collections side.

### 2.5 API surface fully preserved

- The URL / response shape of `/api/records` **does not change**
- The `id` in the response is **`user_collections.id`** (the frontend works without changes)
- The POST request shape also stays `VinylRecordCreate`. Internally, the catalog branch is chosen based on whether `spotify_album_id` is present
- PUT keeps accepting the same fields. Updates to catalog-side fields (title / image_url / original_release_date / artist_id) are applied only to `source='manual'` rows; `source='spotify'` rows are silently ignored (shared metadata)

### 2.6 Display order is per user

`display_order` lives on the `user_collections` side. Using the two-argument form of `pg_advisory_xact_lock(k1, k2)` with `k2 = hash(user_id)`, we **serialize per user**. POSTs from other users are not blocked.

### 2.7 Handling catalog orphans

When a user deletes a user_collections row, a `source='manual'` vinyl_records row is not referenced by any other user (it is always 1:1 because it is never deduped) → it effectively becomes an orphan, but this ADR deliberately leaves it in place. Reasons:

- No practical harm (`/api/records` goes through a JOIN via user_collections, so it is not visible)
- If the user later re-registers it ("actually, I do own this album"), the UUID differs, but from the user's perspective nothing feels off, title included
- If cleanup is wanted later, adding a delete-after hook in the service layer is enough

`source='spotify'` rows are catalog, so they are never physically deleted.

### 2.8 record_favorite_tracks (implemented in this ADR)

A per-user "favorite tracks" table tied to user_collections is implemented as part of this ADR. It was initially treated as Future work for a separate ADR, but review settled on the experience of "adding Spotify search results one track at a time + writing a short impression (`note`) for each track", so it is folded into this ADR.

```sql
CREATE TABLE record_favorite_tracks (
  user_collection_id UUID NOT NULL REFERENCES user_collections(id) ON DELETE CASCADE,
  position INT NOT NULL,
  spotify_track_id TEXT NULL,        -- from Spotify search results; NULL for manual
  track_name TEXT NOT NULL,
  note TEXT NULL,                    -- short per-track impression (a note scribbled on the back cover)
  PRIMARY KEY (user_collection_id, position),
  UNIQUE (user_collection_id, spotify_track_id)
);

CREATE INDEX ix_record_favorite_tracks_spotify_track_id
  ON record_favorite_tracks (spotify_track_id)
  WHERE spotify_track_id IS NOT NULL;
```

Rationale:

- Under ADR-003 §1.2 Principle 7, "the degree of physicality determines the granularity of notes", records are classified on the "full set (photo spread)" side, so structuring tracks is consistent with the principle. Whereas concert notes were on the "column (free text)" side, favorite tracks on a record are on the "photo spread (structured)" side
- The intent of ADR-001 §2.1, "keep 'favorite tracks' as free text", is preserved via the `note` column. The two-tier structure, `user_collections.memo` for the impression of the album as a whole (the magazine column) and `record_favorite_tracks.note` for per-track scribbles, secures the "UX that makes you want to write a story" (product vision notes, not published)
- Tracks are fetched from Spotify via **Get Album Tracks** (`/v1/albums/{album_id}/tracks`) → checkbox selection on the frontend → INSERT into this table
- `track_name` is stored denormalized; no `tracks` catalog table is created. Reason: there is currently no demand where catalog sharing pays off, such as "popular tracks across all users" or "Spotify Liked Songs sync", and we do not want to add more orphan management. If it becomes necessary later, it can be extracted with a local migration while referencing `spotify_track_id` through the partial INDEX (the partial INDEX is created ahead of time in this ADR as groundwork for exactly this)
- Ordering is held in the `position` column; when editing, an advisory lock per user_collection is enough (independent of the user-wide display_order lock)

### 2.9 Manual → Spotify promote

We allow a flow where a user who registered a record manually later realizes "this was on Spotify" and fills in `spotify_album_id`. The implementation phase will inevitably hit this scenario, so it is spelled out in this ADR.

Spec:

1. Triggered when the `PUT /api/records/{id}` body contains a non-NULL `spotify_album_id`
2. The service layer looks up a catalog row with that `spotify_album_id` using `SELECT FOR UPDATE`:
   - No existing row → UPDATE the current `vinyl_records` row (`source='manual'` → `'spotify'`, set `spotify_album_id`). The partial UNIQUE INDEX prevents duplicates at the SQL layer, so idempotency is guaranteed
   - Existing row (another user has already cataloged the same Spotify album) → repoint `user_collections.vinyl_record_id` to the existing catalog row; the original manual catalog row is left as an orphan per §2.7
3. A promote request against a `source='spotify'` row is silently ignored (already promoted)
4. `record_favorite_tracks` is linked via `user_collection_id`, so repointing the catalog row has no effect on it

The frontend needs no changes since the response shape is preserved.

---

## 3. Specification

### 3.1 Columns of `vinyl_records` (catalog)

| Column | Type | Notes |
|---|---|---|
| id | UUID v7 | PK |
| artist_id | text(64) | FK → artists.spotify_id, ON DELETE RESTRICT |
| spotify_album_id | text(64) NULL | partial UNIQUE INDEX `WHERE spotify_album_id IS NOT NULL` |
| source | text(20) | `'spotify'` \| `'manual'` |
| title | text(300) |  |
| image_url | text(500) NULL |  |
| original_release_date | text(10) NULL |  |
| created_at | timestamptz |  |
| updated_at | timestamptz | updated on title fixes etc. to manual rows |

**status / purchase_* / rating / memo / favorite_tracks / pressing_info / display_order** are removed from the current `vinyl_records`.

### 3.2 Columns of `user_collections` (new)

| Column | Type | Notes |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID | FK → users.id ON DELETE CASCADE, INDEX |
| vinyl_record_id | UUID | FK → vinyl_records.id ON DELETE CASCADE |
| status | text(20) | `'owned'` \| `'wanted'`, default `'owned'` |
| pressing_info | text(200) NULL | physical pressing info (per-copy) |
| purchase_date | date NULL |  |
| purchase_store | text(200) NULL |  |
| purchase_price | int NULL |  |
| purchase_currency | text(3) | default `'JPY'` |
| rating | int NULL | 1..5 |
| memo | text(2000) NULL | Impression of the album as a whole (the magazine column / the body of the handwritten note on the back cover). Per-track impressions are held separately in `record_favorite_tracks.note` |
| display_order | int |  |
| created_at | timestamptz |  |
| updated_at | timestamptz |  |

UNIQUE INDEX `uq_user_collections_user_vinyl_record` on (`user_id`, `vinyl_record_id`).

### 3.3 Migration plan

Since this is pre-deploy, **existing dev data is discarded**. One hand-written migration is cut:

1. `DELETE FROM vinyl_records` (nothing has been loaded into production)
2. DROP the unneeded columns from `vinyl_records` (status / purchase_* / rating / memo / favorite_tracks / pressing_info / display_order)
3. Create the partial UNIQUE INDEX `uq_vinyl_records_spotify_album_id_not_null`
4. CREATE the `user_collections` table (columns + FKs + UNIQUE INDEX)
5. Indexes: `ix_user_collections_user_id`, `ix_user_collections_vinyl_record_id`
6. CREATE the `record_favorite_tracks` table (FK + composite PRIMARY KEY + UNIQUE INDEX + partial INDEX restricted to non-NULL `spotify_track_id`)

Alembic autogenerate is unstable with the `postgresql_where` of a partial UNIQUE INDEX (a diff shows up every time), so the migration is **written by hand**. On the SQLModel side, put the corresponding `Index(..., postgresql_where=text("..."))` in `__table_args__` to keep the model and the DB in sync.

### 3.4 API layer implementation policy

- **`RecordService.create(data, user_id)`**:
  - `data.spotify_album_id` is non-NULL → `SELECT FOR UPDATE` on `vinyl_records` by `spotify_album_id` / INSERT if absent (find-or-create)
  - NULL → always INSERT a new `vinyl_records` row
  - Then INSERT into `user_collections` (assigning `display_order` under the advisory lock)
  - IntegrityError on the `user_collections` UNIQUE → return the existing user_collection or 409 (which one is decided in the PR)
- **`RecordService.list_for_user(user_id)`**: build flat rows from `user_collections` ← LEFT JOIN `vinyl_records` and adapt them to `VinylRecordRead`
- **`RecordService.update_partial(id, patch, user_id)`**: look up `user_collections` by user_id to get the catalog id. Catalog fields (title / image_url / original_release_date / artist_id) are written only when `source='manual'`
- **`RecordService.delete(id, user_id)`**: physically delete `user_collections`. `record_favorite_tracks` is deleted automatically by CASCADE; `vinyl_records` is left untouched
- **`RecordService.set_favorite_tracks(record_id, tracks, user_id)`**: after looking up `user_collections.id` by user_id, replace `record_favorite_tracks` for that collection by deleting all rows → INSERTing the new ones. `position` follows array order; whether it is 0- or 1-based is decided in the implementation phase. If the same `spotify_track_id` is sent twice within the same collection, return a 4xx as a UNIQUE violation. Whether this becomes a new API endpoint or is included in the PUT body is decided in a separate PR (the impact on OpenAPI differs)
- Include `favorite_tracks: list[FavoriteTrack]` in the response of **`RecordService.list_for_user`** (ascending by position). To avoid N+1 from the frontend, load them in bulk within the same TX as the collection list query

### 3.5 Affected tests

Almost all records-related tests need to be rewritten:

- `tests/integration/test_records.py`: replace direct INSERTs with a two-step "catalog + user_collections" insert helper / add cross-user isolation tests / verify Spotify dedup with 2 users / manual duplicates succeed / partial UNIQUE violations verified at the SQL level
- `tests/integration/test_releases.py`: replace direct `VinylRecord(...)` INSERTs with the new two-step insert
- `tests/integration/test_user_follows.py`: same as above
- `tests/unit/test_record_service.py`: rewrite all cases (create branches on spotify / manual, display_order is per user, cross-user delete/update returns 404)
- `tests/unit/test_release_service.py`: switch the `_seed_record` helper to the two-step insert
- Additional cases in `tests/integration/test_records.py`: CRUD for `record_favorite_tracks` (order preserved, cross-user isolation, `spotify_track_id` UNIQUE violation within the same collection, CASCADE on user_collection deletion)
- Additional cases in `tests/unit/test_record_service.py`: the full-replacement logic of `set_favorite_tracks`, an empty array deletes everything, `note` accepts null, multiple manual rows with NULL `spotify_track_id` can be added

---

## 4. Out of scope

- **Jacket upload** (`PUT /api/records/{id}/jacket`): not implemented until Phase B-3+. In this ADR, vinyl_records.image_url is fixed to the Spotify cover. If per-user jacket overrides are to be allowed, either add a `user_collections.custom_image_url` column or create a separate table in the future (separate ADR)
- **Catalog edits on `source='spotify'` rows**: the spec is to silently ignore them for the user. Returning an explicit 409 is an option, but it would require UI changes, so it is out of scope
- **Orphan cleanup for manual records**: left alone for now, per §2.7
- **Choosing the "primary artist" of a Spotify album**: compilations etc. where multiple artists are tied to one album are represented, as before, by a single `vinyl_records.artist_id` (the first artist from the Spotify search is used)
- **Cataloging tracks**: a separate ADR will be raised once demand where catalog sharing pays off emerges, such as "popular tracks across all users" or "Spotify Liked Songs sync". This ADR keeps `record_favorite_tracks` storing `track_name` denormalized

---

## 5. Consequences

### Positive

- Records are scoped by user_id and work safely even with multiple users registered on the Dashboard
- Spotify album dedup reduces data duplication and makes future release sync / jacket sharing easier
- Provides a foundation for growing per-user derived tables (favorite tracks, etc.) with `user_collections.id` as the FK target
- The responsibilities of catalog and ownership become clear, resolving the confusion in the edit spec (who can edit whose title)
- Implementing `record_favorite_tracks` in this ADR makes per-track search possible in the future in Phase 4 (full-text search across the whole collection / cross-tag)
- The handwritten-note metaphor of ADR-000 §F-H2, "back cover = memo + purchase info", is preserved in two tiers, `user_collections.memo` (the album as a whole) and `record_favorite_tracks.note` (per track), while introducing per-track structure

### Negative / Caveats

- The schema change is large; the migration PR is backend-only but must rewrite `model / repo / service / router / seed / all record-related tests` in one go
- The API surface is preserved, but the service layer grows slightly because a `_FlatRow` dataclass is inserted as an extra layer internally
- The catalog of `source='spotify'` rows is shared across all users, so title fixes would propagate to other users (this ADR sidesteps this by silently ignoring them)
- A hand-written migration is required (because autogenerate is unstable for partial UNIQUE INDEXes)
- The frontend has 0 changes for the catalog/ownership split (response shape preserved). Only the `record_favorite_tracks` addition introduces new UI / type additions on the frontend, and the orval diff is limited to that scope

### Migration risk

- Only now, pre-deploy, can we get away with the "DELETE existing data" approach. **This ADR's migration cannot be used after production launch**, so either merge before deploying, or a separate staged migration plan is needed if it lands after deploying

---

## 6. Implementation plan

Implement in the following order in a separate PR (separate branch from this ADR):

1. SQLModel: shrink `VinylRecord` + new `UserCollection` + new `RecordFavoriteTrack` (UNIQUE INDEX / partial INDEX made explicit in `__table_args__`)
2. Hand-written Alembic migration (DELETE → DROP COLUMNS → ADD INDEX → CREATE TABLE user_collections → CREATE TABLE record_favorite_tracks)
3. Split into 2 repositories (`RecordRepository` becomes catalog-only, new `UserCollectionRepository`; whether `RecordFavoriteTrackRepository` is new or folded into `UserCollectionRepository` is decided in the implementation phase)
4. Rewrite `RecordService` (catalog → user_collection in 1 TX, with the full-replacement logic for favorite_tracks living alongside as a `set_favorite_tracks` method)
5. Routers: `routers/records.py` keeps its surface and only swaps the internal path; `count_owned_by_artist_for_user` in `routers/user_follows.py` goes through the new repo; update the DI wiring in `routers/deps.py`. Whether to add a favorite_tracks endpoint or extend the PUT body is decided in the implementation phase
6. Swap dependencies in seed.py / release_service.py
7. Rewrite all tests (§3.5 above)
8. Regenerate OpenAPI / orval with `make spec && make gen` and check the diff
9. Update the Status of ADR-006 from `Proposed` → `Accepted`
