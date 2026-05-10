import uuid

from fastapi.testclient import TestClient

BILL_EVANS_ID = "4xRYI6VqpkE3UwrDrAZL8L"


def _new_record_payload(**overrides) -> dict:
    base = {
        "artist_id": BILL_EVANS_ID,
        "title": "Waltz for Debby",
        "original_release_date": "1962",
        "pressing_info": "original",
        "memo": "",
    }
    base.update(overrides)
    return base


def test_list_empty(seeded_client: TestClient) -> None:
    res = seeded_client.get("/api/records")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_create_then_list(seeded_client: TestClient) -> None:
    res = seeded_client.post("/api/records", json=_new_record_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    # id is uuid v7 (string format)
    parsed = uuid.UUID(body["id"])
    assert parsed.version == 7
    assert body["display_order"] == 1
    assert body["title"] == "Waltz for Debby"
    assert body["source"] == "manual"
    assert body["purchase_currency"] == "JPY"

    res2 = seeded_client.get("/api/records")
    assert len(res2.json()["items"]) == 1


def test_display_order_increments(seeded_client: TestClient) -> None:
    a = seeded_client.post("/api/records", json=_new_record_payload(title="A")).json()
    b = seeded_client.post("/api/records", json=_new_record_payload(title="B")).json()
    c = seeded_client.post("/api/records", json=_new_record_payload(title="C")).json()
    assert (a["display_order"], b["display_order"], c["display_order"]) == (1, 2, 3)


def test_partial_update_preserves_unsent_fields(seeded_client: TestClient) -> None:
    created = seeded_client.post(
        "/api/records",
        json=_new_record_payload(title="Original", memo="initial memo"),
    ).json()

    res = seeded_client.put(
        f"/api/records/{created['id']}",
        json={"memo": "updated memo only"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["memo"] == "updated memo only"
    # untouched fields preserved
    assert body["title"] == "Original"
    assert body["original_release_date"] == "1962"
    assert body["display_order"] == 1


def test_put_unknown_id_returns_404(seeded_client: TestClient) -> None:
    res = seeded_client.put(
        f"/api/records/{uuid.uuid4()}",
        json={"memo": "noop"},
    )
    assert res.status_code == 404


def test_invalid_release_date_returns_422(seeded_client: TestClient) -> None:
    res = seeded_client.post(
        "/api/records",
        json=_new_record_payload(original_release_date="not-a-date"),
    )
    assert res.status_code == 422


def test_invalid_currency_returns_422(seeded_client: TestClient) -> None:
    res = seeded_client.post(
        "/api/records",
        json=_new_record_payload(purchase_currency="yen"),
    )
    assert res.status_code == 422
