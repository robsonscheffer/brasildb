from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("extension_data", ROOT / "scripts/extension_data.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_map_is_reproducible_from_published_records():
    generated = module.build()
    assert generated == json.loads((ROOT / "docs/site/prorrogacao/closures.json").read_text())
    assert generated["total"] == 497894
    assert len(generated["cities"]) > 5500
    assert all(sum(n for _, n in c["closures"]) == c["total"] for c in generated["cities"])


def test_checkpoint_counts_use_strict_minute_boundaries():
    data = module.build()
    before = lambda time: sum(n for c in data["cities"] for minute, n in c["closures"] if minute < time)
    assert before(17 * 60 + 3) == 393786
    assert before(17 * 60 + 49) == 490634
    assert before(17 * 60 + 3) <= before(17 * 60 + 49) <= data["total"]


def test_aliases_and_foreign_sections_are_not_counted(tmp_path):
    (tmp_path / "data/secoes/BR").mkdir(parents=True)
    (tmp_path / "data/secoes/ZZ").mkdir()
    (tmp_path / "data/towns.json").write_text(json.dumps({"id": ["1"], "uf": ["SP"],
        "nome": ["Cidade"], "lat": [0], "lon": [0]}))
    sample = {"uf": "SP", "municipio": "1", "campos": ["encerramento"],
              "secoes": {"1": ["17:03"], "2": "1", "3": [None]}}
    (tmp_path / "data/secoes/BR/1.json").write_text(json.dumps(sample))
    sample["uf"] = "ZZ"
    (tmp_path / "data/secoes/ZZ/1.json").write_text(json.dumps(sample))
    data = module.build(tmp_path)
    assert data["total"] == 1
    assert data["aggregated_aliases_excluded"] == 1
    assert data["cities"][0]["closures"] == [[1023, 1]]
