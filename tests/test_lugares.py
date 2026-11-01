"""The place picker's lists: every section the home or the count page can show, by city and zona."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "site_v2_data", Path(__file__).parents[1] / "scripts" / "site_v2_data.py")
sv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sv)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def test_runs_of_three_or_more_become_ranges():
    assert sv.faixas([1, 2, 3, 5, 6, 9]) == [[1, 3], 5, 6, 9]


def test_a_city_lists_the_sections_of_both_pages_and_its_aggregated_ones(tmp_path):
    _write(tmp_path / "secoes/RS/85367-0085.json", {"uf": "RS", "municipio": "85367", "zona": "0085",
           "secoes": {"0001": [], "0002": [], "0003": [], "0010": "0001"}})
    _write(tmp_path / "apuracao/mun/85367.json", {"uf": "RS", "id": "85367",
           "secoes": {"0085-0001": [], "0085-0002": [], "0085-0003": [], "0085-0004": []}})
    _write(tmp_path / "apuracao/mun/29270.json", {"uf": "ZZ", "id": "29270", "secoes": {"0001-0003": []}})
    assert sv.lugares(tmp_path) == {
        "RS": {"85367": {"0085": [[1, 4], 10], "agregadas": {"0085-0010": "0001"}}},
        "ZZ": {"29270": {"0001": [3]}},
    }
