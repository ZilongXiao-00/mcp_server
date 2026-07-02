import pytest

from config import MAX_BODY_BYTES, MAX_INPUT_CHARS


pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_text_stats_normal(client):
    r = await client.post("/tools/text_stats", json={"text": "hello openclaw", "request_id": "t-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["request_id"] == "t-1"
    assert body["result"] == {"length": 14, "word_count": 2}


async def test_text_stats_empty_is_valid(client):
    r = await client.post("/tools/text_stats", json={"text": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"] == {"length": 0, "word_count": 0}
    assert body["request_id"].startswith("req_")


async def test_text_stats_request_id_auto_generated(client):
    r = await client.post("/tools/text_stats", json={"text": "hi"})
    assert r.status_code == 200
    assert r.json()["request_id"].startswith("req_")


async def test_text_stats_non_string_returns_structured_error(client):
    r = await client.post("/tools/text_stats", json={"text": 123})
    # Pydantic rejects non-string -> 422, but body is structured.
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    assert "traceback" not in r.text.lower()


async def test_text_stats_missing_text_field_returns_structured_error(client):
    r = await client.post("/tools/text_stats", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"


async def test_text_stats_too_long_returns_structured_error(client):
    r = await client.post(
        "/tools/text_stats",
        json={"text": "a" * (MAX_INPUT_CHARS + 1)},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "input_too_long"


async def test_oversized_body_rejected(client):
    big = "x" * (MAX_BODY_BYTES + 10)
    r = await client.post(
        "/tools/text_stats",
        json={"text": big},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "body_too_large"
