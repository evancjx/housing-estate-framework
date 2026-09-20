"""Offline CSV viewer contracts; Node is optional, with no browser dependency."""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is needed to execute the static viewer helpers")


def run_javascript(assertions):
    result = subprocess.run(
        [NODE, "-e", "const assert = require('assert/strict');\n"
         "require('./site/assets/research-data.js');\n"
         "const {parseCSV, serializeCSV, validatePath, sortRecords} = global.ResearchCSV;\n"
         + assertions],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_csv_parses_quotes_newlines_bom_empty_cells_and_duplicate_headers_rows():
    run_javascript(r'''
      const cases = [
        ['', []], ['\uFEFF', []],
        ['a,b\r\n1,2\r\n', [['a','b'],['1','2']]],
        ['a,a,\r\n1,,\r\n1,,\r\n', [['a','a',''],['1','',''],['1','','']]],
        ['\uFEFFa,b\n"a,b","line1\r\nline2"\n"a""b",\n',
          [['a','b'],['a,b','line1\r\nline2'],['a"b','']]],
        ['a\n\n', [['a'],['']]], ['""', [['']]], [',', [['','']]],
        ['a,b\rx,y\r', [['a','b'],['x','y']]],
      ];
      for (const [text, expected] of cases) assert.deepEqual(parseCSV(text), expected);
    ''')


def test_csv_download_roundtrip_retains_original_field_values_and_ragged_rows():
    run_javascript(r'''
      const rows = [
        ['name','name','', 'value'],
        ['same','001','','=literal'],
        ['same','001','','=literal'],
        ['quoted "text", with comma','line1\nline2','trailing '],
        [''], ['more','fields','','than','header'],
      ];
      assert.deepEqual(parseCSV(serializeCSV(rows)), rows);
      assert.deepEqual(parseCSV(serializeCSV([])), []);
    ''')


def test_malformed_quoted_csv_fails_instead_of_silently_changing_fields():
    run_javascript(r'''
      for (const value of ['"unfinished', 'a"b', '"a"x']) {
        assert.throws(() => parseCSV(value), /quoted field/);
      }
    ''')


def test_viewer_paths_allow_published_nested_csv_and_reject_external_or_traversal():
    run_javascript(r'''
      for (const path of ['research/2026-09-20/transactions.csv',
                          'research/2026-09-20/enrichment/peer_matches.csv']) {
        assert.equal(validatePath(path), path);
      }
      for (const path of [null, '/research/a.csv', 'https://evil.test/a.csv',
        '//evil.test/research/a.csv', 'research/../a.csv', 'research/./a.csv',
        'research/%2e%2e/a.csv', 'research/a.csv?q=x', 'research/a.csv#x',
        'research/a\\b.csv', 'Research/a.csv', 'research/.hidden.csv']) {
        assert.throws(() => validatePath(path));
      }
      const encoded = new URLSearchParams('path=research%2F..%2Fa.csv').get('path');
      assert.throws(() => validatePath(encoded));
      const doubled = new URLSearchParams('path=research%2F%252e%252e%2Fa.csv').get('path');
      assert.throws(() => validatePath(doubled));
    ''')


def test_numeric_sort_is_stable_retains_duplicates_and_places_empty_values_last():
    run_javascript(r'''
      const records = [['10'],['2'],[''],['2']].map((row,index) => ({row,index}));
      assert.deepEqual(sortRecords(records,0,1,true).map(x => x.index), [1,3,0,2]);
      assert.deepEqual(sortRecords(records,0,-1,true).map(x => x.index), [0,1,3,2]);
      assert.deepEqual(records.map(x => x.index), [0,1,2,3]);
      assert.deepEqual(records.map(x => x.row[0]), ['10','2','','2']);
    ''')
