from pydantic import BaseModel


class SpotifyAlbumSummary(BaseModel):
    """Spotify album search 結果の 1 件を表す DTO。

    `vinyl_records` への投入で必要なフィールドだけを露出する:
    `spotify_album_id` (= id) / `title` (= name) / `original_release_date` (= release_date)
    / `image_url` / 表示用の `artist_names` / artist auto-upsert 用の `primary_artist_id`。

    `primary_artist_id` は album.artists[0].id (Spotify artist ID)。RecordFormModal が
    album 選択時に artists テーブルへ upsert する際、name 一致ではなく Spotify 正規 ID で
    識別するために用いる。album に artists が無いケース (極めて稀) のみ null。
    """

    id: str
    name: str
    release_date: str | None
    image_url: str | None
    artist_names: list[str]
    primary_artist_id: str | None
