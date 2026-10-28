"""SQL views and checks, run on synthetic catalog tables in an in-memory DuckDB (no Parquet, no network)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import pytest

from brasildb import config, sqlrun

SQL = Path(__file__).resolve().parents[1] / "sql"
DIA = dt.date(2026, 10, 25)  # round 2 voting day
DIA_ANTES = dt.date(2026, 10, 24)  # setup day, not an election day

EVENTOS_COLUNAS = (
    "ano INTEGER, turno INTEGER, sigla_uf VARCHAR, id_municipio_tse VARCHAR, zona VARCHAR, "
    "secao VARCHAR, arquivo_hash VARCHAR, linha INTEGER, data_hora TIMESTAMP, nivel VARCHAR, "
    "id_urna VARCHAR, componente VARCHAR, mensagem VARCHAR, "
    "tipo_evento VARCHAR, valor VARCHAR"
)
DETALHE_COLUNAS = (
    "ano INTEGER, turno INTEGER, id_eleicao VARCHAR, tipo_eleicao VARCHAR, data_eleicao DATE, "
    "sigla_uf VARCHAR, id_municipio_tse VARCHAR, zona VARCHAR, secao VARCHAR, cargo VARCHAR, "
    "aptos BIGINT, comparecimento BIGINT, abstencoes BIGINT, votos_nominais BIGINT, "
    "votos_brancos BIGINT, votos_nulos BIGINT, votos_legenda BIGINT, votos_nulos_apu_sep BIGINT, "
    "id_local_votacao VARCHAR, secao_instalada BOOLEAN, modelo_urna VARCHAR"
)


def _ts(dia: dt.date, hora: str) -> dt.datetime:
    h, m = hora.split(":")
    return dt.datetime(dia.year, dia.month, dia.day, int(h), int(m), 0)


class Linhas:
    """Builds eventos rows: one line per call, numbered in order."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def add(self, uf, mun, zona, secao, ts, tipo, valor=None) -> None:
        linha = len(self.rows) + 1
        self.rows.append((
            2026, 2, uf, mun, zona, secao, "hash1", linha, ts, "INFO", "02299969",
            "VOTA", "msg", tipo, valor,
        ))

    def votos(self, uf, mun, zona, secao, horas: list[str], dia: dt.date = DIA) -> None:
        for hora in horas:
            self.add(uf, mun, zona, secao, _ts(dia, hora), "voto_computado", "Presidente")


def _eventos() -> list[tuple]:
    l = Linhas()
    # RR 03085 zona 0008: four sections with election-day votes, one with none.
    l.add("RR", "03085", "0008", "0001", _ts(DIA, "06:50"), "urna_ligada")  # not a vote, ignored
    l.votos("RR", "03085", "0008", "0001", ["07:00", "07:01", "07:02", "07:03", "07:04"])
    l.votos("RR", "03085", "0008", "0001", ["03:00"], DIA_ANTES)  # setup day, ignored
    l.votos("RR", "03085", "0008", "0002", ["07:05", "07:06", "07:07", "07:08"])
    l.votos("RR", "03085", "0008", "0003", ["07:20", "07:21", "07:22", "07:23", "07:24", "07:25"])
    l.votos("RR", "03085", "0008", "0004", ["07:30", "07:31"])  # log, no CSV row
    l.votos("RR", "03085", "0008", "0005", ["07:40"], DIA_ANTES)  # only setup-day lines
    # RR 00108: one section only, so the state default applies (-1), not the derived 0.
    l.votos("RR", "00108", "0001", "0001", ["08:00", "08:01"])
    # AC 01304: one section, state default -2.
    l.votos("AC", "01304", "0001", "0001", ["09:00"])
    # AM 02135 (Benjamin Constant, Acre time): one section at 06:00, derived -2 is kept.
    l.votos("AM", "02135", "0020", "0026", ["06:01"])
    # PE 26000 (Noronha-like): one section at 09:00, derived +1 is kept.
    l.votos("PE", "26000", "0001", "0001", ["09:00"])
    # SP 71072: one section that opened late at 09:00; +1 is not an SP offset, so default 0.
    l.votos("SP", "71072", "0001", "0001", ["09:00"])
    # SP 50308: three sections at 07:00 local, derived -1 (state default would be 0).
    l.votos("SP", "50308", "0001", "0001", ["07:00", "07:01"])
    l.votos("SP", "50308", "0001", "0002", ["07:10", "07:11"])
    l.votos("SP", "50308", "0001", "0003", ["07:20", "07:21"])
    return l.rows


def _detalhe_row(uf, mun, zona, secao, cargo, comparecimento) -> tuple:
    return (
        2026, 2, "2045202026", "Eleição Ordinária", DIA, uf, mun, zona, secao, cargo,
        10, comparecimento, 10 - comparecimento, 0, 0, 0, 0, 0, "1", True, "UE2020",
    )


def _detalhe() -> list[tuple]:
    rows = [
        # 0001: two cargos; max must give 5 (the Governador row says 4).
        _detalhe_row("RR", "03085", "0008", "0001", "Presidente", 5),
        _detalhe_row("RR", "03085", "0008", "0001", "Governador", 4),
        _detalhe_row("RR", "03085", "0008", "0002", "Presidente", 3),  # log says 4
        _detalhe_row("RR", "03085", "0008", "0003", "Presidente", 6),
        _detalhe_row("RR", "03085", "0008", "0005", "Presidente", 5),  # no log at all
        _detalhe_row("RR", "00108", "0001", "0001", "Presidente", 2),
        _detalhe_row("AC", "01304", "0001", "0001", "Presidente", 1),
        _detalhe_row("AM", "02135", "0020", "0026", "Presidente", 1),
        _detalhe_row("PE", "26000", "0001", "0001", "Presidente", 1),
        _detalhe_row("SP", "71072", "0001", "0001", "Presidente", 1),
    ]
    for secao in ("0001", "0002", "0003"):
        rows.append(_detalhe_row("SP", "50308", "0001", secao, "Presidente", 2))
    return rows


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA br_tse_urna_logs")
    c.execute("CREATE SCHEMA br_tse_eleicoes")
    c.execute(f"CREATE TABLE br_tse_urna_logs.eventos ({EVENTOS_COLUNAS})")
    c.execute(f"CREATE TABLE br_tse_eleicoes.detalhes_votacao_secao ({DETALHE_COLUNAS})")
    c.executemany(f"INSERT INTO br_tse_urna_logs.eventos VALUES ({','.join('?' * 15)})", _eventos())
    c.executemany(
        f"INSERT INTO br_tse_eleicoes.detalhes_votacao_secao VALUES ({','.join('?' * 21)})",
        _detalhe(),
    )
    sqlrun.apply(c, SQL / "views")
    sqlrun.apply(c, SQL / "checks")
    yield c
    c.close()


def _q(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def test_eleicoes_matches_config(con):
    rows = _q(con, "SELECT ano, turno, id_pleito, data FROM main.eleicoes ORDER BY turno")
    esperado = [
        (e.ano, e.turno, e.id_pleito, e.data) for _, e in sorted(config.ELECTIONS.items(), key=lambda kv: kv[0][1])
    ]
    assert rows == esperado


def test_fuso_derived_and_fallback(con):
    rows = _q(con, "SELECT sigla_uf, id_municipio_tse, fuso FROM main.fuso_municipio")
    fuso = {(uf, mun): f for uf, mun, f in rows}
    assert fuso == {
        ("RR", "03085"): -1,  # 4 sections, median of first votes 07:00-07:30 -> -1
        ("RR", "00108"): -1,  # 1 section: state default (derived would be 0)
        ("AC", "01304"): -2,  # 1 section: state default
        ("SP", "50308"): -1,  # 3 sections, derived; state default would be 0
        ("AM", "02135"): -2,  # 1 section, derived -2 is AM's other offset
        ("PE", "26000"): 1,   # 1 section, derived +1 is PE's other offset (Noronha)
        ("SP", "71072"): 0,   # 1 late section, derived +1 is not an SP offset
    }


def test_votos_hora_applies_fuso_and_ignores_other_days(con):
    rows = _q(
        con,
        "SELECT zona, secao, hora_local, hora_brasilia, votos FROM main.votos_hora "
        "WHERE sigla_uf = 'RR' AND id_municipio_tse = '03085' ORDER BY secao",
    )
    assert rows == [
        ("0008", "0001", 7, 8, 5),  # 07:00-07:04 local = 08:00 Brasilia; setup-day 03:00 absent
        ("0008", "0002", 7, 8, 4),
        ("0008", "0003", 7, 8, 6),
        ("0008", "0004", 7, 8, 2),
    ]


def test_votos_hora_single_section_uses_default(con):
    rows = _q(con, "SELECT hora_local, hora_brasilia, votos FROM main.votos_hora WHERE sigla_uf = 'RR' AND id_municipio_tse = '00108'")
    assert rows == [(8, 9, 2)]


def test_votos_hora_uf_rollup(con):
    rows = _q(con, "SELECT sigla_uf, hora_brasilia, votos FROM main.votos_hora_uf ORDER BY sigla_uf, hora_brasilia")
    assert rows == [
        ("AC", 11, 1),
        ("AM", 8, 1),   # 06:01 local at -2
        ("PE", 8, 1),   # 09:00 local at +1
        ("RR", 8, 17),  # 5 + 4 + 6 + 2
        ("RR", 9, 2),
        ("SP", 8, 6),
        ("SP", 9, 1),   # the late section stays at 09:00
    ]


def test_check_comparecimento_statuses(con):
    rows = _q(
        con,
        "SELECT sigla_uf, id_municipio_tse, zona, secao, votos_log, comparecimento, status "
        "FROM main.check_comparecimento ORDER BY sigla_uf, id_municipio_tse, secao",
    )
    assert rows == [
        ("AC", "01304", "0001", "0001", 1, 1, "ok"),
        ("AM", "02135", "0020", "0026", 1, 1, "ok"),
        ("PE", "26000", "0001", "0001", 1, 1, "ok"),
        ("RR", "00108", "0001", "0001", 2, 2, "ok"),
        ("RR", "03085", "0008", "0001", 5, 5, "ok"),  # max over cargos; setup-day vote not counted
        ("RR", "03085", "0008", "0002", 4, 3, "diferente"),
        ("RR", "03085", "0008", "0003", 6, 6, "ok"),
        ("RR", "03085", "0008", "0004", 2, None, "sem_csv"),
        ("RR", "03085", "0008", "0005", None, 5, "sem_log"),  # only setup-day lines in the log
        ("SP", "50308", "0001", "0001", 2, 2, "ok"),
        ("SP", "50308", "0001", "0002", 2, 2, "ok"),
        ("SP", "50308", "0001", "0003", 2, 2, "ok"),
        ("SP", "71072", "0001", "0001", 1, 1, "ok"),
    ]


def test_apply_runs_files_in_name_order(tmp_path):
    c = duckdb.connect(":memory:")
    (tmp_path / "02_b.sql").write_text("CREATE OR REPLACE VIEW v_b AS SELECT * FROM v_a;")
    (tmp_path / "01_a.sql").write_text("CREATE OR REPLACE VIEW v_a AS SELECT 1 AS x;")
    sqlrun.apply(c, tmp_path)
    assert c.execute("SELECT x FROM v_b").fetchall() == [(1,)]
    # Re-running is safe.
    sqlrun.apply(c, tmp_path)


def test_apply_missing_folder_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        sqlrun.apply(duckdb.connect(":memory:"), tmp_path / "nope")


def test_apply_skip_missing(tmp_path):
    (tmp_path / "a.sql").write_text("CREATE VIEW v AS SELECT * FROM nope.missing;")
    con = duckdb.connect()
    with pytest.raises(duckdb.CatalogException):
        sqlrun.apply(con, tmp_path)
    sqlrun.apply(con, tmp_path, skip_missing=True)
