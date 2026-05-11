import re
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from app.core.exceptions import SpotifyApiError
from app.services.spotify_app_client import SPOTIFY_TOKEN_URL, SpotifyAppClient
from tests.conftest import make_settings

_SEARCH_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/search")
_ARTISTS_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/artists")


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


def _artists_response(entries: list[dict[str, Any] | None]) -> dict[str, Any]:
    return {"artists": entries}


def _artist_entry(
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
        url=_ARTISTS_URL_PATTERN,
        method="GET",
        json=_artists_response([_artist_entry("art-1"), _artist_entry("art-2", image_url=None)]),
    )

    result = _make_client().get_artists_images(["art-1", "art-2"])

    assert result == {
        "art-1": "https://i.scdn.co/image/art1.jpg",
        "art-2": None,
    }


def test_get_artists_images_empty_input_skips_network(httpx_mock: HTTPXMock) -> None:
    # 空入力でトークン / artists どちらも叩かないこと。
    # pytest-httpx は teardown で「未使用 mock があれば失敗」させるので、
    # add_response しないことで「呼び出さなければ成功」を表現する。
    assert _make_client().get_artists_images([]) == {}


def test_get_artists_images_dedupes_input(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTISTS_URL_PATTERN,
        method="GET",
        json=_artists_response([_artist_entry("art-1")]),
    )

    _make_client().get_artists_images(["art-1", "art-1", ""])

    req = next(r for r in httpx_mock.get_requests() if r.url.path == "/v1/artists")
    assert req.url.params.get("ids") == "art-1"


def test_get_artists_images_chunks_above_50(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    # 51 ids → 50 + 1 の 2 リクエストに分かれる。
    ids = [f"art-{i}" for i in range(51)]
    httpx_mock.add_response(
        url=_ARTISTS_URL_PATTERN,
        method="GET",
        json=_artists_response([_artist_entry(i) for i in ids[:50]]),
    )
    httpx_mock.add_response(
        url=_ARTISTS_URL_PATTERN,
        method="GET",
        json=_artists_response([_artist_entry(ids[50])]),
    )

    result = _make_client().get_artists_images(ids)

    artists_reqs = [r for r in httpx_mock.get_requests() if r.url.path == "/v1/artists"]
    assert len(artists_reqs) == 2
    assert len(result) == 51


def test_get_artists_images_skips_null_entries(httpx_mock: HTTPXMock) -> None:
    # Spotify は ID 不正時に null を返す。dict にエントリを作らずスキップする。
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTISTS_URL_PATTERN,
        method="GET",
        json=_artists_response([_artist_entry("art-1"), None]),
    )

    result = _make_client().get_artists_images(["art-1", "bogus"])

    assert result == {"art-1": "https://i.scdn.co/image/art1.jpg"}


def test_get_artists_images_429_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_ARTISTS_URL_PATTERN, method="GET", status_code=429)

    with pytest.raises(SpotifyApiError) as exc_info:
        _make_client().get_artists_images(["art-1"])
    assert exc_info.value.status_code == 429
