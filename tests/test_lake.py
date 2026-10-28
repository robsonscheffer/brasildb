from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pytest

from brasildb import lake

EVENTO_COLUMNS = [
    "ano", "turno", "sigla_uf", "id_municipio_tse", "zona", "secao", "arquivo_hash", "arquivo_membro", "linha",
    "data_hora", "nivel", "id_urna", "componente", "mensagem", "tipo_evento", "valor",
]


def _eventos(uf: str, turno: int, n: int) -> pa.Table:
    """n synthetic urna log lines for one state and round, all 17 catalog columns."""
    rows = {c: [] for c in EVENTO_COLUMNS}
    for i in range(n):
        values = {
            "ano": 2026,
            "turno": turno,
            "sigla_uf": uf,
            "id_municipio_tse": "03085",
            "zona": "0008",
            "secao": "0001",
            "arquivo_hash": "h1",
            "arquivo_membro": "logd.dat",
            "linha": i + 1,
            "data_hora": datetime(2026, 10, 25, 8, 0, i % 60),
            "nivel": "INFO",
            "id_urna": "02299969",
            "componente": "VOTA",
            "mensagem": f"linha {i}",
            "tipo_evento": "voto_computado",
            "valor": None,
        }
        for c in EVENTO_COLUMNS:
            rows[c].append(values[c])
    return pa.table(rows)


def _count(con, schema: str, table: str) -> int:
    return con.execute(f'SELECT count(*) FROM "{schema}"."{table}"').fetchone()[0]


def _parquet_files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.parquet"))


def test_load_catalog_has_eventos_with_partition():
    catalog = lake.load_catalog()
    assert catalog["br_tse_urna_logs"]["eventos"]["partition"] == ["ano", "turno", "sigla_uf"]
    assert catalog["br_bd_diretorios_brasil"]["municipio"]["partition"] == []


def test_write_uses_hive_layout_and_basename(tmp_path: Path):
    lake_dir = tmp_path / "lake"
    lake.write_table(str(lake_dir), "br_tse_urna_logs", "eventos", _eventos("RR", 2, 3), "rr-1")

    assert _parquet_files(lake_dir) == [
        "br_tse_urna_logs/eventos/ano=2026/turno=2/sigla_uf=RR/rr-1-0.parquet"
    ]


def test_connect_queries_views_with_partition_columns(tmp_path: Path):
    lake_dir = str(tmp_path / "lake")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("RR", 2, 3), "rr-2")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("RR", 1, 5), "rr-1")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("AC", 2, 4), "ac-2")

    con = lake.connect(lake_dir)
    try:
        assert _count(con, "br_tse_urna_logs", "eventos") == 12
        rows = con.execute(
            "SELECT turno, sigla_uf, count(*) FROM br_tse_urna_logs.eventos "
            "GROUP BY turno, sigla_uf ORDER BY turno, sigla_uf"
        ).fetchall()
        assert rows == [(1, "RR", 5), (2, "AC", 4), (2, "RR", 3)]
    finally:
        con.close()


def test_rewrite_same_basename_with_fewer_rows_leaves_no_stale_files(tmp_path: Path):
    lake_dir = tmp_path / "lake"
    # Many rows at once make several part files in the same partition.
    lake.write_table(str(lake_dir), "br_tse_urna_logs", "eventos", _eventos("RR", 2, 50_000), "rr-2")
    before = _parquet_files(lake_dir)
    assert len(before) >= 1

    lake.write_table(str(lake_dir), "br_tse_urna_logs", "eventos", _eventos("RR", 2, 2), "rr-2")

    after = _parquet_files(lake_dir)
    assert after == ["br_tse_urna_logs/eventos/ano=2026/turno=2/sigla_uf=RR/rr-2-0.parquet"]
    con = lake.connect(str(lake_dir))
    try:
        assert _count(con, "br_tse_urna_logs", "eventos") == 2
    finally:
        con.close()


def test_rewrite_keeps_other_basenames_and_other_partitions(tmp_path: Path):
    lake_dir = str(tmp_path / "lake")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("RR", 2, 3), "rr-2")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("RR", 2, 1), "rr-2-extra")
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("AC", 2, 2), "ac-2")

    # Rewriting basename "rr-2" must not touch "rr-2-extra" (names differ by more than the -<n> suffix)
    lake.write_table(lake_dir, "br_tse_urna_logs", "eventos", _eventos("RR", 2, 4), "rr-2")

    con = lake.connect(lake_dir)
    try:
        assert _count(con, "br_tse_urna_logs", "eventos") == 4 + 1 + 2
    finally:
        con.close()


def test_non_partitioned_table_writes_directly_into_table_dir(tmp_path: Path):
    lake_dir = tmp_path / "lake"
    municipios = pa.table(
        {
            "id_municipio": ["1400100", "1400209"],
            "id_municipio_tse": ["03123", "03085"],
            "sigla_uf": ["RR", "RR"],
            "nome": ["Amajari", "Alto Alegre"],
        }
    )
    lake.write_table(str(lake_dir), "br_bd_diretorios_brasil", "municipio", municipios, "municipio")
    assert _parquet_files(lake_dir) == ["br_bd_diretorios_brasil/municipio/municipio-0.parquet"]

    lake.write_table(str(lake_dir), "br_bd_diretorios_brasil", "municipio", municipios.slice(0, 1), "municipio")
    assert _parquet_files(lake_dir) == ["br_bd_diretorios_brasil/municipio/municipio-0.parquet"]

    con = lake.connect(str(lake_dir))
    try:
        assert _count(con, "br_bd_diretorios_brasil", "municipio") == 1
    finally:
        con.close()


def test_connect_skips_tables_without_files(tmp_path: Path):
    con = lake.connect(str(tmp_path / "empty"))
    try:
        schemas = [r[0] for r in con.execute("SELECT schema_name FROM duckdb_schemas()").fetchall()]
        assert "br_tse_urna_logs" not in schemas
    finally:
        con.close()


def test_write_rejects_missing_or_extra_columns(tmp_path: Path):
    good = _eventos("RR", 2, 1)
    missing = good.drop_columns(["valor"])
    with pytest.raises(ValueError, match="missing=\\['valor'\\]"):
        lake.write_table(str(tmp_path), "br_tse_urna_logs", "eventos", missing, "rr-2")

    extra = good.append_column("surpresa", pa.array(["x"]))
    with pytest.raises(ValueError, match="extra=\\['surpresa'\\]"):
        lake.write_table(str(tmp_path), "br_tse_urna_logs", "eventos", extra, "rr-2")
    assert _parquet_files(tmp_path) == []


def test_write_rejects_unknown_table(tmp_path: Path):
    with pytest.raises(KeyError, match="not in catalog"):
        lake.write_table(str(tmp_path), "br_tse_urna_logs", "nao_existe", _eventos("RR", 2, 1), "x")
