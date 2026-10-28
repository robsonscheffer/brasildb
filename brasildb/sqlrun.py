"""Run the SQL views and checks in a DuckDB connection."""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb


def apply(con: duckdb.DuckDBPyConnection, folder: str | Path, skip_missing: bool = False) -> None:
    """Run every .sql file in `folder`, in file name order. Files are re-runnable (CREATE OR REPLACE).

    skip_missing: a file whose tables are not in the lake yet is skipped with a note on stderr."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"SQL folder not found: {folder}")
    for path in sorted(folder.glob("*.sql")):
        try:
            con.execute(path.read_text(encoding="utf-8"))
        except duckdb.CatalogException as exc:
            if not skip_missing:
                raise
            print(f"skipped {path.name}: {str(exc).splitlines()[0]}", file=sys.stderr)
