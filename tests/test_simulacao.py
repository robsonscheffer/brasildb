"""The simulated day: each section's result spread over its own voting hours, summed upward."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

spec = importlib.util.spec_from_file_location(
    "simulacao_data", Path(__file__).parents[1] / "scripts" / "simulacao_data.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def _con():
    con = duckdb.connect()
    con.execute("""CREATE TABLE c_votos_hora AS SELECT * FROM (VALUES
        ('RR', '03085', '0008', '0001', 8, 30), ('RR', '03085', '0008', '0001', 9, 10),
        ('RR', '03085', '0008', '0002', 9, 5), ('RR', '03085', '0008', '0002', 10, 15))
        AS t(sigla_uf, id_municipio_tse, zona, secao, hora, votos)""")
    # 0001 and 0002 have logs; 0003 has none and takes the city's hours.
    con.execute("""CREATE TABLE c_votacao AS SELECT * FROM (VALUES
        ('RR', '03085', '0008', '0001', '13', 30), ('RR', '03085', '0008', '0001', '22', 10),
        ('RR', '03085', '0008', '0002', '13', 4), ('RR', '03085', '0008', '0002', '22', 16),
        ('RR', '03085', '0008', '0003', '13', 6))
        AS t(sigla_uf, id_municipio_tse, zona, secao, numero_votavel, votos)""")
    con.execute("""CREATE TABLE c_principal (sigla_uf VARCHAR, id_municipio_tse VARCHAR,
        zona VARCHAR, secao VARCHAR, secao_principal VARCHAR)""")
    sim.simular(con)
    return con


def test_each_section_ends_at_its_official_result():
    con = _con()
    assert sim.check(con) == []


def test_a_section_spreads_its_result_by_its_own_hours():
    con = _con()
    rows = con.execute("""SELECT hora, votos FROM c_sim
        WHERE secao = '0001' AND numero_votavel = '13' ORDER BY hora""").fetchall()
    assert rows == [(8, 22.5), (9, 7.5)]  # 30 votes, 3/4 of the log at 8h


def test_a_section_without_a_log_takes_its_city_hours():
    con = _con()
    fonte, = con.execute("SELECT DISTINCT fonte FROM c_peso WHERE secao = '0003'").fetchone()
    assert fonte == "cidade"
    rows = con.execute("SELECT hora, votos FROM c_sim WHERE secao = '0003' ORDER BY hora").fetchall()
    assert rows == [(8, 3.0), (9, 1.5), (10, 1.5)]  # city log: 30, 15, 15 of 60


def test_the_sum_moves_when_places_vote_at_different_hours():
    con = _con()
    share = dict(con.execute("""SELECT hora, sum(votos) FILTER (WHERE numero_votavel = '13') / sum(votos)
        FROM c_sim WHERE secao IN ('0001', '0002') GROUP BY hora""").fetchall())
    assert share[8] > share[10]


def test_the_count_orders_sections_by_bu_received_time():
    con = _con()
    con.execute("""CREATE TABLE c_apuracao AS SELECT * FROM (VALUES
        ('RR', '03085', '0008', '0001', 1230.0), ('RR', '03085', '0008', '0002', 1201.5),
        ('RR', '03085', '0008', '0003', 1215.0))
        AS t(sigla_uf, id_municipio_tse, zona, secao, minuto)""")
    assert sim.ordem(con) == 0
    rows = con.execute("SELECT secao, ordem_br FROM c_ordem ORDER BY ordem_br").fetchall()
    assert rows == [("0002", 1), ("0003", 2), ("0001", 3)]


def test_the_count_stops_when_a_section_with_votes_has_no_bu_time():
    con = _con()
    con.execute("""CREATE TABLE c_apuracao AS SELECT * FROM (VALUES
        ('RR', '03085', '0008', '0001', 1230.0), ('RR', '03085', '0008', '0002', 1201.5))
        AS t(sigla_uf, id_municipio_tse, zona, secao, minuto)""")
    with pytest.raises(SystemExit, match="1 sections with votes have no BU received time"):
        sim.ordem(con)
