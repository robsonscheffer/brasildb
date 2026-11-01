"""The count night: sections enter the sum in the order the TSE received their bulletins."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

spec = importlib.util.spec_from_file_location(
    "apuracao_data", Path(__file__).parents[1] / "scripts" / "apuracao_data.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)


def _con(minutos):
    con = duckdb.connect()
    con.execute("""CREATE TABLE c_votacao AS SELECT * FROM (VALUES
        ('RR', '03085', '0008', '0001', '13', 30), ('RR', '03085', '0008', '0001', '22', 10),
        ('RR', '03085', '0008', '0002', '13', 4), ('RR', '03085', '0008', '0002', '22', 16),
        ('RR', '03085', '0008', '0003', '13', 6))
        AS t(sigla_uf, id_municipio_tse, zona, secao, numero_votavel, votos)""")
    con.execute("CREATE TABLE c_apuracao (sigla_uf VARCHAR, id_municipio_tse VARCHAR, zona VARCHAR, "
                "secao VARCHAR, minuto DOUBLE)")
    con.executemany("INSERT INTO c_apuracao VALUES ('RR', '03085', '0008', ?, ?)", minutos)
    return con


def test_the_count_orders_sections_by_bu_received_time():
    con = _con([("0001", 1230.0), ("0002", 1201.5), ("0003", 1215.0)])
    ap.ordem(con)
    rows = con.execute("SELECT secao, ordem_br FROM c_ordem ORDER BY ordem_br").fetchall()
    assert rows == [("0002", 1), ("0003", 2), ("0001", 3)]


def test_the_count_stops_when_a_section_with_votes_has_no_bu_time():
    con = _con([("0001", 1230.0), ("0002", 1201.5)])
    with pytest.raises(SystemExit, match="1 sections with votes have no BU received time"):
        ap.ordem(con)


def test_a_city_file_holds_each_sections_votes_and_place():
    con = _con([("0001", 1230.0), ("0002", 1201.5), ("0003", 1215.0)])
    ap.ordem(con)
    assert ap.municipios(con) == {("RR", "03085"): {
        "0008-0001": [[30, 10, 0, 0], 3],
        "0008-0002": [[4, 16, 0, 0], 1],
        "0008-0003": [[6, 0, 0, 0], 2],
    }}


def test_the_brasil_count_ends_at_the_official_votes():
    con = _con([("0001", 1230.0), ("0002", 1201.5), ("0003", 1215.0)])
    ap.ordem(con)
    s = ap.apuracao_series(con)
    assert {n: sum(v) for n, v in s["brasil"].items()} == {"13": 40, "22": 26, "95": 0, "96": 0}
