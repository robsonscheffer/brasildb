"""Fetch tests. All HTTP is mocked with respx; nothing reaches the network."""
from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path

import httpx
import respx

from brasildb import cli
from brasildb.config import ELECTIONS, Settings
from brasildb.tse import fetch
from brasildb.tse.fetch import RateLimiter, StateStore, SectionResult, collect, fetch_section
from brasildb.tse.paths import SectionKey, aux_url, file_url
from brasildb.tse.sections import SectionEntry

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna"
ELECTION = ELECTIONS[(2026, 2)]  # pleito 3221
KEY = SectionKey("rr", "03085", "0008", "0001")
ENTRY = SectionEntry(key=KEY, principal=None, aggregated=())
AUX_URL = aux_url(BASE, ELECTION.id_pleito, KEY)
AUX = json.loads((FIXTURES / "aux_rr_03085_0008_0001.json").read_text())
HASH = AUX["hashes"][0]["hash"]
LOG_NAME = "o03221rr0308500080001-log.jez"
LOG_URL = file_url(BASE, ELECTION.id_pleito, KEY, HASH, LOG_NAME)
LOG_BYTES = (FIXTURES / LOG_NAME).read_bytes()


class NoLimit:
    async def acquire(self) -> None:
        return None


def no_sleep(monkeypatch) -> list[float]:
    """Replace retry backoff with a recorder so retries cost no real time."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(fetch.asyncio, "sleep", fake_sleep)
    return slept


def settings(tmp_path: Path, **over) -> Settings:
    base = dict(
        lake=str(tmp_path / "lake"),
        raw=str(tmp_path / "raw"),
        state=str(tmp_path / "state.sqlite"),
        results_base=BASE,
        rps=1000.0,
        concurrency=4,
        keep_raw=False,
    )
    base.update(over)
    return Settings(**base)


async def test_ok_section_downloads_log(monkeypatch):
    no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=AUX))
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)

    assert result.status == "ok"
    assert result.erro is None
    assert result.logs == [(HASH, LOG_NAME, LOG_BYTES)]
    assert LOG_BYTES.startswith(b"PK")  # the .jez is a ZIP


async def test_aggregated_entry_makes_no_request():
    aggregated = SectionEntry(key=KEY, principal="0001", aggregated=())
    with respx.mock(assert_all_mocked=True) as router:
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, aggregated)
        assert router.calls.call_count == 0
    assert result.status == "agregada"
    assert result.logs == []


async def test_aux_404_is_sem_log_and_not_retried(monkeypatch):
    slept = no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        route = router.get(AUX_URL).mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "sem_log"
    assert route.call_count == 1
    assert slept == []


async def test_503_then_ok_retries_once(monkeypatch):
    slept = no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        route = router.get(AUX_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=AUX)]
        )
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "ok"
    assert route.call_count == 2
    assert slept == [1]


async def test_timeout_is_retried_then_ok(monkeypatch):
    no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(
            side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json=AUX)]
        )
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "ok"


async def test_persistent_503_gives_erro_after_five_attempts_with_backoff(monkeypatch):
    slept = no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        route = router.get(AUX_URL).mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "erro"
    assert "HTTP 503" in result.erro
    assert route.call_count == 5
    assert slept == [1, 2, 4, 8]


async def test_network_error_waits_then_ok(monkeypatch):
    slept = no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(
            side_effect=[httpx.ConnectError("no route"), httpx.Response(200, json=AUX)]
        )
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "ok"
    assert slept == [2]


async def test_long_outage_gives_erro_after_network_backoff(monkeypatch):
    slept = no_sleep(monkeypatch)
    with respx.mock(assert_all_mocked=True) as router:
        route = router.get(AUX_URL).mock(side_effect=httpx.ConnectError("no route"))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "erro"
    assert "network (ConnectError)" in result.erro
    assert route.call_count == len(fetch.NETWORK_RETRY_DELAYS) + 1
    assert slept == list(fetch.NETWORK_RETRY_DELAYS)


async def test_two_hashes_give_two_logs(monkeypatch):
    no_sleep(monkeypatch)
    second = "ab" * 32
    aux = {
        "hashes": [
            {"hash": HASH, "arq": [{"nm": LOG_NAME, "tp": "log"}]},
            {"hash": second, "arq": [{"nm": "o03221rr0308500080001-log.jez", "tp": "log"},
                                      {"nm": "o03221rr0308500080001-vota.vsc", "tp": "vota"}]},
        ]
    }
    second_url = file_url(BASE, ELECTION.id_pleito, KEY, second, LOG_NAME)
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=aux))
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        router.get(second_url).mock(return_value=httpx.Response(200, content=b"second"))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "ok"
    assert [(h, n) for h, n, _ in result.logs] == [(HASH, LOG_NAME), (second, LOG_NAME)]
    assert result.logs[1][2] == b"second"


async def test_unlisted_log_is_fetched_by_its_name(monkeypatch):
    no_sleep(monkeypatch)
    aux = {"hashes": [{"hash": HASH, "arq": [{"nm": "o03221rr0308500080001-bu.dat", "tp": "bu"},
                                             {"nm": "o03221rr0308500080001-vota.vsc", "tp": "vota"}]}]}
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=aux))
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert fetch.log_name(ELECTION.id_pleito, KEY) == LOG_NAME
    assert result.status == "ok"
    assert result.logs == [(HASH, LOG_NAME, LOG_BYTES)]


async def test_unlisted_log_missing_is_sem_log(monkeypatch):
    no_sleep(monkeypatch)
    aux = {"hashes": [{"hash": HASH, "arq": [{"nm": "o03221rr0308500080001-bu.dat", "tp": "bu"}]}]}
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=aux))
        route = router.get(LOG_URL).mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
    assert result.status == "sem_log"
    assert route.call_count == 1


async def test_apuracao_only_section_is_not_probed(monkeypatch):
    no_sleep(monkeypatch)
    aux = {"hashes": [{"hash": HASH, "arq": [{"nm": "o03221rr0308500080001-busa.dat", "tp": "busa"},
                                             {"nm": "o03221rr0308500080001-logsa.jez", "tp": "logsa"}]}]}
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=aux))
        async with httpx.AsyncClient() as client:
            result = await fetch_section(client, NoLimit(), BASE, ELECTION, ENTRY)
        assert router.calls.call_count == 1
    assert result.status == "sem_log"


async def test_rate_limiter_spaces_requests():
    limiter = RateLimiter(rps=50)  # 20 ms apart
    loop = asyncio.get_running_loop()
    stamps = []
    for _ in range(5):
        await limiter.acquire()
        stamps.append(loop.time())
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.02 * 0.9 for g in gaps)


def test_state_store_round_trip_and_resume(tmp_path):
    path = str(tmp_path / "state.sqlite")
    store = StateStore(path)
    ok = SectionResult(ENTRY, "ok", [(HASH, LOG_NAME, LOG_BYTES)])
    agregada = SectionResult(SectionEntry(SectionKey("rr", "03085", "0008", "0002"), "0001", ()), "agregada")
    erro = SectionResult(SectionEntry(SectionKey("rr", "03085", "0008", "0003"), None, ()), "erro", [], "boom")
    store.record(2026, 2, ok)
    store.record(2026, 2, agregada)
    store.record(2026, 2, erro)
    store.record(2026, 1, ok)
    store.close()

    reopened = StateStore(path)  # table and rows survive a new connection
    assert reopened.done(2026, 2) == {ENTRY.key, agregada.entry.key}
    assert reopened.done(2026, 1) == {ENTRY.key}
    reopened.close()


async def test_collect_counts_skips_done_and_records(tmp_path, monkeypatch):
    no_sleep(monkeypatch)
    cfg = settings(tmp_path)
    ok_key = KEY
    sem_key = SectionKey("rr", "03085", "0008", "0009")
    agg_key = SectionKey("rr", "03085", "0008", "0010")
    done_key = SectionKey("rr", "03085", "0008", "0011")
    entries = [
        ENTRY,
        SectionEntry(sem_key, None, ()),
        SectionEntry(agg_key, "0001", ()),
        SectionEntry(done_key, None, ()),
    ]
    # Mark one section done from an earlier run: it must not be requested again.
    store = StateStore(cfg.state)
    store.record(2026, 2, SectionResult(SectionEntry(done_key, None, ()), "sem_log"))
    store.close()

    seen: list[SectionResult] = []
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=AUX))
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        router.get(aux_url(BASE, ELECTION.id_pleito, entries[1].key)).mock(return_value=httpx.Response(404))
        counts = await collect(cfg, ELECTION, entries, seen.append)
        assert router.calls.call_count == 3  # aux + log for ok, aux for sem_log; none for done/agregada

    assert counts == {"ok": 1, "sem_log": 1, "agregada": 1}
    assert sorted(r.status for r in seen) == ["agregada", "ok", "sem_log"]
    assert {r.entry.key for r in seen} == {ok_key, sem_key, agg_key}

    # Resume: everything is recorded now, so a second run does nothing.
    with respx.mock(assert_all_mocked=True) as router:
        again = await collect(cfg, ELECTION, entries, seen.append)
        assert router.calls.call_count == 0
    assert again == {}


async def test_collect_parses_in_worker_processes(tmp_path, monkeypatch):
    no_sleep(monkeypatch)
    cfg = settings(tmp_path, parse_workers=2)
    seen: list[SectionResult] = []
    with respx.mock(assert_all_mocked=True) as router:
        router.get(AUX_URL).mock(return_value=httpx.Response(200, json=AUX))
        router.get(LOG_URL).mock(return_value=httpx.Response(200, content=LOG_BYTES))
        parse = functools.partial(cli.parse_section, raw_dir=str(tmp_path / "raw"))
        await collect(cfg, ELECTION, [ENTRY], seen.append, parse=parse)
    [result] = seen
    assert result.parsed == cli.parse_section(result, None)
    assert result.parsed and {r["arquivo_hash"] for r in result.parsed} == {HASH}
    assert (tmp_path / "raw" / "rr" / f"{HASH[:12]}-{LOG_NAME}").read_bytes() == LOG_BYTES


def test_resume_uses_latest_status_and_can_retry_sem_log(tmp_path):
    import pyarrow as pa
    from datetime import datetime

    from brasildb import lake

    s = settings(tmp_path)
    other = SectionKey("rr", "03085", "0008", "0002")
    rows = [dict(ano=2026, turno=2, sigla_uf=k.sigla_uf.upper(), id_municipio_tse=k.id_municipio_tse,
                 zona=k.zona, secao=k.secao, secao_principal=None, status=st, n_hashes=0, erro=None,
                 coletado_em=datetime(2026, 10, 26, h))
            for k, st, h in [(KEY, "erro", 1), (KEY, "ok", 2), (other, "sem_log", 1)]]
    lake.write_table(s.lake, "br_tse_urna_logs", "secoes_coleta",
                     pa.Table.from_pylist(rows, cli.arrow_schema("br_tse_urna_logs", "secoes_coleta")), "t")
    assert cli._collected_in_lake(s, ELECTION) == {KEY, other}
    assert cli._collected_in_lake(s, ELECTION, ("ok", "agregada")) == {KEY}
