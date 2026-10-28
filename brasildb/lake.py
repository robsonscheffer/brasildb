"""Parquet lake: write catalog tables with hive partitions, and open them as DuckDB views.

Layout: {lake}/{dataset}/{table}/<partition dirs>/{basename}-{i}.parquet
Local paths work everywhere; s3:// is wired through pyarrow.fs.S3FileSystem (not tested locally).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import duckdb
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import yaml

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog.yaml"
HIVE_NULL = "__HIVE_DEFAULT_PARTITION__"  # what pyarrow writes for a null partition value


def load_catalog() -> dict[str, Any]:
    """The schema contract: {dataset: {table: {partition, keys, columns, ...}}}."""
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _table_spec(catalog: dict[str, Any], dataset: str, table: str) -> dict[str, Any]:
    try:
        return catalog[dataset][table]
    except KeyError:
        raise KeyError(f"{dataset}.{table} is not in catalog.yaml") from None


def _join(*parts: str) -> str:
    head, *rest = parts
    return "/".join([head.rstrip("/"), *[p.strip("/") for p in rest]])


def _s3_filesystem() -> pafs.S3FileSystem:
    endpoint = os.environ.get("BRASILDB_S3_ENDPOINT") or None
    scheme = "https"
    if endpoint and "://" in endpoint:
        parsed = urlparse(endpoint)
        scheme = parsed.scheme
        endpoint = parsed.netloc
    return pafs.S3FileSystem(
        access_key=os.environ.get("AWS_ACCESS_KEY_ID"),
        secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        session_token=os.environ.get("AWS_SESSION_TOKEN"),
        region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
        endpoint_override=endpoint,
        scheme=scheme,
    )


def _filesystem(lake: str) -> tuple[pafs.FileSystem, str]:
    """Return (filesystem, root path inside it) for a lake given as a local path or s3:// URI."""
    if lake.startswith("s3://"):
        return _s3_filesystem(), lake[len("s3://"):].rstrip("/")
    return pafs.LocalFileSystem(), os.path.abspath(lake)


def _partition_dirs(data: pa.Table, partition: list[str]) -> list[str]:
    """Relative hive directories (ano=2026/turno=2/...) that the rows of `data` land in."""
    combos = data.select(partition).group_by(partition).aggregate([]).to_pylist()
    dirs = []
    for combo in combos:
        segments = []
        for col in partition:
            value = combo[col]
            text = HIVE_NULL if value is None else quote(str(value), safe="")
            segments.append(f"{col}={text}")
        dirs.append("/".join(segments))
    return sorted(set(dirs))


def _delete_stale(fs: pafs.FileSystem, target_dir: str, basename: str) -> None:
    """Remove files named {basename}-<n>.parquet in one directory, so a smaller rewrite leaves none."""
    pattern = re.compile(rf"^{re.escape(basename)}-\d+\.parquet$")
    selector = pafs.FileSelector(target_dir, recursive=False, allow_not_found=True)
    stale = [
        info.path
        for info in fs.get_file_info(selector)
        if info.type == pafs.FileType.File and pattern.match(os.path.basename(info.path))
    ]
    for path in stale:
        fs.delete_file(path)


def write_table(lake: str, dataset: str, table: str, data: pa.Table, basename: str) -> None:
    """Write `data` as hive-partitioned Parquet. Writing the same basename again replaces its files."""
    catalog = load_catalog()
    spec = _table_spec(catalog, dataset, table)
    expected = set(spec["columns"])
    got = set(data.column_names)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise ValueError(
            f"{dataset}.{table}: columns do not match catalog.yaml; missing={missing} extra={extra}"
        )

    partition: list[str] = list(spec.get("partition") or [])
    fs, root = _filesystem(lake)
    table_dir = f"{root}/{dataset}/{table}"

    if partition:
        target_dirs = [f"{table_dir}/{d}" for d in _partition_dirs(data, partition)]
        partitioning = ds.partitioning(
            pa.schema([data.schema.field(c) for c in partition]), flavor="hive"
        )
    else:
        target_dirs = [table_dir]
        partitioning = None

    for target in target_dirs:
        _delete_stale(fs, target, basename)

    ds.write_dataset(
        data,
        base_dir=table_dir,
        filesystem=fs,
        format="parquet",
        file_options=ds.ParquetFileFormat().make_write_options(compression="zstd", compression_level=9),
        partitioning=partitioning,
        basename_template=f"{basename}-{{i}}.parquet",
        existing_data_behavior="overwrite_or_ignore",
        create_dir=True,
    )


def _has_parquet(fs: pafs.FileSystem, directory: str) -> bool:
    selector = pafs.FileSelector(directory, recursive=True, allow_not_found=True)
    return any(
        info.type == pafs.FileType.File and info.path.endswith(".parquet")
        for info in fs.get_file_info(selector)
    )


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _configure_s3(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    if not key:
        con.execute("CREATE OR REPLACE SECRET brasildb_s3 (TYPE s3, PROVIDER credential_chain)")
        return
    endpoint = os.environ.get("BRASILDB_S3_ENDPOINT", "")
    use_ssl = "true"
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        use_ssl = "true" if parsed.scheme == "https" else "false"
        endpoint = parsed.netloc
    options = [
        "TYPE s3",
        "PROVIDER config",
        f"KEY_ID {_sql_str(key)}",
        f"SECRET {_sql_str(os.environ.get('AWS_SECRET_ACCESS_KEY', ''))}",
        f"REGION {_sql_str(os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1')}",
    ]
    if os.environ.get("AWS_SESSION_TOKEN"):
        options.append(f"SESSION_TOKEN {_sql_str(os.environ['AWS_SESSION_TOKEN'])}")
    if endpoint:
        options += [f"ENDPOINT {_sql_str(endpoint)}", "URL_STYLE 'path'", f"USE_SSL {use_ssl}"]
    con.execute(f"CREATE OR REPLACE SECRET brasildb_s3 ({', '.join(options)})")


def connect(lake: str, database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open DuckDB with one schema per dataset and one view per catalog table that has files."""
    catalog = load_catalog()
    con = duckdb.connect(database)
    if lake.startswith("s3://"):
        _configure_s3(con)
    fs, root = _filesystem(lake)
    for dataset, tables in catalog.items():
        for table in tables:
            table_dir = f"{root}/{dataset}/{table}"
            if not _has_parquet(fs, table_dir):
                continue
            # Views point at the lake URI (s3://...) or the absolute local path.
            base = lake if lake.startswith("s3://") else root
            glob = _join(base, dataset, table) + "/**/*.parquet"
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{dataset}"')
            con.execute(
                f'CREATE OR REPLACE VIEW "{dataset}"."{table}" AS '
                f"SELECT * FROM read_parquet({_sql_str(glob)}, "
                f"hive_partitioning=true, union_by_name=true)"
            )
    return con
