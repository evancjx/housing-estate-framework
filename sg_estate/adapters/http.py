"""Small, dependency-free helpers for resilient HTTP GET requests.

The pipeline ingesters run against public APIs where short-lived 429 and 5xx
responses are expected.  These helpers keep retry behaviour consistent while
leaving callers responsible for dataset-specific validation and caching.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar


DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5
DEFAULT_MAX_RETRY_DELAY_SECONDS = 30.0

_TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, *range(500, 600)})
_T = TypeVar("_T")


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    """Parse a Retry-After delta or HTTP date, returning ``None`` if invalid."""
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            return None
        return max(0.0, retry_at.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return None


def _retry_delay(
    attempt: int,
    error: Exception,
    *,
    backoff_seconds: float,
    max_retry_delay_seconds: float,
) -> float:
    retry_after = (
        _retry_after_seconds(error)
        if isinstance(error, urllib.error.HTTPError)
        else None
    )
    delay = (
        retry_after
        if retry_after is not None
        else backoff_seconds * (2 ** (attempt - 1))
    )
    return min(max_retry_delay_seconds, delay)


def _is_transient(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in _TRANSIENT_HTTP_STATUSES
    return isinstance(
        error,
        (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.IncompleteRead,
        ),
    )


def _get(
    url: str,
    *,
    decoder: Callable[[bytes], _T],
    timeout: float,
    headers: Mapping[str, str] | None,
    attempts: int,
    backoff_seconds: float,
    max_retry_delay_seconds: float,
    opener: Callable[..., Any] | None,
    sleep: Callable[[float], None] | None,
) -> _T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if backoff_seconds < 0 or max_retry_delay_seconds < 0:
        raise ValueError("retry delays cannot be negative")

    open_url = opener or urllib.request.urlopen
    wait = sleep or time.sleep
    request = urllib.request.Request(url, headers=dict(headers or {}))

    for attempt in range(1, attempts + 1):
        try:
            with open_url(request, timeout=timeout) as response:
                return decoder(response.read())
        except Exception as error:
            if attempt == attempts or not _is_transient(error):
                raise
            delay = _retry_delay(
                attempt,
                error,
                backoff_seconds=backoff_seconds,
                max_retry_delay_seconds=max_retry_delay_seconds,
            )
            if delay > 0:
                wait(delay)

    raise AssertionError("unreachable")


def get_bytes(
    url: str,
    *,
    timeout: float = 30,
    headers: Mapping[str, str] | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    max_retry_delay_seconds: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bytes:
    """Fetch a URL as bytes, retrying only transient failures."""
    return _get(
        url,
        decoder=lambda payload: payload,
        timeout=timeout,
        headers=headers,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
        max_retry_delay_seconds=max_retry_delay_seconds,
        opener=opener,
        sleep=sleep,
    )


def get_text(
    url: str,
    *,
    timeout: float = 30,
    headers: Mapping[str, str] | None = None,
    encoding: str = "utf-8",
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    max_retry_delay_seconds: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Fetch and decode text with the same bounded retry policy."""
    return _get(
        url,
        decoder=lambda payload: payload.decode(encoding),
        timeout=timeout,
        headers=headers,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
        max_retry_delay_seconds=max_retry_delay_seconds,
        opener=opener,
        sleep=sleep,
    )


def get_json(
    url: str,
    *,
    timeout: float = 30,
    headers: Mapping[str, str] | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    max_retry_delay_seconds: float = DEFAULT_MAX_RETRY_DELAY_SECONDS,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Any:
    """Fetch a UTF-8 JSON document with the same bounded retry policy."""
    return _get(
        url,
        decoder=lambda payload: json.loads(payload.decode("utf-8-sig")),
        timeout=timeout,
        headers=headers,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
        max_retry_delay_seconds=max_retry_delay_seconds,
        opener=opener,
        sleep=sleep,
    )
