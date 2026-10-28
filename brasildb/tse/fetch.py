"""Fetch each section's urna log files from the results site, with one shared rate limit and resume."""
from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from brasildb.config import Election, Settings
from brasildb.tse.paths import SectionKey, aux_url, file_url
from brasildb.tse.sections import SectionEntry

# Sleep before each retry. One attempt, then one retry per value: 5 attempts in all.
RETRY_DELAYS: tuple[float, ...] = (1, 2, 4, 8)
# Network errors (no route, DNS, reset) wait about 5 minutes in all, so a short outage
# pauses the run instead of marking every section it reaches as erro.
NETWORK_RETRY_DELAYS: tuple[float, ...] = (2, 5, 10, 20, 30, 60, 60, 60, 60)
REQUEST_TIMEOUT = 30.0
DONE_STATUSES = ("ok", "agregada", "sem_log")


class RateLimiter:
    """Starts requests at least 1/rps apart. Share one instance across all workers."""

    def __init__(self, rps: float):
        if rps <= 0:
            raise ValueError("rps must be positive")
        self._interval = 1.0 / rps
        self._next = 0.0

    async def acquire(self) -> None:
        # No await between reading and writing self._next, so this is safe for many tasks.
        loop = asyncio.get_running_loop()
        now = loop.time()
        start = max(now, self._next)
        self._next = start + self._interval
        if start > now:
            await asyncio.sleep(start - now)


@dataclass
class SectionResult:
    entry: SectionEntry
    status: str  # ok | agregada | sem_log | erro
    logs: list[tuple[str, str, bytes]] = field(default_factory=list)  # (hash, file name, bytes)
    erro: str | None = None


class _Failed(Exception):
    """A request that failed for good: retries used up."""


async def _get(client: httpx.AsyncClient, limiter: RateLimiter, url: str) -> httpx.Response:
    """GET under the shared limiter. Timeouts, 5xx and network errors are retried; any other
    status is returned."""
    retries = {"server": 0, "network": 0}
    while True:
        await limiter.acquire()
        try:
            response = await client.get(url)
        except httpx.TimeoutException as e:
            kind, problema = "server", f"timeout ({type(e).__name__})"
        except httpx.TransportError as e:
            kind, problema = "network", f"network ({type(e).__name__})"
        else:
            if response.status_code < 500:
                return response
            kind, problema = "server", f"HTTP {response.status_code}"
        delays = RETRY_DELAYS if kind == "server" else NETWORK_RETRY_DELAYS
        if retries[kind] == len(delays):
            raise _Failed(f"{problema} after {sum(retries.values()) + 1} attempts: {url}")
        await asyncio.sleep(delays[retries[kind]])
        retries[kind] += 1


def _log_files(aux: dict) -> list[tuple[str, str]]:
    """(hash, file name) for every log in the section index, across all hashes."""
    found = []
    for h in aux.get("hashes", []):
        for arq in h.get("arq", []):
            nome = arq.get("nm", "")
            if arq.get("tp") == "log" or nome.endswith("-log.jez"):
                found.append((h["hash"], nome))
    return found


def _erro(entry: SectionEntry, mensagem: str) -> SectionResult:
    return SectionResult(entry, "erro", [], mensagem)


async def fetch_section(
    client: httpx.AsyncClient,
    limiter: RateLimiter,
    base: str,
    election: Election,
    entry: SectionEntry,
) -> SectionResult:
    # An aggregated entry (cs.json "nsp") has no files of its own; its principal holds them.
    if entry.principal is not None:
        return SectionResult(entry, "agregada")
    key = entry.key
    try:
        aux = await _get(client, limiter, aux_url(base, election.id_pleito, key))
        if aux.status_code == 404:
            return SectionResult(entry, "sem_log")
        if aux.status_code != 200:
            return _erro(entry, f"aux.json HTTP {aux.status_code}")
        arquivos = _log_files(aux.json())
        if not arquivos:
            return SectionResult(entry, "sem_log")
        logs = []
        for hash_, nome in arquivos:
            url = file_url(base, election.id_pleito, key, hash_, nome)
            response = await _get(client, limiter, url)
            if response.status_code != 200:
                return _erro(entry, f"{nome} HTTP {response.status_code}")
            logs.append((hash_, nome, response.content))
        return SectionResult(entry, "ok", logs)
    except _Failed as e:
        return _erro(entry, str(e))
    except Exception as e:  # any other failure is recorded, not raised
        return _erro(entry, f"{type(e).__name__}: {e}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS secoes_coleta (
    ano INTEGER NOT NULL,
    turno INTEGER NOT NULL,
    sigla_uf TEXT NOT NULL,
    id_municipio_tse TEXT NOT NULL,
    zona TEXT NOT NULL,
    secao TEXT NOT NULL,
    secao_principal TEXT,
    status TEXT NOT NULL,
    n_hashes INTEGER NOT NULL,
    erro TEXT,
    coletado_em TEXT NOT NULL,
    PRIMARY KEY (ano, turno, sigla_uf, id_municipio_tse, zona, secao)
)
"""


class StateStore:
    """SQLite record of which sections are collected, one row per section per round."""

    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._con = sqlite3.connect(path)
        with self._con:
            self._con.execute(SCHEMA)

    def done(self, ano: int, turno: int) -> set[SectionKey]:
        rows = self._con.execute(
            "SELECT sigla_uf, id_municipio_tse, zona, secao FROM secoes_coleta "
            "WHERE ano = ? AND turno = ? AND status IN ('ok', 'agregada', 'sem_log')",
            (ano, turno),
        ).fetchall()
        return {SectionKey(uf.lower(), municipio, zona, secao) for uf, municipio, zona, secao in rows}

    def record(self, ano: int, turno: int, result: SectionResult) -> None:
        k = result.entry.key
        n_hashes = len({h for h, _, _ in result.logs})
        with self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO secoes_coleta VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ano,
                    turno,
                    k.sigla_uf.upper(),
                    k.id_municipio_tse,
                    k.zona,
                    k.secao,
                    result.entry.principal,
                    result.status,
                    n_hashes,
                    result.erro,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )

    def close(self) -> None:
        self._con.close()


async def collect(
    settings: Settings,
    election: Election,
    entries: list[SectionEntry],
    on_result: Callable[[SectionResult], None],
    resume_from_state: bool = True,
) -> dict[str, int]:
    """Fetch every section not yet done. Returns the count of each status seen in this run.

    Pass resume_from_state=False when the caller already filtered entries against a more
    durable record (the CLI uses the lake, since buffered rows are lost if a run dies)."""
    store = StateStore(settings.state)
    try:
        done = store.done(election.ano, election.turno) if resume_from_state else set()
        todo = iter([e for e in entries if e.key not in done])
        counts: dict[str, int] = {}
        limiter = RateLimiter(settings.rps)

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_connections=settings.concurrency),
        ) as client:

            async def worker() -> None:
                # next() on a plain iterator does not yield to the loop, so workers never race.
                for entry in todo:
                    result = await fetch_section(client, limiter, settings.results_base, election, entry)
                    on_result(result)
                    store.record(election.ano, election.turno, result)
                    counts[result.status] = counts.get(result.status, 0) + 1

            await asyncio.gather(*(worker() for _ in range(settings.concurrency)))
        return counts
    finally:
        store.close()
