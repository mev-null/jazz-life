from fastapi.testclient import TestClient


def test_artists_empty(client: TestClient) -> None:
    res = client.get("/api/artists")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_artists_seeded_returns_six(seeded_client: TestClient) -> None:
    res = seeded_client.get("/api/artists")
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 6
    names = {item["name"] for item in body["items"]}
    assert "Bill Evans" in names
    assert "Avishai Cohen" in names


def test_artists_sorted_by_added_at_desc(seeded_client: TestClient) -> None:
    res = seeded_client.get("/api/artists")
    items = res.json()["items"]
    added_dates = [item["added_at"] for item in items]
    assert added_dates == sorted(added_dates, reverse=True)
