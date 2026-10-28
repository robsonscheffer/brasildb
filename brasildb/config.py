"""Settings from environment variables, so the same code runs on a laptop and in a pod."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Election:
    ano: int
    turno: int
    id_pleito: str  # results-site "pleito" code, e.g. "3221"
    data: date  # voting day; log lines from other days are ignored by views


# Known elections. Add a row per new round.
ELECTIONS: dict[tuple[int, int], Election] = {
    (2026, 1): Election(2026, 1, "3220", date(2026, 10, 4)),
    (2026, 2): Election(2026, 2, "3221", date(2026, 10, 25)),
}

UFS = [
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
    "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to",
]  # "zz" (abroad) is left out until we need it


@dataclass(frozen=True)
class Settings:
    lake: str  # root of Parquet tables: a local path or s3://bucket/prefix
    raw: str  # root for original downloaded files (log.jez); local path
    state: str  # SQLite file that records which sections are done (resume)
    results_base: str  # results-site root
    rps: float  # global request budget per second to resultados.tse.jus.br
    concurrency: int
    keep_raw: bool


def load() -> Settings:
    data = os.environ.get("BRASILDB_DATA", "data")
    return Settings(
        lake=os.environ.get("BRASILDB_LAKE", f"{data}/lake"),
        raw=os.environ.get("BRASILDB_RAW", f"{data}/raw"),
        state=os.environ.get("BRASILDB_STATE", f"{data}/state.sqlite"),
        results_base=os.environ.get(
            "BRASILDB_RESULTS_BASE", "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna"
        ),
        rps=float(os.environ.get("BRASILDB_RPS", "20")),
        concurrency=int(os.environ.get("BRASILDB_CONCURRENCY", "20")),
        keep_raw=os.environ.get("BRASILDB_KEEP_RAW", "1") == "1",
    )
