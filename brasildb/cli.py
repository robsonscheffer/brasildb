"""brasildb command line: collect urna logs, load TSE tables, query the lake."""
from __future__ import annotations

import argparse
import asyncio
import functools
import gzip
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pyarrow as pa

from brasildb import config, lake, sqlrun
from brasildb.tse import aux, csv_tables, fetch, logparse, paths, sections

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


def _collected_in_lake(settings, election, done=("ok", "agregada", "sem_log")) -> set[paths.SectionKey]:
    """Sections already written to the lake: the durable record used to resume. A section
    counts by its latest status, so a later run can re-check one."""
    con = lake.connect(settings.lake)
    try:
        rows = con.execute(
            "SELECT lower(sigla_uf), id_municipio_tse, zona, secao FROM br_tse_urna_logs.secoes_coleta "
            "WHERE ano = ? AND turno = ? "
            "QUALIFY row_number() OVER (PARTITION BY sigla_uf, id_municipio_tse, zona, secao "
            "ORDER BY coletado_em DESC) = 1 AND status IN (SELECT unnest(?))",
            [election.ano, election.turno, list(done)]).fetchall()
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
        out.extend(parse_archive(hash_, jez))
    return out


def parse_archive(hash_: str, jez: bytes) -> list[dict]:
    """Event rows of every logd.dat in one -log.jez (a replaced urna's log is nested inside)."""
    out = []
    for membro, logd in logparse.extract_logds(jez):
        rows, _ = logparse.parse_logd_stats(logd)
        for r in rows:
            r.pop("autenticador", None)
            out.append({"arquivo_hash": hash_, "arquivo_membro": membro, **r})
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
    done = _collected_in_lake(s, e, ("ok", "agregada") if a.retry_sem_log else ("ok", "agregada", "sem_log"))
    todo = [x for x in entries if x.key not in done]
    print(f"{len(entries)} sections in scope, {len(todo)} to collect")
    w = BatchWriter(s, e, run_id=f"r{int(time.time())}", size=a.batch)
    parse = functools.partial(parse_section, raw_dir=w.raw_dir)
    counts = asyncio.run(fetch.collect(s, e, todo, w.on_result, resume_from_state=False, parse=parse))
    w.flush()
    dt = time.time() - t0
    print(json.dumps({"counts": counts, "seconds": round(dt, 1), "log_bytes": w.bytes_in,
                      "sections_per_s": round(len(todo) / dt, 2) if dt else None}))


# ---------------------------------------------------------------------------- collect-aux

def _aux_in_lake(settings, election) -> set[paths.SectionKey]:
    """Sections already in totalizacao_secao for this round: the record used to resume."""
    con = lake.connect(settings.lake)
    try:
        rows = con.execute(
            "SELECT DISTINCT lower(sigla_uf), id_municipio_tse, zona, secao "
            "FROM br_tse_eleicoes.totalizacao_secao WHERE ano = ? AND turno = ?",
            [election.ano, election.turno]).fetchall()
    except Exception:  # noqa: BLE001  no table yet
        return set()
    return {paths.SectionKey(*r) for r in rows}


class AuxWriter:
    """Buffers aux.json results and writes totalizacao_secao every `size` sections. A failed
    section is not written, so the next run fetches it again. With keep_raw, each batch's
    aux.json files also go to raw/<ano>/<turno>/aux/<run>-<batch>.jsonl.gz."""

    def __init__(self, settings, election, run_id: str, size: int = 1000):
        self.s, self.e, self.run_id, self.size = settings, election, run_id, size
        self.rows, self.raw, self.pending, self.n_batch = [], [], 0, 0
        self.erros: list[str] = []
        self.raw_dir = Path(settings.raw) / f"{election.ano}" / f"{election.turno}" / "aux" if settings.keep_raw else None

    def on_result(self, res: aux.AuxResult) -> None:
        if res.http_status is None:
            self.erros.append(f"{res.key}: {res.erro}")
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.rows.extend({"ano": self.e.ano, "turno": self.e.turno, **r, "coletado_em": now}
                         for r in aux.aux_rows(res))
        k = res.key
        self.raw.append({"key": [k.sigla_uf, k.id_municipio_tse, k.zona, k.secao],"http_status": res.http_status, "aux": res.aux})
        self.pending += 1
        if self.pending >= self.size:
            self.flush()

    def flush(self) -> None:
        if not self.pending:
            return
        basename = f"{self.run_id}-{self.n_batch:05d}"
        lake.write_table(self.s.lake, "br_tse_eleicoes", "totalizacao_secao",
                         pa.Table.from_pylist(self.rows, arrow_schema("br_tse_eleicoes", "totalizacao_secao")),
                         basename)
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            with gzip.open(self.raw_dir / f"{basename}.jsonl.gz", "wt", encoding="utf-8") as f:
                f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in self.raw)
        self.rows, self.raw, self.pending = [], [], 0
        self.n_batch += 1


def cmd_collect_aux(a) -> None:
    s = config.load()
    e = config.ELECTIONS[(a.ano, a.turno)]
    ufs = sorted({u.lower() for u in a.ufs} or set(config.UFS))
    t0 = time.time()
    by_uf = asyncio.run(_section_lists(s, e, ufs))
    # An aggregated section (cs.json "nsp") has no aux.json of its own; its principal has it.
    keys = sorted(x.key for uf in ufs for x in by_uf[uf] if x.principal is None)
    done = _aux_in_lake(s, e)
    todo = [k for k in keys if k not in done]
    print(f"{len(keys)} sections in scope, {len(todo)} to fetch", flush=True)
    w = AuxWriter(s, e, run_id=f"a{int(time.time())}", size=a.batch)

    def on_result(res: aux.AuxResult) -> None:
        w.on_result(res)
        n = w.n_batch * w.size + w.pending + len(w.erros)
        if n % 10_000 == 0:
            print(f"{n}/{len(todo)} at {n / (time.time() - t0):.1f}/s", flush=True)

    counts = asyncio.run(aux.collect_aux(s, e, todo, on_result))
    w.flush()
    for erro in w.erros[:20]:
        print("erro", erro)
    dt = time.time() - t0
    print(json.dumps({"counts": counts, "seconds": round(dt, 1),
                      "sections_per_s": round(len(todo) / dt, 2) if dt else None}))


# ---------------------------------------------------------------------------- reparse

# A raw file name: the first 12 hex of its aux.json hash, then the TSE name
# o0{pleito}{uf}{municipio}{zona}{secao}-log.jez.
RAW_NAME = re.compile(
    r"^(?P<hash>[0-9a-f]{12})-o0(?P<pleito>\d{4})(?P<uf>[a-z]{2})(?P<mun>\d{5})"
    r"(?P<zona>\d{4})(?P<secao>\d{4})-log\.jez$"
)


def reparse_file(path: str) -> tuple[dict, list[dict]]:
    """Section key and event rows of one raw archive. Module-level: runs in a worker process."""
    m = RAW_NAME.match(os.path.basename(path))
    if not m:
        raise ValueError(f"not a raw log name: {path}")
    key = dict(sigla_uf=m["uf"].upper(), id_municipio_tse=m["mun"], zona=m["zona"], secao=m["secao"])
    return key, parse_archive(m["hash"], Path(path).read_bytes())


def cmd_reparse(a) -> None:
    """Rebuild eventos from the raw archives on disk into another lake, no network.

    Use after a parser change. Writes only br_tse_urna_logs.eventos under --out; copy or move
    the other tables yourself, then point BRASILDB_LAKE at the new lake. arquivo_hash holds the
    12-hex prefix kept in the raw file name."""
    s = config.load()
    e = config.ELECTIONS[(a.ano, a.turno)]
    ufs = [u.lower() for u in a.ufs] or list(config.UFS)
    run_id = f"p{int(time.time())}"
    schema = arrow_schema("br_tse_urna_logs", "eventos")
    t0, total = time.time(), 0
    with ProcessPoolExecutor(s.parse_workers) as pool:
        for uf in ufs:
            raw_dir = Path(s.raw) / str(e.ano) / str(e.turno) / uf
            files = sorted(str(p) for p in raw_dir.glob("*-log.jez"))
            rows, n_batch, n_sec = [], 0, 0
            base = dict(ano=e.ano, turno=e.turno)

            def flush() -> None:
                nonlocal rows, n_batch
                if rows:
                    lake.write_table(a.out, "br_tse_urna_logs", "eventos",
                                     pa.Table.from_pylist(rows, schema), f"{run_id}-{uf}-{n_batch:05d}")
                rows, n_batch = [], n_batch + 1

            for key, evs in pool.map(reparse_file, files, chunksize=4):
                rows.extend({**base, **key, **r} for r in evs)
                n_sec += 1
                if n_sec % a.batch == 0:
                    flush()
            flush()
            total += n_sec
            dt = time.time() - t0
            print(f"{uf}: {n_sec} sections; {total} total at {total / dt:.1f}/s", flush=True)


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
    c.add_argument("--retry-sem-log", action="store_true",
                   help="collect again the sections whose latest status is sem_log")
    c.set_defaults(fn=cmd_collect_logs)

    x = sub.add_parser("collect-aux", help="download each section's aux.json into totalizacao_secao")
    x.add_argument("--ano", type=int, default=2026)
    x.add_argument("--turno", type=int, required=True)
    x.add_argument("--ufs", nargs="*", default=[], help="states to fetch; default all")
    x.add_argument("--batch", type=int, default=1000, help="sections per Parquet write")
    x.set_defaults(fn=cmd_collect_aux)

    r = sub.add_parser("reparse",help="rebuild eventos from the raw archives into another lake")
    r.add_argument("--ano", type=int, default=2026)
    r.add_argument("--turno", type=int, required=True)
    r.add_argument("--ufs", nargs="*", default=[], help="states to reparse; default all")
    r.add_argument("--out", required=True, help="lake to write; a path or s3://bucket/prefix")
    r.add_argument("--batch", type=int, default=200, help="sections per Parquet write")
    r.set_defaults(fn=cmd_reparse)

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
