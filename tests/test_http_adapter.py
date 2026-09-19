import io
import urllib.error

import pytest

from sg_estate.adapters import http


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def _http_error(status, headers=None):
    return urllib.error.HTTPError(
        "https://example.test/data",
        status,
        "request failed",
        headers or {},
        io.BytesIO(),
    )


def test_get_json_honours_capped_retry_after_then_succeeds():
    outcomes = iter(
        [
            _http_error(429, {"Retry-After": "120"}),
            _Response(b'\xef\xbb\xbf{"status": "ok"}'),
        ]
    )
    requests = []
    delays = []

    def opener(request, timeout):
        requests.append((request, timeout))
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    payload = http.get_json(
        "https://example.test/data",
        timeout=7,
        headers={"Accept": "application/json", "User-Agent": "test-agent"},
        max_retry_delay_seconds=2,
        opener=opener,
        sleep=delays.append,
    )

    assert payload == {"status": "ok"}
    assert len(requests) == 2
    assert all(timeout == 7 for _, timeout in requests)
    assert requests[0][0].get_header("Accept") == "application/json"
    assert requests[0][0].get_header("User-agent") == "test-agent"
    assert delays == [2]


def test_get_text_retries_transport_errors_only_up_to_attempt_limit():
    calls = 0
    delays = []

    def opener(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 4
        raise urllib.error.URLError("temporary DNS failure")

    with pytest.raises(urllib.error.URLError, match="temporary DNS failure"):
        http.get_text(
            "https://example.test/data.csv",
            timeout=4,
            attempts=3,
            backoff_seconds=0.25,
            opener=opener,
            sleep=delays.append,
        )

    assert calls == 3
    assert delays == [0.25, 0.5]


def test_get_text_retries_server_errors_with_exponential_backoff():
    outcomes = iter([_http_error(503), _Response(b"ready")])
    delays = []

    def opener(_request, timeout):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = http.get_text(
        "https://example.test/data.csv",
        backoff_seconds=0.75,
        opener=opener,
        sleep=delays.append,
    )

    assert result == "ready"
    assert delays == [0.75]


def test_get_bytes_does_not_retry_non_transient_http_errors():
    calls = 0
    delays = []

    def opener(_request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(404)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http.get_bytes(
            "https://example.test/missing",
            attempts=3,
            opener=opener,
            sleep=delays.append,
        )

    assert exc_info.value.code == 404
    assert calls == 1
    assert delays == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"attempts": 0}, "attempts must be at least 1"),
        ({"timeout": 0}, "timeout must be positive"),
        ({"backoff_seconds": -1}, "retry delays cannot be negative"),
    ],
)
def test_request_policy_rejects_unbounded_or_invalid_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        http.get_bytes("https://example.test/data", **kwargs)
