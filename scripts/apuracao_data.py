"""Build the count night's data files: each candidate's votes in the order the TSE counted them.

  uv run python scripts/apuracao_data.py cache    # lake -> $BRASILDB_DATA/apuracao.duckdb
  uv run python scripts/apuracao_data.py dados    # docs/site/data/apuracao/{brasil.json, mapa.json, mun/<id>.json}

Each section enters the sum at once, with its whole official result (votacao_secao), when the
TSE received its bulletin (boletim_urna_secao, from the TSE BU files); the x axis is the share of
sections counted. scripts/check_count_time.py checks that time against the TSE totalization
panel. (cs.json `ha` is not that time: in 8 states it is one rewrite time for every section.)

Round 2 of 2026, Presidente only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brasildb import config, lake  # noqa: E402

ANO, TURNO, CARGO = 2026, 2, "Presidente"
OUT = ROOT / "docs/site/data/apuracao"
KEYS = "sigla_uf, id_municipio_tse, zona, secao"


def cache_path() -> Path:
    return Path(os.environ.get("BRASILDB_DATA", "data")) / "apuracao.duckdb"


def build_cache(only: list[str] | None = None) -> None:
    """Materialize the inputs of dados() from the lake."""
    con = lake.connect(config.load().lake, str(cache_path()))
    con.execute("SET preserve_insertion_order = false")
    steps = {
        "votacao": f"""
            SELECT {KEYS}, numero_votavel, votos
            FROM br_tse_eleicoes.votacao_secao
            WHERE ano = {ANO} AND turno = {TURNO} AND cargo = '{CARGO}' AND votos > 0""",
        "nomes": f"""
            SELECT numero_votavel, any_value(nome_votavel) AS nome_votavel
            FROM br_tse_eleicoes.votacao_secao
            WHERE ano = {ANO} AND turno = {TURNO} AND cargo = '{CARGO}'
            GROUP BY ALL""",
    }
    if not only or "apuracao" in only:
        apuracao(con)
    for name, sql in steps.items():
        if only and name not in only:
            continue
        t = time.time()
        con.execute(f"CREATE OR REPLACE TABLE c_{name} AS {sql}")
        n = con.execute(f"SELECT count(*) FROM c_{name}").fetchone()[0]
        print(f"c_{name}: {n} rows, {time.time() - t:.0f}s", flush=True)


def apuracao(con: duckdb.DuckDBPyConnection) -> None:
    """c_apuracao: when the TSE received each section's bulletin (boletim_urna_secao
    data_hora_recebimento, Brasilia time), in minutes from election day 00:00."""
    dia = config.ELECTIONS[(ANO, TURNO)].data
    t = time.time()
    con.execute(f"""
        CREATE OR REPLACE TABLE c_apuracao AS
        SELECT {KEYS}, epoch(data_hora_recebimento - TIMESTAMP '{dia} 00:00:00') / 60 AS minuto
        FROM br_tse_eleicoes.boletim_urna_secao
        WHERE ano = {ANO} AND turno = {TURNO} AND data_hora_recebimento IS NOT NULL""")
    n = con.execute("SELECT count(*) FROM c_apuracao").fetchone()[0]
    print(f"c_apuracao: {n} rows, {time.time() - t:.0f}s", flush=True)


PONTOS = 200  # points on the count curve of Brasil and of each state


def ordem(con: duckdb.DuckDBPyConnection) -> None:
    """c_ordem: each section with votes, ranked by when the TSE received its bulletin (Brasil and
    in its state). Exits if a section with votes has no such time."""
    sem = con.execute(f"""
        SELECT count(*) FROM (SELECT DISTINCT {KEYS} FROM c_votacao) s
        ANTI JOIN c_apuracao a USING ({KEYS})""").fetchone()[0]
    if sem:
        sys.exit(f"check failed: {sem} sections with votes have no BU received time")
    con.execute(f"""
        CREATE OR REPLACE TABLE c_ordem AS
        WITH s AS (SELECT DISTINCT {KEYS} FROM c_votacao)
        SELECT {KEYS},
               row_number() OVER (ORDER BY a.minuto, hash({KEYS})) AS ordem_br,
               row_number() OVER (PARTITION BY sigla_uf ORDER BY a.minuto, hash({KEYS})) AS ordem_uf,
               count(*) OVER () AS n_br,
               count(*) OVER (PARTITION BY sigla_uf) AS n_uf
        FROM s JOIN c_apuracao a USING ({KEYS})""")


VOTAVEIS = ["13", "22", "95", "96"]

# The names the page shows, as the candidates are known; votacao_secao has only the civil name.
NOMES = {"13": "Lula", "22": "Bolsonaro"}


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def apuracao_series(con: duckdb.DuckDBPyConnection) -> dict:
    """Votes entering the sum per point (1/PONTOS of the sections), Brasil and per state."""
    rows = con.execute(f"""
        SELECT v.sigla_uf, CAST(floor((o.ordem_br - 1) * {PONTOS} / o.n_br) AS INTEGER),
               CAST(floor((o.ordem_uf - 1) * {PONTOS} / o.n_uf) AS INTEGER), v.numero_votavel, v.votos
        FROM c_votacao v JOIN c_ordem o USING ({KEYS})""").fetchall()
    brasil = {k: [0] * PONTOS for k in VOTAVEIS}
    ufs: dict[str, dict] = {}
    for uf, ib, iu, num, v in rows:
        brasil[num][ib] += v
        ufs.setdefault(uf, {k: [0] * PONTOS for k in VOTAVEIS})[num][iu] += v
    return {"pontos": PONTOS, "brasil": brasil, "ufs": ufs}


PONTOS_MAPA = 400  # finer than the curve, so the map fills city by city


def mapa(con: duckdb.DuckDBPyConnection) -> dict:
    """The count on the map: for each city (not abroad), the points of the Brasil count at which
    its sections enter and the votes of 13 and 22 they bring, flat as [point, 13, 22, ...]. The
    state count is the same order within the state, so `secoes` (sections entering per point, per
    state) turns a Brasil point into the state's share. `n` (sections in the Brasil count, abroad
    too) turns a section's place in that count into a point."""
    rows = con.execute(f"""
        SELECT o.sigla_uf, o.id_municipio_tse,
               CAST(floor((o.ordem_br - 1) * {PONTOS_MAPA} / o.n_br) AS INTEGER) AS p,
               count(DISTINCT (o.zona, o.secao)) AS n,
               coalesce(sum(v.votos) FILTER (WHERE v.numero_votavel = '13'), 0),
               coalesce(sum(v.votos) FILTER (WHERE v.numero_votavel = '22'), 0)
        FROM c_ordem o JOIN c_votacao v USING ({KEYS})
        WHERE o.sigla_uf <> 'ZZ' GROUP BY ALL ORDER BY 2, 3""").fetchall()
    cidades: dict[str, list] = {}
    secoes: dict[str, list] = {}
    for uf, mun, pt, n, a, b in rows:
        cidades.setdefault(mun, []).extend([pt, int(a), int(b)])
        secoes.setdefault(uf, [0] * PONTOS_MAPA)[pt] += n
    n = con.execute("SELECT any_value(n_br) FROM c_ordem").fetchone()[0]
    return {"pontos": PONTOS_MAPA, "n": n, "id": list(cidades), "c": list(cidades.values()),
            "secoes": dict(sorted(secoes.items()))}


def municipios(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    """(UF, city) -> its sections as {"zona-secao": [[votes of 13, 22, 95, 96], place in the
    Brasil count]}; the page orders a city's or zone's sections by that place."""
    votos: dict[tuple, dict] = {}
    for uf, mun, zona, secao, n, v in con.execute("SELECT * FROM c_votacao ORDER BY ALL").fetchall():
        votos.setdefault((uf, mun, zona, secao), {})[n] = v
    out: dict[tuple, dict] = {}
    for uf, mun, zona, secao, lugar in con.execute(
            f"SELECT {KEYS}, ordem_br FROM c_ordem ORDER BY ALL").fetchall():
        v = votos[(uf, mun, zona, secao)]
        out.setdefault((uf, mun), {})[f"{zona}-{secao}"] = [[v.get(n, 0) for n in VOTAVEIS], lugar]
    return out


def dados(con: duckdb.DuckDBPyConnection) -> None:
    civil = dict(con.execute("SELECT * FROM c_nomes").fetchall())
    assert civil["13"].startswith("LUIZ INÁCIO LULA") and civil["22"].endswith("BOLSONARO"), civil
    ordem(con)
    ap = apuracao_series(con)
    oficial = dict(con.execute("SELECT numero_votavel, sum(votos) FROM c_votacao GROUP BY 1").fetchall())
    for n in VOTAVEIS:
        if sum(ap["brasil"][n]) != oficial.get(n, 0):
            sys.exit(f"check failed: the count of {n} ends at {sum(ap['brasil'][n])}, not {oficial.get(n, 0)}")
    base = {"mock": False, "votaveis": VOTAVEIS}
    dump(OUT / "brasil.json", {**base, "nomes": NOMES, "apuracao": ap})
    dump(OUT / "mapa.json", mapa(con))
    mun = municipios(con)
    for (uf, m), secoes in mun.items():
        dump(OUT / "mun" / f"{m}.json", {**base, "uf": uf, "id": m, "secoes": secoes})
    print(f"{len(ap['ufs'])} states, {len(mun)} cities")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cache", "dados"])
    ap.add_argument("--only", nargs="*", help="cache: rebuild only these tables (apuracao votacao nomes)")
    a = ap.parse_args()
    if a.step == "cache":
        build_cache(a.only)
    else:
        dados(duckdb.connect(str(cache_path())))


if __name__ == "__main__":
    main()
