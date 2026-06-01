import re
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from app.core.exceptions import SpotifyApiError
from app.services.spotify_app_client import SPOTIFY_TOKEN_URL, SpotifyAppClient
from tests.conftest import make_settings

_SEARCH_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/search")
_ARTISTS_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/artists")
_ARTIST_ALBUMS_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/artists/[^/]+/albums")


def _token_response(expires_in: int = 3600) -> dict[str, Any]:
    return {
        "access_token": "BQA-app-token",
        "token_type": "Bearer",
        "expires_in": expires_in,
    }


def _search_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"albums": {"items": items, "total": len(items), "limit": 20, "offset": 0}}


def _album(
    id_: str = "spot-album-1",
    name: str = "Kind of Blue",
    release_date: str | None = "1959-08-17",
    image_url: str | None = "https://i.scdn.co/image/kind-of-blue.jpg",
    artist_names: tuple[str, ...] = ("Miles Davis",),
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "release_date": release_date,
        "images": [{"url": image_url, "width": 640, "height": 640}] if image_url else [],
        "artists": [{"id": f"art-{i}", "name": n} for i, n in enumerate(artist_names)],
    }


def _make_client() -> SpotifyAppClient:
    return SpotifyAppClient(make_settings())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """テスト中は throttle / Retry-After の実スリープを無効化して高速化する。"""
    monkeypatch.setattr("app.services.spotify_app_client.time.sleep", lambda _seconds: None)


def test_search_returns_mapped_albums(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN, method="GET", json=_search_response([_album()])
    )

    items = _make_client().search_albums("Kind of Blue")

    assert len(items) == 1
    a = items[0]
    assert a.id == "spot-album-1"
    assert a.name == "Kind of Blue"
    assert a.release_date == "1959-08-17"
    assert a.image_url == "https://i.scdn.co/image/kind-of-blue.jpg"
    assert a.artist_names == ["Miles Davis"]
    assert a.primary_artist_id == "art-0"


def test_empty_query_skips_network(httpx_mock: HTTPXMock) -> None:
    # httpx_mock would raise on any unexpected request if we set strict mode,
    # but pytest-httpx by default also asserts at teardown that mocks were used.
    # Here we register none and rely on "no requests dispatched" being the success signal.
    items = _make_client().search_albums("   ")
    assert items == []


def test_search_returns_empty_on_zero_results(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", json=_search_response([]))

    assert _make_client().search_albums("nonsense xyzzy") == []


def test_artist_parameter_is_added_to_query(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN, method="GET", json=_search_response([_album()])
    )

    _make_client().search_albums("Kind of Blue", artist="Miles Davis")

    requests = [r for r in httpx_mock.get_requests() if r.url.path == "/v1/search"]
    assert len(requests) == 1
    q_param = requests[0].url.params.get("q")
    assert q_param is not None
    assert "Kind of Blue" in q_param
    assert 'artist:"Miles Davis"' in q_param


def test_429_raises_with_status_code(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", status_code=429)

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().search_albums("anything")
    assert exc_info.value.status_code == 429


def test_500_raises_with_status_code(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", status_code=500)

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().search_albums("anything")
    assert exc_info.value.status_code == 500


def test_token_endpoint_400_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=SPOTIFY_TOKEN_URL,
        method="POST",
        status_code=400,
        json={"error": "invalid_client"},
    )

    with pytest.raises(SpotifyApiError):
        _make_client().search_albums("anything")


def test_token_is_cached_across_searches(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN, method="GET", json=_search_response([_album()])
    )
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN, method="GET", json=_search_response([_album()])
    )

    client = _make_client()
    client.search_albums("first")
    client.search_albums("second")

    token_requests = [r for r in httpx_mock.get_requests() if r.url.path == "/api/token"]
    search_requests = [r for r in httpx_mock.get_requests() if r.url.path == "/v1/search"]
    assert len(token_requests) == 1
    assert len(search_requests) == 2


def test_album_without_images_returns_null_image_url(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN,
        method="GET",
        json=_search_response([_album(image_url=None)]),
    )

    items = _make_client().search_albums("anything")
    assert items[0].image_url is None


# ---- get_artists_images ----
# 実装は `GET /v1/artists/{id}` を 1 id ずつ叩くループ (batch endpoint
# `GET /v1/artists?ids=...` は Spotify Development Mode app だと 403 を返す
# ため。詳細は spotify_app_client.py の get_artists_images docstring 参照)。


def _single_artist_response(
    id_: str = "art-1",
    image_url: str | None = "https://i.scdn.co/image/art1.jpg",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": "Some Artist",
        "images": [{"url": image_url, "width": 640, "height": 640}] if image_url else [],
    }


def test_get_artists_images_returns_first_image(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-1",
        method="GET",
        json=_single_artist_response("art-1"),
    )
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-2",
        method="GET",
        json=_single_artist_response("art-2", image_url=None),
    )

    result = _make_client().get_artists_images(["art-1", "art-2"])

    assert result == {
        "art-1": "https://i.scdn.co/image/art1.jpg",
        "art-2": None,
    }


def test_get_artists_images_empty_input_skips_network(httpx_mock: HTTPXMock) -> None:
    # 空入力ではトークン / artist endpoint いずれも叩かない。
    assert _make_client().get_artists_images([]) == {}


def test_get_artists_images_dedupes_input(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-1",
        method="GET",
        json=_single_artist_response("art-1"),
    )

    _make_client().get_artists_images(["art-1", "art-1", ""])

    # art-1 は 1 回しか叩かれない (dedup) + 空文字は捨てる。
    artist_reqs = [r for r in httpx_mock.get_requests() if "/v1/artists/" in r.url.path]
    assert len(artist_reqs) == 1


def test_get_artists_images_loops_per_id(httpx_mock: HTTPXMock) -> None:
    """51 ids 投入 → 51 リクエスト (単発ループ)。batch 化はしない。"""
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    ids = [f"art-{i}" for i in range(51)]
    for aid in ids:
        httpx_mock.add_response(
            url=f"https://api.spotify.com/v1/artists/{aid}",
            method="GET",
            json=_single_artist_response(aid),
        )

    result = _make_client().get_artists_images(ids)

    artist_reqs = [r for r in httpx_mock.get_requests() if "/v1/artists/" in r.url.path]
    assert len(artist_reqs) == 51
    assert len(result) == 51


def test_get_artists_images_skips_404(httpx_mock: HTTPXMock) -> None:
    """invalid ID は 404 で skip、他は継続。"""
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-1",
        method="GET",
        json=_single_artist_response("art-1"),
    )
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/bogus",
        method="GET",
        status_code=404,
    )

    result = _make_client().get_artists_images(["art-1", "bogus"])

    assert result == {"art-1": "https://i.scdn.co/image/art1.jpg"}


def test_get_artists_images_429_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-1", method="GET", status_code=429
    )

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().get_artists_images(["art-1"])
    assert exc_info.value.status_code == 429


# ---- get_artist_albums ----


def _album_ingest(
    id_: str = "alb-1",
    name: str = "Some Album",
    album_type: str = "album",
    release_date: str = "2026-01-15",
    release_date_precision: str = "day",
    image_url: str | None = "https://i.scdn.co/image/alb1.jpg",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "album_type": album_type,
        "release_date": release_date,
        "release_date_precision": release_date_precision,
        "images": [{"url": image_url, "width": 640, "height": 640}] if image_url else [],
    }


def _albums_page(items: list[dict[str, Any]]) -> dict[str, Any]:
    # /v1/artists/{id}/albums の limit は Spotify 公式仕様で max 10。
    return {"items": items, "limit": 10, "offset": 0, "total": len(items)}


def test_get_artist_albums_basic_200(httpx_mock: HTTPXMock) -> None:
    from datetime import date

    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page([_album_ingest()]),
    )

    items = _make_client().get_artist_albums("art-1")

    assert len(items) == 1
    a = items[0]
    assert a.id == "alb-1"
    assert a.name == "Some Album"
    assert a.album_type == "album"
    assert a.release_date == date(2026, 1, 15)
    assert a.image_url == "https://i.scdn.co/image/alb1.jpg"
    assert a.artist_id == "art-1"


def test_get_artist_albums_paginates_at_page_limit(httpx_mock: HTTPXMock) -> None:
    """このエンドポイントの limit は Spotify 公式仕様で max 10。

    1 ページ目を 10 件返した場合のみ次ページを取りに行き、未満なら終端する。
    """
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    # 1 ページ目 10 件 (limit と一致 → 次ページへ)
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json={
            "items": [_album_ingest(id_=f"alb-{i}") for i in range(10)],
            "limit": 10,
            "offset": 0,
            "total": 11,
        },
    )
    # 2 ページ目 1 件 (limit 未満 → 終端)
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json={
            "items": [_album_ingest(id_="alb-10")],
            "limit": 10,
            "offset": 10,
            "total": 11,
        },
    )

    items = _make_client().get_artist_albums("art-1")

    assert len(items) == 11
    album_reqs = [r for r in httpx_mock.get_requests() if "/albums" in r.url.path]
    assert len(album_reqs) == 2
    assert album_reqs[0].url.params.get("offset") == "0"
    assert album_reqs[1].url.params.get("offset") == "10"
    # limit が正しく渡されていることも確認 (Spotify が拒否する 50 等を送らないこと)
    assert album_reqs[0].url.params.get("limit") == "10"


def test_get_artist_albums_applies_since_date_cutoff(httpx_mock: HTTPXMock) -> None:
    from datetime import date

    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page(
            [
                _album_ingest(id_="old", release_date="2020-01-01"),
                _album_ingest(id_="new", release_date="2026-01-15"),
            ]
        ),
    )

    items = _make_client().get_artist_albums("art-1", since_date=date(2025, 1, 1))

    assert {i.id for i in items} == {"new"}


def test_get_artist_albums_applies_until_date_cutoff(httpx_mock: HTTPXMock) -> None:
    from datetime import date

    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page(
            [
                _album_ingest(id_="ok", release_date="2026-01-15"),
                _album_ingest(id_="future", release_date="2099-12-31"),
            ]
        ),
    )

    items = _make_client().get_artist_albums("art-1", until_date=date(2030, 1, 1))

    assert {i.id for i in items} == {"ok"}


def test_get_artist_albums_normalizes_year_and_month_precision(
    httpx_mock: HTTPXMock,
) -> None:
    """`release_date_precision=year` は YYYY-01-01、`month` は YYYY-MM-01 に丸める。"""
    from datetime import date

    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page(
            [
                _album_ingest(
                    id_="y",
                    release_date="1959",
                    release_date_precision="year",
                ),
                _album_ingest(
                    id_="m",
                    release_date="1962-08",
                    release_date_precision="month",
                ),
            ]
        ),
    )

    items = _make_client().get_artist_albums("art-1")

    by_id = {i.id: i for i in items}
    assert by_id["y"].release_date == date(1959, 1, 1)
    assert by_id["m"].release_date == date(1962, 8, 1)


def test_get_artist_albums_skips_unparseable_release_date(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page(
            [
                _album_ingest(id_="ok"),
                _album_ingest(id_="bad", release_date="not-a-date"),
            ]
        ),
    )

    items = _make_client().get_artist_albums("art-1")

    assert {i.id for i in items} == {"ok"}


def test_get_artist_albums_filters_unexpected_album_type(
    httpx_mock: HTTPXMock,
) -> None:
    """include_groups=album,single で叩いてるが、Spotify が compilation を混ぜて
    返すケースに備えてクライアント側でも弾く (定義的な防御)。"""
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page(
            [
                _album_ingest(id_="alb", album_type="album"),
                _album_ingest(id_="comp", album_type="compilation"),
            ]
        ),
    )

    items = _make_client().get_artist_albums("art-1")

    assert {i.id for i in items} == {"alb"}


def test_get_artist_albums_passes_include_groups_and_market(
    httpx_mock: HTTPXMock,
) -> None:
    """include_groups は album,single 固定、market は US 固定で叩く。

    market を渡さないと Spotify が同一アルバムをリージョン別に重複返却して
    リリース件数が膨張するため market は指定する。値は US (ジャズは US 先行 /
    輸入盤主体で JP 配信が遅れる盤が多く、JP だと Feed への登場が遅れるため)。
    """
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page([_album_ingest()]),
    )

    _make_client().get_artist_albums("art-1")

    album_reqs = [r for r in httpx_mock.get_requests() if "/albums" in r.url.path]
    assert album_reqs[0].url.params.get("include_groups") == "album,single"
    assert album_reqs[0].url.params.get("market") == "US"


def test_get_artist_albums_429_raises_after_retry_exhausted(httpx_mock: HTTPXMock) -> None:
    """429 は Retry-After を見て 1 回リトライする。再送後もなお 429 なら 429 を上げる。

    リトライ後も埋まらない window は呼び出し元 (release sync) が残りアーティストを
    次回送りにする材料にする。
    """
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    # 1 回目 + Retry-After リトライの計 2 回とも 429。
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=429, headers={"Retry-After": "1"}
    )
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=429, headers={"Retry-After": "1"}
    )

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().get_artist_albums("art-1")
    assert exc_info.value.status_code == 429
    album_reqs = [r for r in httpx_mock.get_requests() if "/albums" in r.url.path]
    assert len(album_reqs) == 2


def test_get_artist_albums_retries_once_on_429_then_succeeds(httpx_mock: HTTPXMock) -> None:
    """429 を 1 回踏んでも Retry-After 待ち後の再送が 200 なら結果を返す。"""
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=429, headers={"Retry-After": "1"}
    )
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", json=_albums_page([_album_ingest()])
    )

    items = _make_client().get_artist_albums("art-1")

    assert {i.id for i in items} == {"alb-1"}
    album_reqs = [r for r in httpx_mock.get_requests() if "/albums" in r.url.path]
    assert len(album_reqs) == 2


def test_get_artist_albums_404_returns_empty_not_raise(httpx_mock: HTTPXMock) -> None:
    """404 は invalid artist_id / market 該当無しの両方で起こりうるので空配列で抜ける。

    sync 全体を「全件失敗」にせず、他のアーティストの ingest を続行できるよう
    にするための防御的挙動 (実際に backend ログで `artist_id=7HRgLn... 404` が
    観測されたので追加)。
    """
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=404)

    result = _make_client().get_artist_albums("art-bogus")

    assert result == []


def test_get_artist_albums_500_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=500)

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().get_artist_albums("art-1")
    assert exc_info.value.status_code == 500
