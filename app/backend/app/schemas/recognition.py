"""DTOs for audio recognition via AudD (ADR-016).

Response of `/api/recognize`. Normalizes the single match AudD returns for a
short recorded clip into the minimal set of fields the frontend needs to
prefill the add-record form.

Uses the Spotify metadata attached when AudD is called with `return=spotify`
(album.id / images / release_date / artists[].id) to resolve track → album +
Spotify artist ID. When nothing matched, `matched=False` and everything else is
None.
"""

from __future__ import annotations

from pydantic import BaseModel


class RecognitionResult(BaseModel):
    # Whether a match was found. If False, all remaining fields are None.
    matched: bool = False

    # The recognized track (used to auto-insert into favorite_tracks).
    title: str | None = None
    artist_name: str | None = None

    # The album the track belongs to (the main subject: On the hunt is per record).
    album: str | None = None
    spotify_album_id: str | None = None
    image_url: str | None = None  # album cover art
    original_release_date: str | None = None

    # For artist resolution. If not yet in the DB, the frontend adds it via upsertArtist.
    spotify_artist_id: str | None = None
    artist_image_url: str | None = None
