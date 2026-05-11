"""Spotify Web API を app token (Client Credentials Flow) で叩くクライアント。

`spotify_oauth_client.SpotifyOAuthClient` は user OAuth (Authorization Code Flow)
専用で、ユーザのプロフィールやフォロー情報など user-scoped なエンドポイントに使う。
一方アルバム検索など public な参照系は user token を使う必要がなく、app token
(Client Credentials) で十分。クライアントを分けることで、user scope の access_token を
処理する DB ロジック (refresh / 暗号化) を public 参照経路に持ち込まないようにする。

設計詳細:
- access_token は in-memory にキャッシュし、`expires_in` から margin (60s) を引いた
  時刻で再取得する。Web API の rate limit / latency 両方を削るための定石。
- sync (`httpx.Client`) で揃える (`spotify_oauth_client` と同じ理由)。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date

import httpx

from app.core.exceptions import SpotifyApiError
from app.core.settings import Settings
from app.schemas.spotify import SpotifyAlbumSummary

logger = logging.getLogger("uvicorn.error")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTISTS_URL = "https://api.spotify.com/v1/artists"
SPOTIFY_ARTIST_ALBUMS_URL_TEMPLATE = "https://api.spotify.com/v1/artists/{id}/albums"

_TOKEN_EXPIRY_MARGIN_SECONDS = 60
# GET /v1/artists?ids=... の上限。Spotify 公式仕様。
_ARTISTS_BATCH_LIMIT = 50
# GET /v1/artists/{id}/albums の 1 ページ最大件数。Spotify 公式仕様で
# このエンドポイントだけ上限 10 (default 5)。他の Spotify endpoint は 50 まで
# 行けるが、ここで 50 を渡すと 400 "Invalid limit" が返るので注意。
_ARTIST_ALBUMS_PAGE_LIMIT = 10
# Phase B-3 では album / single のみ ingest する (ADR-000 §45 / §220)。
# compilation や appears_on は将来必要になったら別ジョブで取る。
_ARTIST_ALBUMS_INCLUDE_GROUPS = "album,single"
# /v1/artists/{id}/albums は market 無しだと同一アルバムを 30+ リージョン別に
# 重複返却する (Spotify 公式仕様、"If neither market or user country are
# provided, the content is considered unavailable for the client")。
# 日本ジャズリスナー向けアプリなので JP に固定して dedup を効かせる。
# 将来マルチユーザ化したら users.country を見るのが正道。
_ARTIST_ALBUMS_MARKET = "JP"


@dataclass(frozen=True)
class SpotifyAlbumIngest:
    """Get Artist's Albums のレコード ingest 用に dataclass を分けて持つ。

    `SpotifyAlbumSummary` は検索 UI に直接見せる schema (Pydantic) で、
    こちらは内部 ingest 専用の純データ。`release_date` を date に正規化済み
    である点と、`artist_id` (このアルバムを所有する artist の Spotify ID) を
    呼び出し側に返してリポジトリ書き込みに使えるようにしている点が違う。
    """

    id: str
    name: str
    album_type: str
    release_date: date
    image_url: str | None
    artist_id: str


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # epoch seconds


class SpotifyAppClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cached: _CachedToken | None = None

    def search_albums(
        self,
        query: str,
        artist: str | None = None,
        limit: int = 20,
    ) -> list[SpotifyAlbumSummary]:
        if not query.strip():
            return []
        token = self._get_app_token()
        # type=album で既に album 種別に絞っているので、追加で `album:` field-filter を
        # 重ねると Spotify が 400 を返すことがある。クエリ本体はそのまま渡し、artist
        # のみ field filter で絞り込む。
        q = query.strip()
        if artist:
            q += f' artist:"{artist}"'
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    SPOTIFY_SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": q, "type": "album", "limit": limit},
                )
        except httpx.HTTPError as exc:
            raise SpotifyApiError("failed to reach Spotify search endpoint") from exc
        if res.status_code == 429:
            raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
        if res.status_code != 200:
            try:
                err_body = res.json()
                err_detail = err_body.get("error")
            except ValueError:
                err_detail = None
            logger.warning(
                "spotify search returned %s q=%r error=%s",
                res.status_code,
                q,
                err_detail,
            )
            raise SpotifyApiError(
                f"spotify search returned {res.status_code}",
                status_code=res.status_code,
            )
        payload = res.json()
        items = (payload.get("albums") or {}).get("items") or []
        return [_to_summary(item) for item in items]

    def get_artists_images(self, ids: list[str]) -> dict[str, str | None]:
        """`GET /v1/artists?ids=...` で複数アーティストの画像 URL をまとめて取る。

        Spotify は一度に 50 件まで受け付けるので超える場合はチャンク分割する。
        戻り値は `{ spotify_id: image_url or None }`。Spotify から `null`
        (ID 不正) が返ったエントリや、`images` が空のアーティストは `None`
        を入れて返し、呼び出し側で「未取得」と「画像なし」を区別する必要は
        生じないようにする (どちらも DB 上は image_url=None のまま据え置きで
        良い)。
        """
        deduped = [i for i in dict.fromkeys(ids) if i]
        if not deduped:
            return {}
        token = self._get_app_token()
        result: dict[str, str | None] = {}
        for start in range(0, len(deduped), _ARTISTS_BATCH_LIMIT):
            chunk = deduped[start : start + _ARTISTS_BATCH_LIMIT]
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(
                        SPOTIFY_ARTISTS_URL,
                        headers={"Authorization": f"Bearer {token}"},
                        params={"ids": ",".join(chunk)},
                    )
            except httpx.HTTPError as exc:
                raise SpotifyApiError("failed to reach Spotify artists endpoint") from exc
            if res.status_code == 429:
                raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
            if res.status_code != 200:
                try:
                    err_body = res.json()
                    err_detail = err_body.get("error")
                except ValueError:
                    err_detail = None
                logger.warning(
                    "spotify artists endpoint returned %s ids=%d error=%s",
                    res.status_code,
                    len(chunk),
                    err_detail,
                )
                raise SpotifyApiError(
                    f"spotify artists endpoint returned {res.status_code}",
                    status_code=res.status_code,
                )
            payload = res.json()
            entries = payload.get("artists") or []
            for entry in entries:
                if not entry:
                    # Spotify は ID 不正時に null を返す。呼び出し側がチャンクに
                    # 入れた順序は保てないので、id 取り出しは entry["id"] に頼る。
                    continue
                artist_id = entry.get("id")
                if not artist_id:
                    continue
                images = entry.get("images") or []
                image_url = images[0].get("url") if images else None
                result[artist_id] = image_url
        return result

    def get_artist_albums(
        self,
        artist_id: str,
        since_date: date | None = None,
        until_date: date | None = None,
    ) -> list[SpotifyAlbumIngest]:
        """`GET /v1/artists/{id}/albums` で release ingest 用にアルバム一覧を取る。

        - `include_groups=album,single` 固定 (Phase B-3 では compilation /
          appears_on は ingest しない、ADR-000 §45 / §220)。
        - pagination は `offset` 加算で完走する (Spotify 側にフィルタ機能が
          無いので「since_date より古い」「until_date より新しい」アルバムは
          クライアント側で捨てる)。
        - `release_date_precision` が `year` の場合は `YYYY-01-01`、`month`
          の場合は `YYYY-MM-01` に正規化して `date` 型にする。precision を
          捨てるので「年だけ分かってる古いアルバム」は 1/1 として扱われるが、
          Feed の対象窓 (本日 ± 数百日) には影響しない。
        - `release_date` パース不能なアルバムは warn ログを残して読み飛ばす。
        """
        token = self._get_app_token()
        results: list[SpotifyAlbumIngest] = []
        url = SPOTIFY_ARTIST_ALBUMS_URL_TEMPLATE.format(id=artist_id)
        offset = 0
        while True:
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(
                        url,
                        headers={"Authorization": f"Bearer {token}"},
                        params={
                            "include_groups": _ARTIST_ALBUMS_INCLUDE_GROUPS,
                            "limit": _ARTIST_ALBUMS_PAGE_LIMIT,
                            "offset": offset,
                            "market": _ARTIST_ALBUMS_MARKET,
                        },
                    )
            except httpx.HTTPError as exc:
                raise SpotifyApiError("failed to reach Spotify artist albums endpoint") from exc
            if res.status_code == 429:
                raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
            if res.status_code == 404:
                # 404 は「invalid artist_id」または「指定 market に該当コンテンツ無し」の
                # 両方で起こる (Spotify 公式仕様)。どちらでもユーザにとっての結果は
                # 同じ「このアーティストから新譜なし」なので、sync 全体を失敗扱いに
                # せず空配列で抜ける。warn ログだけ残して seed や user_follows 側で
                # ID を直す材料にする。
                logger.warning(
                    "spotify artist albums 404 artist_id=%s (bad id or no market content) — skip",
                    artist_id,
                )
                return []
            if res.status_code != 200:
                try:
                    err_body = res.json()
                    err_detail = err_body.get("error")
                except ValueError:
                    err_detail = None
                logger.warning(
                    "spotify artist albums returned %s artist_id=%s offset=%d error=%s",
                    res.status_code,
                    artist_id,
                    offset,
                    err_detail,
                )
                raise SpotifyApiError(
                    f"spotify artist albums returned {res.status_code}",
                    status_code=res.status_code,
                )
            payload = res.json()
            items = payload.get("items") or []
            for item in items:
                parsed = _parse_ingest(item, artist_id)
                if parsed is None:
                    continue
                if since_date is not None and parsed.release_date < since_date:
                    continue
                if until_date is not None and parsed.release_date > until_date:
                    continue
                results.append(parsed)
            # Spotify は `next` を返すが、件数管理は offset 自走で十分。
            # items が空 or limit 未満なら終端。
            if len(items) < _ARTIST_ALBUMS_PAGE_LIMIT:
                break
            offset += _ARTIST_ALBUMS_PAGE_LIMIT
        return results

    def _get_app_token(self) -> str:
        cached = self._cached
        if cached is not None and cached.expires_at > time.time():
            return cached.access_token
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    SPOTIFY_TOKEN_URL,
                    data={"grant_type": "client_credentials"},
                    auth=(
                        self._settings.spotify_client_id,
                        self._settings.spotify_client_secret,
                    ),
                )
        except httpx.HTTPError as exc:
            raise SpotifyApiError("failed to reach Spotify token endpoint") from exc
        if res.status_code != 200:
            try:
                err_body = res.json()
                err_code = err_body.get("error")
            except ValueError:
                err_code = None
            logger.warning(
                "spotify app-token endpoint returned %s error=%s",
                res.status_code,
                err_code,
            )
            raise SpotifyApiError(
                f"spotify app-token endpoint returned {res.status_code}",
                status_code=res.status_code,
            )
        payload = res.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not access_token or expires_in <= 0:
            raise SpotifyApiError("spotify app-token response missing fields")
        self._cached = _CachedToken(
            access_token=access_token,
            expires_at=time.time() + expires_in - _TOKEN_EXPIRY_MARGIN_SECONDS,
        )
        return access_token


def _parse_release_date(value: str, precision: str | None) -> date | None:
    """Spotify の `release_date` (`release_date_precision` 付き) を `date` に正規化する。

    Spotify は precision に応じて短縮形を返す:
    - `day` → `"1959-08-17"`
    - `month` → `"1959-08"` → `1959-08-01` に丸める
    - `year` → `"1959"` → `1959-01-01` に丸める
    どちらの precision も丸めるので「正確な発売日」より「Feed の窓に入るか」
    を判定する目的でのみ使う前提。
    """
    if not value:
        return None
    try:
        if precision == "year" or len(value) == 4:
            return date(int(value), 1, 1)
        if precision == "month" or len(value) == 7:
            year, month = value.split("-")
            return date(int(year), int(month), 1)
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_ingest(item: dict, artist_id: str) -> SpotifyAlbumIngest | None:
    """Get Artist's Albums のレスポンス 1 件を `SpotifyAlbumIngest` に詰める。

    `release_date` パース失敗 / id 欠落のアルバムは None を返して呼び出し側で
    捨てる。仕様外データで sync 全体を落とさないための防御。
    """
    album_id = item.get("id")
    name = item.get("name")
    album_type = item.get("album_type")
    if not album_id or not name or album_type not in {"album", "single"}:
        return None
    release_date = _parse_release_date(
        item.get("release_date") or "", item.get("release_date_precision")
    )
    if release_date is None:
        logger.warning(
            "spotify artist albums: skipping album with unparseable release_date album_id=%s",
            album_id,
        )
        return None
    images = item.get("images") or []
    image_url = images[0].get("url") if images else None
    return SpotifyAlbumIngest(
        id=album_id,
        name=name,
        album_type=album_type,
        release_date=release_date,
        image_url=image_url,
        artist_id=artist_id,
    )


def _to_summary(item: dict) -> SpotifyAlbumSummary:
    images = item.get("images") or []
    image_url = images[0].get("url") if images else None
    artists = item.get("artists") or []
    primary_artist_id = artists[0].get("id") if artists else None
    return SpotifyAlbumSummary(
        id=item.get("id") or "",
        name=item.get("name") or "",
        release_date=item.get("release_date"),
        image_url=image_url,
        artist_names=[a.get("name") for a in artists if a.get("name")],
        primary_artist_id=primary_artist_id,
    )
