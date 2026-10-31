"""Fetch each section's aux.json (the index of its files) and keep its times, for totalizacao_secao.

aux.json holds, per hash, the time the section entered the official count (dr + hr). The
collector reads the same file to find the logs but does not keep it."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from brasildb.config import Election, Settings
from brasildb.tse.fetch import REQUEST_TIMEOUT, RateLimiter, _Failed, _get
from brasildb.tse.paths import SectionKey, aux_url


@dataclass
class AuxResult:
    key: SectionKey
    http_status: int | None  # None when the request failed for good
    aux: dict | None = None
    erro: str | None = None


def _data_hora(d: str | None, h: str | None) -> datetime | None:
    """'25/10/2026' + '20:23:16' -> datetime; None when either part is missing."""
    if not d or not h:
        return None
    return datetime.strptime(f"{d} {h}", "%d/%m/%Y %H:%M:%S")


def aux_rows(res: AuxResult) -> list[dict]:
    """totalizacao_secao rows of one section, without ano, turno and coletado_em."""
    k = res.key
    base = dict(sigla_uf=k.sigla_uf.upper(), id_municipio_tse=k.id_municipio_tse, zona=k.zona,
                secao=k.secao, http_status=res.http_status)
    aux = res.aux or {}
    base |= dict(situacao_secao=aux.get("st"), data_hora_geracao=_data_hora(aux.get("dg"), aux.get("hg")))
    hashes = aux.get("hashes") or []
    if not hashes:
        return [{**base, "arquivo_hash": None, "situacao": None, "data_hora": None}]
    return [{**base, "arquivo_hash": h.get("hash"), "situacao": h.get("st"),
             "data_hora": _data_hora(h.get("dr"), h.get("hr"))} for h in hashes]


async def fetch_aux(client: httpx.AsyncClient, limiter, base: str, election: Election,
                    key: SectionKey) -> AuxResult:
    try:
        r = await _get(client, limiter, aux_url(base, election.id_pleito, key))
    except _Failed as e:
        return AuxResult(key, None, erro=str(e))
    if r.status_code == 404:
        return AuxResult(key, 404)
    if r.status_code != 200:
        return AuxResult(key, None, erro=f"aux.json HTTP {r.status_code}")
    try:
        return AuxResult(key, 200, r.json())
    except ValueError as e:
        return AuxResult(key, None, erro=f"aux.json not JSON: {e}")


async def collect_aux(settings: Settings, election: Election, keys: list[SectionKey],
                      on_result: Callable[[AuxResult], None]) -> dict[str, int]:
    """Fetch aux.json for every key under the shared rate limit. Returns counts by outcome
    (200, 404, erro). A failed section is passed to on_result with http_status None."""
    todo = iter(keys)
    counts: dict[str, int] = {}
    limiter = RateLimiter(settings.rps)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT,
                                 limits=httpx.Limits(max_connections=settings.concurrency)) as client:

        async def worker() -> None:
            # next() on a plain iterator does not yield to the loop, so workers never race.
            for key in todo:
                res = await fetch_aux(client, limiter, settings.results_base, election, key)
                on_result(res)
                outcome = "erro" if res.http_status is None else str(res.http_status)
                counts[outcome] = counts.get(outcome, 0) + 1

        await asyncio.gather(*(worker() for _ in range(settings.concurrency)))
    return counts
