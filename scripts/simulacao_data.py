"""Build the simulated day's data files: each candidate's votes spread over the hours (Brasilia).

  uv run python scripts/simulacao_data.py cache    # lake -> $BRASILDB_DATA/simulacao.duckdb (full eventos scan, minutes)
  uv run python scripts/simulacao_data.py dados    # docs/site/data/simulacao/{brasil.json, uf/<UF>.json, mun/<id>.json}

The count (apuracao) is not simulated: each section enters the TSE sum at its `ha` time
(cs.json, Brasilia), with its whole official result.

The vote is secret: an urna logs when each vote was cast, never for whom. The model spreads each
section's official result (votacao_secao) over the hours in which that section voted (its urna
log), so within one section every hour votes alike. Zones, cities, states and Brasil are sums of
sections; their shares move only because places that vote differently vote at different hours.
A section without its own log takes the hours of its principal section (an aggregated section),
then its city's, then its state's. Every scale ends the day at the official totals.

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

from brasildb import config, lake, sqlrun  # noqa: E402

ANO, TURNO, CARGO = 2026, 2, "Presidente"
OUT = ROOT / "docs/site/data/simulacao"
KEYS = "sigla_uf, id_municipio_tse, zona, secao"


def cache_path() -> Path:
    return Path(os.environ.get("BRASILDB_DATA", "data")) / "simulacao.duckdb"


def build_cache(only: list[str] | None = None) -> None:
    """Materialize the three inputs of simular(). votos_hora reads every vote line in eventos."""
    con = lake.connect(config.load().lake, str(cache_path()))
    con.execute("SET preserve_insertion_order = false")
    sqlrun.apply(con, ROOT / "sql/views", skip_missing=True)
    steps = {
        "votos_hora": f"""
            SELECT v.sigla_uf, v.id_municipio_tse, v.zona, v.secao,
                   CAST(floor((hour(v.data_hora) * 60 + minute(v.data_hora) - f.fuso_minutos) / 60)
                        AS INTEGER) AS hora,
                   count(*) AS votos
            FROM main.votos v
            JOIN main.fuso_municipio f
              ON f.ano = v.ano AND f.turno = v.turno
             AND f.sigla_uf = v.sigla_uf AND f.id_municipio_tse = v.id_municipio_tse
            WHERE v.ano = {ANO} AND v.turno = {TURNO}
            GROUP BY ALL""",
        "votacao": f"""
            SELECT {KEYS}, numero_votavel, votos
            FROM br_tse_eleicoes.votacao_secao
            WHERE ano = {ANO} AND turno = {TURNO} AND cargo = '{CARGO}' AND votos > 0""",
        "nomes": f"""
            SELECT numero_votavel, any_value(nome_votavel) AS nome_votavel
            FROM br_tse_eleicoes.votacao_secao
            WHERE ano = {ANO} AND turno = {TURNO} AND cargo = '{CARGO}'
            GROUP BY ALL""",
        "principal": f"""
            SELECT {KEYS}, any_value(secao_principal) AS secao_principal
            FROM br_tse_urna_logs.secoes_coleta
            WHERE ano = {ANO} AND turno = {TURNO} AND secao_principal IS NOT NULL
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
    """c_apuracao: the minute each section was first counted (cs.json `ha`), Brasilia time,
    in minutes from election day 00:00. Aggregated sections (nsp) have none; the CSV reports
    their votes under the principal section."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import pyarrow as pa
    from site_v2_data import cs_sections

    from datetime import datetime

    dia = config.ELECTIONS[(ANO, TURNO)].data
    rows = []
    for r in cs_sections():
        if r["ha"] and r["da"]:
            h, m, _ = r["ha"].split(":")
            rows.append({"sigla_uf": r["uf"].upper(), "id_municipio_tse": r["mun"].zfill(5),
                         "zona": r["zona"], "secao": r["secao"],
                         "minuto": (datetime.strptime(r["da"], "%d/%m/%Y").date() - dia).days * 1440
                                   + int(h) * 60 + int(m)})
    con.register("cs_rows", pa.Table.from_pylist(rows))
    con.execute("CREATE OR REPLACE TABLE c_apuracao AS SELECT * FROM cs_rows")
    print(f"c_apuracao: {len(rows)} rows", flush=True)


PASSO = 5  # minutes per count bucket


SIMULAR_SQL = f"""
CREATE OR REPLACE TABLE c_peso AS
WITH secoes AS (SELECT DISTINCT {KEYS} FROM c_votacao),
proprio AS (SELECT {KEYS}, hora, votos / sum(votos) OVER (PARTITION BY {KEYS}) AS peso
            FROM c_votos_hora WHERE votos > 0),
cidade AS (SELECT sigla_uf, id_municipio_tse, hora,
                  sum(votos) / sum(sum(votos)) OVER (PARTITION BY sigla_uf, id_municipio_tse) AS peso
           FROM c_votos_hora GROUP BY sigla_uf, id_municipio_tse, hora),
estado AS (SELECT sigla_uf, hora, sum(votos) / sum(sum(votos)) OVER (PARTITION BY sigla_uf) AS peso
           FROM c_votos_hora GROUP BY sigla_uf, hora),
com_log AS (SELECT DISTINCT {KEYS} FROM proprio),
cidades AS (SELECT DISTINCT sigla_uf, id_municipio_tse FROM cidade),
fonte AS (
    SELECT s.*, p.secao_principal,
           CASE WHEN l.secao IS NOT NULL THEN 'log'
                WHEN lp.secao IS NOT NULL THEN 'principal'
                WHEN c.id_municipio_tse IS NOT NULL THEN 'cidade'
                ELSE 'estado' END AS fonte
    FROM secoes s
    LEFT JOIN com_log l USING ({KEYS})
    LEFT JOIN c_principal p USING ({KEYS})
    LEFT JOIN com_log lp ON lp.sigla_uf = s.sigla_uf AND lp.id_municipio_tse = s.id_municipio_tse
                        AND lp.zona = s.zona AND lp.secao = p.secao_principal
    LEFT JOIN cidades c ON c.sigla_uf = s.sigla_uf AND c.id_municipio_tse = s.id_municipio_tse
)
SELECT f.sigla_uf, f.id_municipio_tse, f.zona, f.secao, f.fonte, w.hora, w.peso
FROM fonte f JOIN proprio w USING ({KEYS}) WHERE f.fonte = 'log'
UNION ALL
SELECT f.sigla_uf, f.id_municipio_tse, f.zona, f.secao, f.fonte, w.hora, w.peso
FROM fonte f JOIN proprio w ON w.sigla_uf = f.sigla_uf AND w.id_municipio_tse = f.id_municipio_tse
                           AND w.zona = f.zona AND w.secao = f.secao_principal
WHERE f.fonte = 'principal'
UNION ALL
SELECT f.sigla_uf, f.id_municipio_tse, f.zona, f.secao, f.fonte, w.hora, w.peso
FROM fonte f JOIN cidade w USING (sigla_uf, id_municipio_tse) WHERE f.fonte = 'cidade'
UNION ALL
SELECT f.sigla_uf, f.id_municipio_tse, f.zona, f.secao, f.fonte, w.hora, w.peso
FROM fonte f JOIN estado w USING (sigla_uf) WHERE f.fonte = 'estado';

CREATE OR REPLACE TABLE c_sim AS
SELECT p.sigla_uf, p.id_municipio_tse, p.zona, p.secao, p.hora, v.numero_votavel,
       v.votos * p.peso AS votos
FROM c_peso p JOIN c_votacao v USING ({KEYS});
"""


def simular(con: duckdb.DuckDBPyConnection) -> None:
    """c_votos_hora, c_votacao, c_principal -> c_peso (section x hour shares) and c_sim."""
    con.execute(SIMULAR_SQL)


def check(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Each section's simulated day must end at its official result, and every section counts."""
    erros = []
    falta = con.execute(f"""
        SELECT count(*) FROM (SELECT DISTINCT {KEYS} FROM c_votacao)
        ANTI JOIN (SELECT DISTINCT {KEYS} FROM c_peso) USING ({KEYS})""").fetchone()[0]
    if falta:
        erros.append(f"{falta} sections have no hours")
    diff = con.execute(f"""
        SELECT max(abs(s.votos - v.votos)) FROM
          (SELECT {KEYS}, numero_votavel, sum(votos) AS votos FROM c_sim GROUP BY ALL) s
        JOIN c_votacao v USING ({KEYS}, numero_votavel)""").fetchone()[0]
    if diff is None or diff > 1e-6:
        erros.append(f"a section's day ends {diff} votes off its official result")
    return erros


VOTAVEIS = ["13", "22", "95", "96"]


def _series(rows, horas: list[int]) -> dict[str, list[int]]:
    """rows of (hora, numero, votos) -> {numero: votes per hour}, rounded per hour."""
    idx = {h: i for i, h in enumerate(horas)}
    out = {n: [0.0] * len(horas) for n in VOTAVEIS}
    for h, n, v in rows:
        out[n][idx[h]] += v
    # Round the running total, not each hour, so the day ends at the official total.
    res = {}
    for n, vs in out.items():
        acc, prev, res[n] = 0.0, 0, []
        for x in vs:
            acc += x
            res[n].append(round(acc) - prev)
            prev = round(acc)
    return res


def _grouped(con, cols: str, where: str = "TRUE") -> dict[tuple, list]:
    rows = con.execute(f"""
        SELECT {cols}, hora, numero_votavel, sum(votos) FROM c_sim WHERE {where}
        GROUP BY ALL ORDER BY ALL""").fetchall()
    k = len(cols.split(","))
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault(tuple(r[:k]), []).append(r[k:])
    return out


# The names the page shows, as the candidates are known; votacao_secao has only the civil name.
NOMES = {"13": "Lula", "22": "Bolsonaro"}


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def apuracao_series(con: duckdb.DuckDBPyConnection) -> dict:
    """Votes entering the TSE sum per PASSO-minute bucket, Brasil and per state (not simulated)."""
    sem = con.execute("""SELECT count(*) FROM (SELECT DISTINCT sigla_uf, id_municipio_tse, zona, secao
        FROM c_votacao) ANTI JOIN c_apuracao USING (sigla_uf, id_municipio_tse, zona, secao)""").fetchone()[0]
    if sem:
        sys.exit(f"check failed: {sem} sections with votes have no count time")
    rows = con.execute(f"""
        SELECT v.sigla_uf, CAST(floor(a.minuto / {PASSO}) * {PASSO} AS INTEGER) AS b, v.numero_votavel,
               sum(v.votos)
        FROM c_votacao v JOIN c_apuracao a USING (sigla_uf, id_municipio_tse, zona, secao)
        GROUP BY ALL""").fetchall()
    ini, fim = min(r[1] for r in rows), max(r[1] for r in rows)
    n = (fim - ini) // PASSO + 1
    brasil = {k: [0] * n for k in VOTAVEIS}
    ufs: dict[str, dict] = {}
    for uf, b, num, v in rows:
        i = (b - ini) // PASSO
        brasil[num][i] += v
        ufs.setdefault(uf, {k: [0] * n for k in VOTAVEIS})[num][i] += v
    return {"passo": PASSO, "inicio": ini, "brasil": brasil, "ufs": ufs}


def dados(con: duckdb.DuckDBPyConnection) -> None:
    horas = [h for (h,) in con.execute("SELECT DISTINCT hora FROM c_sim ORDER BY 1").fetchall()]
    base = {"mock": False, "simulacao": True, "hora": "Brasília", "horas": horas,
            "votaveis": VOTAVEIS}
    civil = dict(con.execute("SELECT * FROM c_nomes").fetchall())
    assert civil["13"].startswith("LUIZ INÁCIO LULA") and civil["22"].endswith("BOLSONARO"), civil
    brasil = _series(con.execute("SELECT hora, numero_votavel, sum(votos) FROM c_sim GROUP BY ALL")
                     .fetchall(), horas)
    ufs = {k[0]: _series(v, horas) for k, v in _grouped(con, "sigla_uf").items()}
    dump(OUT / "brasil.json", {**base, "nomes": NOMES, "brasil": brasil, "ufs": ufs,
                               "apuracao": apuracao_series(con)})
    for uf in ufs:
        cidades = {k[0]: _series(v, horas)
                   for k, v in _grouped(con, "id_municipio_tse", f"sigla_uf = '{uf}'").items()}
        dump(OUT / "uf" / f"{uf}.json", {**base, "uf": uf, "cidades": cidades})
    # One file per city: zone curves, and each section's official result and hourly shares, so
    # the page draws a section (flat shares) without one curve per section in the file.
    # A section's hours are its log's vote counts (any weights in proportion), as
    # [first hour index, counts...]; a section without its own log gets its source's shares x 10000.
    pesos: dict[tuple, dict] = {}
    for uf_, mun, zona, secao, fonte, hora, peso in con.execute(f"""
            SELECT p.sigla_uf, p.id_municipio_tse, p.zona, p.secao, p.fonte, p.hora,
                   CASE WHEN p.fonte = 'log' THEN h.votos ELSE round(p.peso * 10000) END
            FROM c_peso p LEFT JOIN c_votos_hora h
              ON p.fonte = 'log' AND h.sigla_uf = p.sigla_uf AND h.id_municipio_tse = p.id_municipio_tse
             AND h.zona = p.zona AND h.secao = p.secao AND h.hora = p.hora
            ORDER BY ALL""").fetchall():
        e = pesos.setdefault((uf_, mun, zona, secao), {"fonte": fonte, "h": {}})
        e["h"][horas.index(hora)] = int(peso)
    votos: dict[tuple, dict] = {}
    for uf_, mun, zona, secao, n, v in con.execute(
            "SELECT * FROM c_votacao ORDER BY ALL").fetchall():
        votos.setdefault((uf_, mun, zona, secao), {})[n] = v
    zonas = _grouped(con, "sigla_uf, id_municipio_tse, zona")
    por_mun: dict[tuple, dict] = {}
    for (uf_, mun, zona), rows in zonas.items():
        por_mun.setdefault((uf_, mun), {"zonas": {}, "secoes": {}})["zonas"][zona] = _series(rows, horas)
    minuto = {tuple(r[:4]): r[4] for r in con.execute("SELECT * FROM c_apuracao").fetchall()}
    for (uf_, mun, zona, secao), e in pesos.items():
        v = votos.get((uf_, mun, zona, secao), {})
        i0, i1 = min(e["h"]), max(e["h"])
        por_mun[(uf_, mun)]["secoes"][f"{zona}-{secao}"] = [
            e["fonte"], [v.get(n, 0) for n in VOTAVEIS], i0, [e["h"].get(i, 0) for i in range(i0, i1 + 1)],
            minuto.get((uf_, mun, zona, secao))]
    for (uf_, mun), m in por_mun.items():
        dump(OUT / "mun" / f"{mun}.json", {**base, "uf": uf_, "id": mun, **m})
    print(f"{len(ufs)} states, {len(por_mun)} cities, hours {horas[0]}..{horas[-1]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cache", "dados"])
    ap.add_argument("--only", nargs="*", help="cache: rebuild only these tables (apuracao votos_hora votacao nomes principal)")
    a = ap.parse_args()
    if a.step == "cache":
        build_cache(a.only)
    else:
        con = duckdb.connect(str(cache_path()))
        simular(con)
        erros = check(con)
        if erros:
            sys.exit("check failed: " + "; ".join(erros))
        print(con.execute("SELECT fonte, count(DISTINCT (sigla_uf, id_municipio_tse, zona, secao)) "
                          "FROM c_peso GROUP BY 1 ORDER BY 2 DESC").fetchall())
        dados(con)


if __name__ == "__main__":
    main()
