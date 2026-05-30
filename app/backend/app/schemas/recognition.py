"""音声認識 (AudD) の DTO (ADR-016)。

`/api/recognize` のレスポンス。録音した短いクリップを AudD に投げて得た 1 件の
マッチを、frontend の Record 追加フォームに prefill しやすい最小フィールドに正規化する。

AudD の `return=spotify` 指定で付いてくる Spotify メタ (album.id / images /
release_date / artists[].id) を使い、曲 → アルバム + Spotify アーティスト ID まで
解決する。マッチしなければ `matched=False` で他は None。
"""

from __future__ import annotations

from pydantic import BaseModel


class RecognitionResult(BaseModel):
    # マッチしたか。False の場合、以降のフィールドはすべて None。
    matched: bool = False

    # 認識した「曲」の情報 (favorite_tracks への自動挿入に使う)。
    title: str | None = None
    artist_name: str | None = None

    # 曲が属する「アルバム」の情報 (On the hunt = レコード単位なので主役)。
    album: str | None = None
    spotify_album_id: str | None = None
    image_url: str | None = None  # アルバムジャケット
    original_release_date: str | None = None

    # アーティスト解決用。DB 未在籍なら frontend が upsertArtist で追加する。
    spotify_artist_id: str | None = None
    artist_image_url: str | None = None
