"""Check that a per-section time is the official count time, against the TSE totalization panel.

  uv run python scripts/check_count_time.py <panel bundle .json> [--ano 2026] [--turno 2]

The panel (evolucao-totalizacao.tse.jus.br) gives, every 5 minutes, how many sections of each
city were counted. It is a test oracle here, never a data source. The bundle is the file saved
from the panel in a browser (its host refuses scripted downloads): {"arquivos": {path: json}}.

Checks boletim_urna_secao.data_hora_recebimento. Every state must pass:
  spread  the middle half of its sections spans at least 10 minutes. One shared time is a batch
          (cs.json "ha" in 8 states was one rewrite time per state, written after the count).
  delay   for each snapshot where a city's count moved to N, the city's N-th section by our time
          arrived 0 to 10 minutes before the snapshot. Below 0, the panel counted a section
          before our time says it arrived; far above, our time is late. At most 0.1% of a
          state's snapshots may fall outside. Round 2 of 2026: none did; median 1.8 minutes,
          worst 7.7.
Exits 1 when any state fails.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brasildb import config, lake  # noqa: E402

MIN_SPREAD = 10  # minutes
DELAY = (0.0, 10.0)  # minutes from our N-th arrival to the panel snapshot showing N
MAX_OUTSIDE = 0.001


def panel(bundle: Path) -> dict[str, list[tuple[int, int]]]:
    """City code -> [(snapshot minute of the day, sections counted)], from the city summary."""
    files = json.loads(bundle.read_text(encoding="utf-8"))["arquivos"]
    d = files[next(k for k in files if k.endswith("_resumo_municipio.json"))]["data"]
    out: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
    for i, code in enumerate(d["sg_ue_mun"]):
        t = d["dt_data"][i]
        out[str(code).zfill(5)].append((int(t[11:13]) * 60 + int(t[14:16]), d["qt_secoes_totalizadas"][i]))
    return {c: sorted(s) for c, s in out.items()}


def delays(snaps: list[tuple[int, int]], arrivals: list[float]) -> list[float]:
    """Minutes from the N-th arrival to each snapshot where the count moved to N. A count above
    the number of arrivals gives infinity (the panel counted sections we do not have)."""
    out, prev = [], 0
    for t, n in snaps:
        if n != prev and n > 0:
            out.append(t - arrivals[n - 1] if n <= len(arrivals) else float("inf"))
        prev = n
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--turno", type=int, default=2)
    a = ap.parse_args()
    off = panel(a.bundle)
    con = lake.connect(config.load().lake)
    # Minutes since midnight of the first arrival's day, the panel's clock (Brasília).
    rows = con.execute(
        "SELECT sigla_uf, id_municipio_tse, epoch(data_hora_recebimento - "
        "  CAST(CAST(min(data_hora_recebimento) OVER () AS DATE) AS TIMESTAMP)) / 60 "
        "FROM br_tse_eleicoes.boletim_urna_secao WHERE ano = ? AND turno = ? AND sigla_uf <> 'ZZ'",
        [a.ano, a.turno]).fetchall()
    city_uf, arrivals = {}, collections.defaultdict(list)
    for uf, city, m in rows:
        city_uf[city] = uf
        arrivals[city].append(m)
    by_uf = collections.defaultdict(lambda: {"mins": [], "delays": []})
    for city, v in arrivals.items():
        v.sort()
        s = by_uf[city_uf[city]]
        s["mins"] += v
        s["delays"] += delays(off.get(city, []), v)

    failed = []
    print("state  sections  spread_min  snapshots  delay_p50  delay_max  outside")
    for uf, s in sorted(by_uf.items()):
        q = statistics.quantiles(s["mins"], n=4)
        spread, ds = q[2] - q[0], s["delays"]
        outside = sum(not DELAY[0] <= x <= DELAY[1] for x in ds) / max(len(ds), 1)
        ok = spread >= MIN_SPREAD and ds and outside <= MAX_OUTSIDE
        print(f"{uf:5}  {len(s['mins']):8}  {spread:10.0f}  {len(ds):9}  {statistics.median(ds) if ds else 0:9.1f}"
              f"  {max(ds) if ds else 0:9.1f}  {outside:7.2%}{'' if ok else '  FAIL'}")
        if not ok:
            failed.append(uf)
    no_panel = sorted(arrivals.keys() - off.keys())
    print(f"cities with no panel data: {len(no_panel)}")
    if failed or no_panel:
        print("FAILED:", ", ".join(failed + no_panel))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
