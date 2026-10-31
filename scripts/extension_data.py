"""Build the extension map from published section records (no database required)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/site"


def build(site: Path = SITE) -> dict:
    towns = json.loads((site / "data/towns.json").read_text())
    positions = {code: i for i, code in enumerate(towns["id"])}
    cities: dict[str, Counter] = {}
    aliases = 0
    for path in sorted((site / "data/secoes").glob("*/*.json")):
        data = json.loads(path.read_text())
        if data["uf"] == "ZZ":
            continue
        index = data["campos"].index("encerramento")
        counts = cities.setdefault(data["municipio"], Counter())
        for row in data["secoes"].values():
            if isinstance(row, str):
                aliases += 1
                continue
            if not row[index]:
                continue
            hour, minute = map(int, row[index].split(":"))
            counts[hour * 60 + minute] += 1
    rows = []
    for code, counts in sorted(cities.items()):
        i = positions[code]
        rows.append({"id": code, "uf": towns["uf"][i], "nome": towns["nome"][i],
                     "lat": towns["lat"][i], "lon": towns["lon"][i],
                     "total": sum(counts.values()), "closures": [list(pair) for pair in sorted(counts.items())]})
    return {"source": "../data/secoes/<UF>/<municipio>-<zona>.json",
            "resolution": "minute", "comparison": "closure < displayed minute",
            "total": sum(row["total"] for row in rows), "aggregated_aliases_excluded": aliases,
            "cities": rows}


if __name__ == "__main__":
    target = SITE / "prorrogacao/closures.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(), ensure_ascii=False, separators=(",", ":")) + "\n")
    print(target)
