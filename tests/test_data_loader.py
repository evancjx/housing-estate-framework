"""Focused contract tests for the shared browser JSON loader."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "site" / "assets" / "data-loader.js"


def test_data_loader_asset_exposes_required_api_and_runtime_semantics() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable; browser loader contract is skipped")

    program = f"""
global.document = {{ baseURI: "https://example.test/research/index.html" }};
const calls = new Map();
let flakyAttempts = 0;
global.fetch = (url, options = {{}}) => {{
  calls.set(url, (calls.get(url) || 0) + 1);
  if (url.endsWith("/slow.json")) {{
    return new Promise((resolve, reject) => {{
      options.signal.addEventListener("abort", () => {{
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      }}, {{ once: true }});
    }});
  }}
  if (url.endsWith("/missing.json")) {{
    return Promise.resolve({{ ok: false, status: 503, json: async () => ({{}}) }});
  }}
  if (url.endsWith("/flaky.json") && flakyAttempts++ === 0) {{
    return Promise.resolve({{ ok: false, status: 500, json: async () => ({{}}) }});
  }}
  return new Promise(resolve => setTimeout(() => resolve({{
    ok: true,
    status: 200,
    json: async () => ({{ schema_version: 1, url }}),
  }}), 2));
}};
require({json.dumps(str(SCRIPT))});

(async () => {{
  const api = global.SGEstateData;
  const validate = value => value.schema_version === 1 || "wrong schema";
  const [first, second] = await Promise.all([
    api.loadJSON("shared.json", {{ validate }}),
    api.loadJSON("./shared.json", {{ validate }}),
  ]);
  const sharedURL = "https://example.test/research/shared.json";
  const cached = await api.loadJSON("shared.json", {{ validate }});
  api.invalidate("shared.json");
  await api.loadJSON("shared.json", {{ validate }});

  let schemaKind = null;
  try {{
    await api.loadJSON("schema.json", {{ validate: () => "schema mismatch" }});
  }} catch (error) {{
    schemaKind = error.kind;
  }}
  await api.loadJSON("cached-schema.json");
  try {{
    await api.loadJSON("cached-schema.json", {{ validate: () => "schema mismatch" }});
  }} catch (error) {{}}
  await api.loadJSON("cached-schema.json", {{ validate }});

  let timeoutKind = null;
  try {{
    await api.loadJSON("slow.json", {{ timeoutMs: 5 }});
  }} catch (error) {{
    timeoutKind = error.kind;
  }}

  let flakyKind = null;
  try {{
    await api.loadJSON("flaky.json");
  }} catch (error) {{
    flakyKind = error.kind;
  }}
  await api.loadJSON("flaky.json", {{ validate }});

  const settled = await api.loadMany(
    ["many-good.json", "missing.json"],
    {{ validate }}
  );

  for (let index = 0; index < 17; index += 1) {{
    await api.loadJSON(`cache-${{index}}.json`, {{ validate }});
  }}
  await api.loadJSON("cache-0.json", {{ validate }});

  process.stdout.write(JSON.stringify({{
    methods: ["loadJSON", "loadMany", "invalidate", "resolveURL"]
      .every(name => typeof api[name] === "function"),
    typedError: typeof api.DataLoadError === "function",
    resolved: api.resolveURL("../data.json"),
    sameValue: first.url === second.url && second.url === cached.url,
    sharedCalls: calls.get(sharedURL),
    schemaKind,
    cachedSchemaCalls: calls.get("https://example.test/research/cached-schema.json"),
    timeoutKind,
    flakyKind,
    flakyCalls: calls.get("https://example.test/research/flaky.json"),
    settled: settled.map(result => result.status),
    settledErrorKind: settled[1].reason.kind,
    cacheZeroCalls: calls.get("https://example.test/research/cache-0.json"),
  }}));
}})().catch(error => {{
  process.stderr.write(error.stack || String(error));
  process.exit(1);
}});
"""
    completed = subprocess.run(
        [node, "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "methods": True,
        "typedError": True,
        "resolved": "https://example.test/data.json",
        "sameValue": True,
        "sharedCalls": 2,
        "schemaKind": "schema",
        "cachedSchemaCalls": 2,
        "timeoutKind": "timeout",
        "flakyKind": "http",
        "flakyCalls": 2,
        "settled": ["fulfilled", "rejected"],
        "settledErrorKind": "http",
        "cacheZeroCalls": 2,
    }
