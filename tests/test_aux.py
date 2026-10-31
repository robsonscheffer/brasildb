"""aux.json -> totalizacao_secao. All HTTP is mocked with respx; nothing reaches the network."""
from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path

import httpx
import respx

from brasildb import cli, lake
from brasildb.config import ELECTIONS
from brasildb.tse import aux, fetch
from brasildb.tse.paths import SectionKey, aux_url
from tests.test_fetch import BASE, FIXTURES, settings

ELECTION = ELECTIONS[(2026, 2)]
KEY = SectionKey("rr", "03085", "0008", "0001")
KEY_404 = SectionKey("rr", "03123", "0007", "0012")
AUX = json.loads((FIXTURES / "aux_rr_03085_0008_0001.json").read_text())


def test_rows_of_one_hash():
    rows = aux.aux_rows(aux.AuxResult(KEY, 200, AUX))
    assert rows == [{
        "sigla_uf": "RR", "id_municipio_tse": "03085", "zona": "0008", "secao": "0001",
        "http_status": 200, "situacao_secao": "Totalizada",
        "data_hora_geracao": datetime(2026, 10, 25, 23, 27, 22),
        "arquivo_hash": AUX["hashes"][0]["hash"], "situacao": "Totalizado",
        "data_hora": datetime(2026, 10, 25, 19, 37, 13),
    }]


def test_a_replaced_urna_gives_one_row_per_hash():
    two = {**AUX, "hashes": [AUX["hashes"][0], {"hash": "ab", "dr": "25/10/2026", "hr": "21:00:05",
                                                "st": "Totalizado", "arq": []}]}
    rows = aux.aux_rows(aux.AuxResult(KEY, 200, two))
    assert [r["arquivo_hash"] for r in rows] == [AUX["hashes"][0]["hash"], "ab"]
    assert rows[1]["data_hora"] == datetime(2026, 10, 25, 21, 0, 5)


def test_a_404_section_has_one_row_without_hash():
    [row] = aux.aux_rows(aux.AuxResult(KEY_404, 404))
    assert row["http_status"] == 404
    assert row["arquivo_hash"] is None and row["data_hora"] is None and row["situacao_secao"] is None


async def test_collect_aux_reports_each_outcome(tmp_path: Path, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(fetch.asyncio, "sleep", no_sleep)
    bad = SectionKey("rr", "03085", "0008", "0002")
    got = []
    with respx.mock(assert_all_mocked=True) as router:
        router.get(aux_url(BASE, ELECTION.id_pleito, KEY)).mock(return_value=httpx.Response(200, json=AUX))
        router.get(aux_url(BASE, ELECTION.id_pleito, KEY_404)).mock(return_value=httpx.Response(404))
        router.get(aux_url(BASE, ELECTION.id_pleito, bad)).mock(return_value=httpx.Response(503))
        counts = await aux.collect_aux(settings(tmp_path), ELECTION, [KEY, KEY_404, bad], got.append)
    assert counts == {"200": 1, "404": 1, "erro": 1}
    by_key = {r.key: r for r in got}
    assert by_key[bad].http_status is None and "503" in by_key[bad].erro


def test_writer_skips_failures_and_keeps_raw(tmp_path: Path):
    s = settings(tmp_path, keep_raw=True)
    w = cli.AuxWriter(s, ELECTION, run_id="t", size=10)
    w.on_result(aux.AuxResult(KEY, 200, AUX))
    w.on_result(aux.AuxResult(KEY_404, 404))
    w.on_result(aux.AuxResult(SectionKey("rr", "03085", "0008", "0002"), None, erro="timeout"))
    w.flush()

    con = lake.connect(s.lake)
    rows = con.execute("SELECT secao, http_status, data_hora FROM br_tse_eleicoes.totalizacao_secao "
                       "ORDER BY secao").fetchall()
    assert rows == [("0001", 200, datetime(2026, 10, 25, 19, 37, 13)), ("0012", 404, None)]
    assert cli._aux_in_lake(s, ELECTION) == {KEY, KEY_404}
    assert len(w.erros) == 1
    raw = Path(s.raw) / "2026" / "2" / "aux" / "t-00000.jsonl.gz"
    lines = [json.loads(x) for x in gzip.open(raw, "rt", encoding="utf-8")]
    assert [x["http_status"] for x in lines] == [200, 404]
    assert lines[0]["aux"] == AUX
