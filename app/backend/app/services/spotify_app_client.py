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
from app.schemas.spotify import SpotifyAlbumSummary, SpotifyArtistSummary

logger = logging.getLogger("uvicorn.error")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_ARTIST_URL_TEMPLATE = "https://api.spotify.com/v1/artists/{id}"
SPOTIFY_ARTIST_ALBUMS_URL_TEMPLATE = "https://api.spotify.com/v1/artists/{id}/albums"

_TOKEN_EXPIRY_MARGIN_SECONDS = 60
# GET /v1/artists/{id}/albums の 1 ページ最大件数。Spotify 公式仕様で
# このエンドポイントだけ上限 10 (default 5)。他の Spotify endpoint は 50 まで
# 行けるが、ここで 50 を渡すと 400 "Invalid limit" が返るので注意。
_ARTIST_ALBUMS_PAGE_LIMIT = 10
# Phase B-3 では album / single のみ ingest する (ADR-000 §45 / §220)。
# compilation や appears_on は将来必要になったら別ジョブで取る。
_ARTIST_ALBUMS_INCLUDE_GROUPS = "album,single"
# /v1/artists/{id}/albums は market 無しだと同一アルバムを 30+ リージョン別に
# 重複返却する (Spotify 公式仕様、"If neither market or user country are
# provided, the content is considered unavailable for the client")。なので
# market は指定して dedup を効かせる。
#
# 値は US。当初 JP にしていたが、ジャズは US 先行リリース / 輸入盤主体で、JP
# 配信が遅れる (or 来ない) 盤が多い。market=JP だと「US では既発売だが JP 未配信」
# のアルバムが available_markets から外れて items に出ず、Feed への登場が実発売
# から大きく遅れていた (実例: Avishai Cohen "Eternal Child" が JP 配信後に初出)。
# US に寄せることで輸入盤ジャズを最速で拾う。トレードオフとして JP 限定配信の
# 邦楽ジャズ等は取りこぼしうる。将来マルチユーザ化したら users.country を見るのが正道。
_ARTIST_ALBUMS_MARKET = "US"

# release sync (Get Artist's Albums) 専用のレート制限対策パラメータ。
# sync は POST リクエスト同期実行なので、待ち時間がそのままレスポンス時間に
# なる点に注意 (大きくしすぎない)。対話的な search 系には適用しない。
#
# RELEASE_SYNC_THROTTLE_SECONDS:
#   連続する Spotify リクエスト (ページ間は client 側 / アーティスト間は
#   release_service 側) に挟む最小スリープ。間隔ゼロの連射で rolling ~30s
#   window を一気に使い切って 429 を踏むのを防ぐ。
# _RATE_LIMIT_MAX_RETRIES:
#   429 を踏んだとき Retry-After を見て待ってから同一リクエストを再送する最大回数。
# _RATE_LIMIT_DEFAULT_WAIT_SECONDS / _RATE_LIMIT_MAX_WAIT_SECONDS:
#   Retry-After が無い / 不正なときのフォールバック秒と、過大値の頭打ち上限
#   (同期リクエストを長時間ブロックしないため)。
RELEASE_SYNC_THROTTLE_SECONDS = 0.2
_RATE_LIMIT_MAX_RETRIES = 1
_RATE_LIMIT_DEFAULT_WAIT_SECONDS = 2.0
_RATE_LIMIT_MAX_WAIT_SECONDS = 30.0


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

    def search_artists(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SpotifyArtistSummary]:
        """`GET /v1/search?type=artist` を叩いて候補一覧を返す。

        ArtistsPage のフォロー追加モーダル用。`search_albums` と違って
        artist 名で直接ヒットさせるだけなので field-filter は重ねない。
        """
        if not query.strip():
            return []
        token = self._get_app_token()
        q = query.strip()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    SPOTIFY_SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": q, "type": "artist", "limit": limit},
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
                "spotify artist search returned %s q=%r error=%s",
                res.status_code,
                q,
                err_detail,
            )
            raise SpotifyApiError(
                f"spotify artist search returned {res.status_code}",
                status_code=res.status_code,
            )
        payload = res.json()
        items = (payload.get("artists") or {}).get("items") or []
        return [_to_artist_summary(item) for item in items if item.get("id") and item.get("name")]

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
        """各アーティストの画像 URL をまとめて取って `{ spotify_id: url or None }` を返す。

        実装は `GET /v1/artists/{id}` を id ごとに 1 回ずつ叩く形にしてある。
        batch 版 (`GET /v1/artists?ids=...`) は Spotify 公式 doc 上は app token
        で叩ける建付けだが、2024 年の API restriction (Development Mode の
        Spotify app) で 403 Forbidden を返してくる。単一取得 (`/v1/artists/{id}`)
        は引き続き許可されているので、確実に動くこちらを採用する。Extended
        Quota Mode を取れたら batch に戻して N 倍速くできる余地あり。

        404 (artist_id が Spotify 上に存在しない) は warn ログを残してその id
        だけスキップする。同じバッチ内の他の id は影響を受けない。
        """
        deduped = [i for i in dict.fromkeys(ids) if i]
        if not deduped:
            return {}
        token = self._get_app_token()
        result: dict[str, str | None] = {}
        for artist_id in deduped:
            url = SPOTIFY_ARTIST_URL_TEMPLATE.format(id=artist_id)
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(url, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as exc:
                raise SpotifyApiError("failed to reach Spotify artist endpoint") from exc
            if res.status_code == 429:
                raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
            if res.status_code == 404:
                # 不正な ID は単一取得だけスキップして他の id 処理を継続する。
                logger.warning(
                    "spotify artist 404 artist_id=%s — skipping in image hydration",
                    artist_id,
                )
                continue
            if res.status_code != 200:
                try:
                    err_body = res.json()
                    err_detail = err_body.get("error")
                except ValueError:
                    err_detail = None
                logger.warning(
                    "spotify artist endpoint returned %s artist_id=%s error=%s",
                    res.status_code,
                    artist_id,
                    err_detail,
                )
                raise SpotifyApiError(
                    f"spotify artist endpoint returned {res.status_code}",
                    status_code=res.status_code,
                )
            entry = res.json() or {}
            entry_id = entry.get("id")
            if not entry_id:
                continue
            images = entry.get("images") or []
            image_url = images[0].get("url") if images else None
            result[entry_id] = image_url
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
            res = self._get_albums_page(token, url, offset, artist_id)
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
            # 次ページを取りに行く前にスロットル。連続ページングで rate limit
            # window を一気に消費しないため (アーティスト間の pacing は
            # release_service 側で別途入れる)。
            time.sleep(RELEASE_SYNC_THROTTLE_SECONDS)
        return results

    def _get_albums_page(self, token: str, url: str, offset: int, artist_id: str) -> httpx.Response:
        """Get Artist's Albums を 1 ページ分 GET する (429 リトライ込み)。

        429 を踏んだら `Retry-After` を見てその秒数だけ待ち、最大
        `_RATE_LIMIT_MAX_RETRIES` 回まで同一リクエストを再送する。Spotify の
        rate limit は rolling ~30s window なので、Retry-After 秒待てば window が
        空く。再送し切ってもなお 429 のままなら 429 を上げ、呼び出し元
        (release_service の sync ループ) が残りアーティストを次回送りにする。
        404 / その他ステータスは判定を呼び出し元に委ねるためそのまま返す。
        """
        attempt = 0
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
            if res.status_code != 429:
                return res
            if attempt >= _RATE_LIMIT_MAX_RETRIES:
                raise SpotifyApiError("spotify rate limit exceeded", status_code=429)
            wait = _parse_retry_after(res.headers.get("Retry-After"))
            logger.warning(
                "spotify artist albums 429 artist_id=%s offset=%d; "
                "waiting %.1fs then retrying (attempt %d/%d)",
                artist_id,
                offset,
                wait,
                attempt + 1,
                _RATE_LIMIT_MAX_RETRIES,
            )
            time.sleep(wait)
            attempt += 1

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


def _parse_retry_after(value: str | None) -> float:
    """Spotify の `Retry-After` レスポンスヘッダ (秒数) を待機秒に変換する。

    欠落 / パース不能 / 負値なら `_RATE_LIMIT_DEFAULT_WAIT_SECONDS` に
    フォールバックし、過大値は `_RATE_LIMIT_MAX_WAIT_SECONDS` で頭打ちにして
    同期リクエストを長時間ブロックしないようにする。
    """
    if value is None:
        return _RATE_LIMIT_DEFAULT_WAIT_SECONDS
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _RATE_LIMIT_DEFAULT_WAIT_SECONDS
    if seconds < 0:
        return _RATE_LIMIT_DEFAULT_WAIT_SECONDS
    return min(seconds, _RATE_LIMIT_MAX_WAIT_SECONDS)


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


def _to_artist_summary(item: dict) -> SpotifyArtistSummary:
    images = item.get("images") or []
    image_url = images[0].get("url") if images else None
    return SpotifyArtistSummary(
        spotify_id=item["id"],
        name=item["name"],
        image_url=image_url,
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
