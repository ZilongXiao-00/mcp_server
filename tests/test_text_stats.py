from text_stats import analyze_text


def test_normal_input():
    r = analyze_text("hello openclaw", request_id="t-1")
    assert r["ok"] is True
    assert r["request_id"] == "t-1"
    assert r["result"] == {"length": 14, "word_count": 2}


def test_empty_string_is_valid():
    r = analyze_text("", request_id="t-2")
    assert r["ok"] is True
    assert r["result"] == {"length": 0, "word_count": 0}


def test_whitespace_only_counts_as_zero_words():
    r = analyze_text("   \t\n  ")
    assert r["ok"] is True
    assert r["result"]["length"] == 7  # 3 spaces + tab + newline + 2 spaces
    assert r["result"]["word_count"] == 0


def test_non_string_input_is_invalid():
    r = analyze_text(123, request_id="t-3")  # type: ignore[arg-type]
    assert r["ok"] is False
    assert r["request_id"] == "t-3"
    assert r["error"]["code"] == "invalid_input"


def test_none_input_is_invalid():
    r = analyze_text(None)  # type: ignore[arg-type]
    assert r["ok"] is False
    assert r["error"]["code"] == "invalid_input"


def test_too_long_input_is_rejected():
    from config import MAX_INPUT_CHARS
    r = analyze_text("a" * (MAX_INPUT_CHARS + 1), request_id="t-4")
    assert r["ok"] is False
    assert r["error"]["code"] == "input_too_long"


def test_request_id_auto_generated_when_missing():
    r = analyze_text("hi")
    assert r["ok"] is True
    assert r["request_id"].startswith("req_")
    assert len(r["request_id"]) > len("req_")


def test_non_string_input_does_not_raise():
    # Must return a structured error, never raise.
    for bad in (123, None, ["a list"], {"a": "dict"}):
        r = analyze_text(bad)  # type: ignore[arg-type]
        assert r["ok"] is False
        assert r["request_id"].startswith("req_")
