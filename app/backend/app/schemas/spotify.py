from pydantic import BaseModel


class SpotifyAlbumSummary(BaseModel):
    """Spotify album search 結果の 1 件を表す DTO。

    `vinyl_records` への投入で必要なフィールドだけを露出する:
    `spotify_album_id` (= id) / `title` (= name) / `original_release_date` (= release_date)
    / `image_url` / 表示用の `artist_names`。
    """

    id: str
    name: str
    release_date: str | None
    image_url: str | None
    artist_names: list[str]
