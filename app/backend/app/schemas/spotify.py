from pydantic import BaseModel


class SpotifyArtistSummary(BaseModel):
    """DTO for one Spotify artist search result.

    Used when the "add follow" modal on ArtistsPage pulls candidates from
    Spotify. Exposes `spotify_id` / `name` / `image_url` so the result can be
    passed to `upsert_artist` (POST /api/artists) and `follow_artist`
    (POST /api/user-follows).
    """

    spotify_id: str
    name: str
    image_url: str | None


class SpotifyAlbumSummary(BaseModel):
    """DTO for one Spotify album search result.

    Exposes only the fields needed to insert into `vinyl_records`:
    `spotify_album_id` (= id) / `title` (= name) / `original_release_date` (= release_date)
    / `image_url` / `artist_names` for display / `primary_artist_id` for artist auto-upsert.

    `primary_artist_id` is album.artists[0].id (Spotify artist ID). When
    RecordFormModal upserts into the artists table on album selection, it
    identifies the artist by canonical Spotify ID rather than by name match.
    null only in the (very rare) case where the album has no artists.
    """

    id: str
    name: str
    release_date: str | None
    image_url: str | None
    artist_names: list[str]
    primary_artist_id: str | None
