"""Run the SQL views and checks in a DuckDB connection."""
from __future__ import annotations

from pathlib import Path

import duckdb


def apply(con: duckdb.DuckDBPyConnection, folder: str | Path) -> None:
    """Run every .sql file in `folder`, in file name order. Files are re-runnable (CREATE OR REPLACE)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"SQL folder not found: {folder}")
    for path in sorted(folder.glob("*.sql")):
        con.execute(path.read_text(encoding="utf-8"))
