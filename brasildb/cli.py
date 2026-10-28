"""brasildb command line: collect urna logs, load TSE tables, query the lake."""
from __future__ import annotations

import argparse
import asyncio
import functools
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pyarrow as pa

from brasildb import config, lake, sqlrun
from brasildb.tse import csv_tables, fetch, logparse, paths, sections

ROOT = Path(__file__).resolve().parent.parent
CKAN_CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
ARROW_TYPES = {
    "VARCHAR": pa.string(), "INTEGER": pa.int32(), "BIGINT": pa.int64(),
    "TIMESTAMP": pa.timestamp("us"), "DATE": pa.date32(), "BOOLEAN": pa.bool_(),
}


def arrow_schema(dataset: str, table: str) -> pa.Schema:
    cols = lake.load_catalog()[dataset][table]["columns"]
    return pa.schema([(name, ARROW_TYPES[typ]) for name, typ in cols.items()])


# ---------------------------------------------------------------------------- collect-logs

async def _section_lists(settings, election, ufs):
    limiter = fetch.RateLimiter(settings.rps)
    out = {}
    async with httpx.AsyncClient(timeout=60) as client:
        for uf in ufs:
            await limiter.acquire()
            r = await client.get(paths.cs_url(settings.results_base, uf, election.id_pleito))
            r.raise_for_status()
            out[uf] = sections.parse_cs(r.json(), uf)
    return out


def _collected_in_lake(settings, election) -> set[paths.SectionKey]:
    """Sections already written to the lake: the durable record used to resume."""
    con = lake.connect(settings.lake)
    try:
        rows = con.execute(
            "SELECT lower(sigla_uf), id_municipio_tse, zona, secao FROM br_tse_urna_logs.secoes_coleta "
            "WHERE ano = ? AND turno = ? AND status IN ('ok', 'agregada', 'sem_log')",
            [election.ano, election.turno]).fetchall()
    except Exception:  # noqa: BLE001  no table yet
        return set()
    return {paths.SectionKey(*r) for r in rows}


def parse_section(res: fetch.SectionResult, raw_dir: str | None) -> list[dict]:
    """Event rows of one section's logs. Saves each raw archive under raw_dir/<uf> when given.
    Runs in a worker process during collection, so it is a module-level function."""
    out = []
    for hash_, name, jez in res.logs:
        if raw_dir:
            d = Path(raw_dir) / res.entry.key.sigla_uf
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{hash_[:12]}-{name}").write_bytes(jez)
        rows, _ = logparse.parse_logd_stats(logparse.extract_logd(jez))
        for r in rows:
            r.pop("autenticador", None)
            out.append({"arquivo_hash": hash_, **r})
    return out


class BatchWriter:
    """Buffers parsed sections and writes them to the lake every `size` sections."""

    def __init__(self, settings, election, run_id: str, size: int = 200):
        self.s, self.e, self.run_id, self.size = settings, election, run_id, size
        self.eventos, self.secoes, self.n_batch, self.pending = [], [], 0, 0
        self.bytes_in = 0
        self.raw_dir = str(Path(settings.raw) / f"{election.ano}" / f"{election.turno}") if settings.keep_raw else None

    def on_result(self, res: fetch.SectionResult) -> None:
        k = res.entry.key
        base = dict(ano=self.e.ano, turno=self.e.turno, sigla_uf=k.sigla_uf.upper(),
                    id_municipio_tse=k.id_municipio_tse, zona=k.zona, secao=k.secao)
        rows = res.parsed if res.parsed is not None else parse_section(res, self.raw_dir)
        self.bytes_in += sum(len(jez) for _, _, jez in res.logs)
        self.eventos.extend({**base, **r} for r in rows)
        self.secoes.append({**base, "secao_principal": res.entry.principal, "status": res.status,
                            "n_hashes": len(res.logs), "erro": res.erro,
                            "coletado_em": datetime.now(timezone.utc).replace(tzinfo=None)})
        self.pending += 1
        if self.pending >= self.size:
            self.flush()

    def flush(self) -> None:
        if not self.pending:
            return
        basename = f"{self.run_id}-{self.n_batch:05d}"
        if self.eventos:
            lake.write_table(self.s.lake, "br_tse_urna_logs", "eventos",
                             pa.Table.from_pylist(self.eventos, arrow_schema("br_tse_urna_logs", "eventos")),
                             basename)
        lake.write_table(self.s.lake, "br_tse_urna_logs", "secoes_coleta",
                         pa.Table.from_pylist(self.secoes, arrow_schema("br_tse_urna_logs", "secoes_coleta")),
                         basename)
        self.eventos, self.secoes, self.pending = [], [], 0
        self.n_batch += 1


def _municipio_ufs(settings, codes: list[str]) -> dict[str, str]:
    """TSE municipality code -> lower-case state, from the loaded municipio table."""
    codes = [c.zfill(5) for c in codes]
    con = lake.connect(settings.lake)
    try:
        rows = con.execute(
            "SELECT id_municipio_tse, lower(sigla_uf) FROM br_bd_diretorios_brasil.municipio "
            "WHERE id_municipio_tse IN (SELECT unnest(?))", [codes]).fetchall()
    except Exception as exc:  # noqa: BLE001  no table yet
        raise SystemExit("municipio table missing: run `brasildb load-municipios` first") from exc
    found = dict(rows)
    if missing := sorted(set(codes) - set(found)):
        raise SystemExit(f"unknown TSE municipality codes: {', '.join(missing)}")
    return found


def cmd_collect_logs(a) -> None:
    s = config.load()
    e = config.ELECTIONS[(a.ano, a.turno)]
    full = {u.lower() for u in a.ufs}
    municipios = _municipio_ufs(s, a.municipios) if a.municipios else {}
    if a.sample_fraction:
        scope = sorted(set(config.UFS))
    else:
        scope = sorted(full | set(municipios.values()))
    t0 = time.time()
    by_uf = asyncio.run(_section_lists(s, e, scope))
    if a.sample_fraction:
        entries = sections.sample_sections(by_uf, a.sample_fraction, a.seed, full)
    else:
        entries = [x for uf in full for x in by_uf[uf]]
    entries += [x for uf in set(municipios.values()) - full for x in by_uf[uf]
                if x.key.id_municipio_tse in municipios]
    entries = sorted(set(entries), key=lambda x: x.key)
    done = _collected_in_lake(s, e)
    todo = [x for x in entries if x.key not in done]
    print(f"{len(entries)} sections in scope, {len(todo)} to collect")
    w = BatchWriter(s, e, run_id=f"r{int(time.time())}", size=a.batch)
    parse = functools.partial(parse_section, raw_dir=w.raw_dir)
    counts = asyncio.run(fetch.collect(s, e, todo, w.on_result, resume_from_state=False, parse=parse))
    w.flush()
    dt = time.time() - t0
    print(json.dumps({"counts": counts, "seconds": round(dt, 1), "log_bytes": w.bytes_in,
                      "sections_per_s": round(len(todo) / dt, 2) if dt else None}))


# ---------------------------------------------------------------------------- loaders

def cmd_load_turnout(a) -> None:
    s = config.load()
    for member in a.members:  # e.g. BR, RR
        name = f"detalhe_votacao_secao_{a.ano}_{member.upper()}.csv"
        url = f"{CKAN_CDN}/detalhe_votacao_secao/detalhe_votacao_secao_{a.ano}.zip"
        path = csv_tables.fetch_zip_member(url, name, f"{s.raw}/ckan")
        lake.write_table(s.lake, "br_tse_eleicoes", "detalhes_votacao_secao",
                         csv_tables.read_detalhe_votacao_secao(str(path)), f"detalhe-{member.upper()}")
        print(f"loaded {name}")


def cmd_load_municipios(a) -> None:
    s = config.load()
    path = csv_tables.fetch_zip_member(f"{CKAN_CDN}/municipio_tse_ibge/municipio_tse_ibge.zip",
                                       "municipio_tse_ibge.csv", f"{s.raw}/ckan")
    lake.write_table(s.lake, "br_bd_diretorios_brasil", "municipio",
                     csv_tables.read_municipio(str(path)), "municipio")
    print("loaded municipio")


# ---------------------------------------------------------------------------- query

def open_db(settings=None):
    s = settings or config.load()
    con = lake.connect(s.lake)
    sqlrun.apply(con, ROOT / "sql" / "views", skip_missing=True)
    sqlrun.apply(con, ROOT / "sql" / "checks", skip_missing=True)
    return con


def cmd_sql(a) -> None:
    con = open_db()
    query = a.query or sys.stdin.read()
    rel = con.sql(query)
    if rel is not None:
        rel.show(max_rows=a.max_rows)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="brasildb")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect-logs", help="download and parse urna logs into the lake")
    c.add_argument("--ano", type=int, default=2026)
    c.add_argument("--turno", type=int, required=True)
    c.add_argument("--ufs", nargs="*", default=[], help="states collected in full, e.g. rr")
    c.add_argument("--municipios", nargs="*", default=[],
                   help="TSE municipality codes collected in full, e.g. 85367 (needs load-municipios)")
    c.add_argument("--sample-fraction", type=float, default=0.0,
                   help="also take this fraction of sections from every other state")
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--batch", type=int, default=200, help="sections per Parquet write")
    c.set_defaults(fn=cmd_collect_logs)

    t = sub.add_parser("load-turnout", help="load detalhe_votacao_secao from CKAN")
    t.add_argument("--ano", type=int, default=2026)
    t.add_argument("--members", nargs="+", default=["BR"], help="BR (president) and/or UF codes")
    t.set_defaults(fn=cmd_load_turnout)

    m = sub.add_parser("load-municipios", help="load the TSE to IBGE municipality codes")
    m.set_defaults(fn=cmd_load_municipios)

    q = sub.add_parser("sql", help="run SQL over the lake (views and checks loaded)")
    q.add_argument("query", nargs="?")
    q.add_argument("--max-rows", type=int, default=50)
    q.set_defaults(fn=cmd_sql)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
