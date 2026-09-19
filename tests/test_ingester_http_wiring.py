import ast
import io
from pathlib import Path
import urllib.error

import pytest

import data_ingest
import fetch_chas
import ingest_hdb_upgrading
import ingest_nea_air


ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_HTTP_SCAN_ROOTS = (ROOT / "models", ROOT / "sg_estate")
SHARED_HTTP_ADAPTER = ROOT / "sg_estate" / "adapters" / "http.py"
DIRECT_URLLIB_CALLS = {"urlopen", "urlretrieve"}
NETWORK_CLIENT_MODULES = {"requests", "httpx", "aiohttp", "urllib3"}


def _direct_http_violations(path: Path) -> list[str]:
    """Return direct-client imports/calls outside the shared adapter.

    The production scan deliberately excludes ``scrapers/``: browser/session
    clients have source-specific behavior and are covered by SCRAPE-204.
    ``urllib.request`` imports remain allowed when an ingester passes urlopen
    as an injected adapter opener; only direct calls are forbidden.
    """

    if path == SHARED_HTTP_ADAPTER:
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    urllib_package_aliases = {"urllib"}
    urllib_request_aliases: set[str] = set()
    direct_urlopen_aliases: set[str] = set()
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".", 1)[0]
                if alias.name == "urllib.request":
                    if alias.asname:
                        urllib_request_aliases.add(alias.asname)
                    else:
                        urllib_package_aliases.add("urllib")
                if top_level in NETWORK_CLIENT_MODULES:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: imports {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "urllib":
                for alias in node.names:
                    if alias.name == "request":
                        urllib_request_aliases.add(alias.asname or alias.name)
            if module == "urllib.request":
                for alias in node.names:
                    if alias.name in DIRECT_URLLIB_CALLS:
                        direct_urlopen_aliases.add(alias.asname or alias.name)
            if module.split(".", 1)[0] in NETWORK_CLIENT_MODULES:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: imports from {module}"
                )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in direct_urlopen_aliases:
            violations.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: calls {function.id}"
            )
            continue
        if not isinstance(function, ast.Attribute) or function.attr not in DIRECT_URLLIB_CALLS:
            continue
        value = function.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "request"
            and isinstance(value.value, ast.Name)
            and value.value.id in urllib_package_aliases
        ):
            violations.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: calls urllib.request.{function.attr}"
            )
        elif isinstance(value, ast.Name) and value.id in urllib_request_aliases:
            violations.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: calls urllib.request.{function.attr}"
            )
    return violations


def test_first_party_ingesters_do_not_bypass_shared_http_adapter():
    production_files = sorted(
        path
        for root in FIRST_PARTY_HTTP_SCAN_ROOTS
        for path in root.rglob("*.py")
    )
    assert ROOT / "models" / "geocode_private_projects.py" in production_files
    assert all(ROOT / "scrapers" not in path.parents for path in production_files)

    violations = [
        violation
        for path in production_files
        for violation in _direct_http_violations(path)
    ]

    assert violations == [], "Direct HTTP clients bypass the shared adapter:\n" + "\n".join(
        violations
    )


@pytest.mark.parametrize(
    ("module", "helper_name", "user_agent", "accept_json"),
    [
        (data_ingest, "http_get_json", "sg-estate-ingest/1.0", False),
        (fetch_chas, "http_get_json", "sg-estate-ingest/1.0", False),
        (ingest_hdb_upgrading, "_http_json", ingest_hdb_upgrading._UA, True),
        (ingest_nea_air, "_http_json", ingest_nea_air._UA, True),
    ],
)
def test_json_helpers_use_shared_resilient_adapter(
    monkeypatch,
    module,
    helper_name,
    user_agent,
    accept_json,
):
    sentinel_opener = object()
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"status": "ok"}

    monkeypatch.setattr(module, "get_json", fake_get_json)
    monkeypatch.setattr(module.urllib.request, "urlopen", sentinel_opener)

    result = getattr(module, helper_name)("https://example.test/data", timeout=13)

    expected_headers = {"User-Agent": user_agent}
    if accept_json:
        expected_headers["Accept"] = "application/json"
    assert result == {"status": "ok"}
    assert calls == [
        (
            "https://example.test/data",
            {
                "timeout": 13,
                "headers": expected_headers,
                "opener": sentinel_opener,
            },
        )
    ]


@pytest.mark.parametrize("module", [data_ingest, fetch_chas])
def test_binary_helpers_use_shared_resilient_adapter(monkeypatch, module):
    sentinel_opener = object()
    calls = []

    def fake_get_bytes(url, **kwargs):
        calls.append((url, kwargs))
        return b"dataset"

    monkeypatch.setattr(module, "get_bytes", fake_get_bytes)
    monkeypatch.setattr(module.urllib.request, "urlopen", sentinel_opener)

    result = module.http_get_bytes("https://example.test/file", timeout=71)

    assert result == b"dataset"
    assert calls == [
        (
            "https://example.test/file",
            {
                "timeout": 71,
                "headers": {"User-Agent": "sg-estate-ingest/1.0"},
                "opener": sentinel_opener,
            },
        )
    ]


def test_data_ingest_keeps_dataset_poll_retry_loop(monkeypatch):
    poll_calls = 0
    download_calls = []
    delays = []

    def fake_poll(url, timeout):
        nonlocal poll_calls
        poll_calls += 1
        assert timeout == 30
        if poll_calls == 1:
            raise urllib.error.HTTPError(
                url,
                429,
                "rate limited",
                {"Retry-After": "0"},
                io.BytesIO(),
            )
        return {"data": {"url": "https://example.test/file.csv"}}

    def fake_download(url, timeout):
        download_calls.append((url, timeout))
        return b"rows"

    monkeypatch.setattr(data_ingest, "http_get_json", fake_poll)
    monkeypatch.setattr(data_ingest, "http_get_bytes", fake_download)
    monkeypatch.setattr(data_ingest.time, "sleep", delays.append)

    result = data_ingest.poll_download("dataset-id", timeout=77, retries=2)

    assert result == b"rows"
    assert poll_calls == 2
    assert download_calls == [("https://example.test/file.csv", 77)]
    assert delays == [5]
