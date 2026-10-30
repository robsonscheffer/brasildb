"""Build the v2 walk's data files from the lake (P4). Same paths and shapes as the mock.

  uv run python scripts/site_v2_data.py cache          # once: lake views -> $BRASILDB_DATA/site_v2.duckdb
  uv run python scripts/site_v2_data.py curiosidades   # docs/site/v2/data/curiosidades.json
  uv run python scripts/site_v2_data.py chegada        # docs/site/v2/data/chegada.json
  uv run python scripts/site_v2_data.py cidades        # docs/site/v2/data/cidades/<UF>.json

Round 2 of 2026 only. Every time is Brasilia time (P4 D4). Every file carries "mock": false.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brasildb import config, lake, sqlrun  # noqa: E402
from brasildb.tse.paths import SectionKey, aux_url  # noqa: E402

ANO, TURNO = 2026, 2
OUT = ROOT / "docs/site/v2/data"


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str))
    print(f"{path.relative_to(ROOT)}: {path.stat().st_size} bytes")


def cache_path() -> Path:
    return Path(os.environ.get("BRASILDB_DATA", "data")) / "site_v2.duckdb"


def build_cache(only: list[str] | None = None) -> None:
    """Materialize the views the facts read. The full eventos scan takes minutes; the facts
    then run in seconds. Rerun after the lake changes."""
    path = cache_path()
    con = lake.connect(config.load().lake, str(path))
    con.execute("SET preserve_insertion_order = false")
    sqlrun.apply(con, ROOT / "sql/views", skip_missing=True)
    steps = {
        "fuso": f"SELECT * FROM main.fuso_municipio WHERE ano = {ANO} AND turno = {TURNO}",
        "votos_minuto": f"SELECT * FROM main.votos_minuto WHERE ano = {ANO} AND turno = {TURNO}",
        "secao": f"SELECT * FROM main.secao_dia WHERE ano = {ANO} AND turno = {TURNO}",
        "aptos": f"""SELECT sigla_uf, id_municipio_tse, zona, secao, aptos, comparecimento
                     FROM br_tse_eleicoes.detalhes_votacao_secao
                     WHERE ano = {ANO} AND turno = {TURNO} AND cargo ILIKE 'presidente'""",
        "coleta": f"""SELECT sigla_uf, id_municipio_tse, zona, secao, status
                      FROM br_tse_urna_logs.secoes_coleta WHERE ano = {ANO} AND turno = {TURNO}""",
        "fim_log": FIM_LOG_SQL,
    }
    for name, sql in steps.items():
        if only and name not in only:
            continue
        t = time.time()
        con.execute(f"CREATE OR REPLACE TABLE c_{name} AS {sql}")
        n = con.execute(f"SELECT count(*) FROM c_{name}").fetchone()[0]
        print(f"c_{name}: {n} rows, {time.time() - t:.0f}s", flush=True)
    r2_views(con)


DIA = "2026-10-25"
SOLIMOES = ["1300060", "1300201", "1300607", "1301605", "1302306", "1303700", "1303908",
            "1304062", "1304237"]  # IBGE microregion 13003 Alto Solimoes (servicodados.ibge.gov.br)
PAIS = {  # time zone -> country, only for cities a fact names; a miss fails loudly
    "Pacific/Auckland": "Nova Zelândia", "Australia/Sydney": "Austrália", "Asia/Tokyo": "Japão",
    "America/Los_Angeles": "Estados Unidos", "America/Vancouver": "Canadá",
    "America/New_York": "Estados Unidos", "America/Chicago": "Estados Unidos",
    "Europe/Lisbon": "Portugal", "America/Guatemala": "Guatemala", "America/Mexico_City": "México",
}
UFNOME = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
          "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
          "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
          "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná",
          "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima",
          "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
          "TO": "Tocantins"}


def nome_pt(n: str) -> str:
    """'Rio De Janeiro' -> 'Rio de Janeiro': articles and 'e' lower case inside a name."""
    w = n.split(" ")
    return " ".join(x.lower() if k and x in ("De", "Do", "Da", "Dos", "Das", "E", "D'") else x
                    for k, x in enumerate(w))


def em(uf: str) -> str:
    """'no Rio de Janeiro', 'na Bahia', 'em São Paulo'."""
    na = {"BA", "PB"}
    sem = {"SP", "MG", "PE", "AL", "SE", "GO", "SC", "RO", "RR"}
    p = "na" if uf in na else "em" if uf in sem else "no"
    return f"{p} {UFNOME[uf]}"


def fmt(n: float) -> str:
    return f"{round(n):,}".replace(",", ".")


def hfala(t: str) -> str:
    """'16:04' or '16:04:31' -> '16h04'; '17:00' -> '17h'."""
    h, m = t.split(":")[:2]
    return f"{int(h)}h" if m == "00" else f"{int(h)}h{m}"


def hora(ts) -> str:
    return ts.strftime("%H:%M:%S")


def dia_label(ts) -> str:
    """A Brasilia timestamp the day before the vote reads 'sábado, 16h04'."""
    return ("sábado, " if str(ts.date()) < DIA else "") + hfala(hora(ts))


class Fatos:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.towns = json.loads((ROOT / "docs/site/data/towns.json").read_text())
        self.coord = {(u, i): (la, lo) for u, i, la, lo in zip(
            self.towns["uf"], self.towns["id"], self.towns["lat"], self.towns["lon"])}
        self.nomes = dict(((u, i), nome_pt(n)) for u, i, n in con.execute(
            "SELECT sigla_uf, id_municipio_tse, nome FROM br_bd_diretorios_brasil.municipio").fetchall())
        for i, n, tz in con.execute("SELECT id_municipio_tse, nome, tz FROM main.fuso_exterior").fetchall():
            self.nomes[("ZZ", i)] = (nome_pt(n.title()), tz)
        self.itens: list[dict] = []

    def q(self, sql: str) -> list[tuple]:
        return self.con.execute(sql).fetchall()

    def lugar(self, uf, mun=None, zona=None, secao=None) -> dict:
        out = {"uf": uf}
        if mun:
            if uf == "ZZ":
                nome, tz = self.nomes[(uf, mun)]
                if tz not in PAIS:
                    raise KeyError(f"PAIS needs a country for {tz} ({nome})")
                out.update(municipio=nome, pais=PAIS[tz])
            else:
                out["municipio"] = self.nomes[(uf, mun)]
                if (uf, mun) in self.coord:
                    out["lat"], out["lon"] = self.coord[(uf, mun)]
            out["id_municipio_tse"] = mun
        if zona:
            out["zona"], out["secao"] = zona, secao
        return out

    def onde(self, l: dict) -> str:
        if l["uf"] == "ZZ":
            return f"{l['municipio']}, {l['pais']}"
        return f"{l['municipio']}, {l['uf']}" if "municipio" in l else UFNOME.get(l["uf"], "Brasil")

    def add(self, id, tela, titulo, texto, hora_, lugar, valor, sql, certo=True):
        self.itens.append({"id": id, "tela": tela, "titulo": titulo, "texto": texto, "hora": hora_,
                           "lugar": lugar, "valor": valor, "certo": certo, "sql": " ".join(sql.split())})


VOTO_BSB = f"""
SELECT e.sigla_uf, e.id_municipio_tse, e.zona, e.secao, e.linha,
       e.data_hora - to_minutes(f.fuso_minutos) AS hora_bsb
FROM main.votos e
JOIN r2.fuso_municipio f USING (sigla_uf, id_municipio_tse)
WHERE e.ano = {ANO} AND e.turno = {TURNO}"""
ORDEM = "hora_bsb, sigla_uf, id_municipio_tse, zona, secao, linha"  # P4 D3


def voto_extremo(f: Fatos, onde: str, desc: bool) -> tuple:
    """First (or last) vote under D3 order. The section table narrows the scan to the sections
    whose first (last) vote is the extreme second; eventos then breaks the tie by line."""
    col, agg = ("ultimo_voto", "max") if desc else ("primeiro_voto", "min")
    alvo = f"(SELECT {agg}({col}) FROM r2.secao_dia WHERE {onde})"
    keys = f"SELECT sigla_uf, id_municipio_tse, zona, secao FROM r2.secao_dia WHERE {onde} AND {col} = {alvo}"
    d = " DESC" if desc else ""
    sql = (f"WITH v AS ({VOTO_BSB}) SELECT * FROM v WHERE (sigla_uf, id_municipio_tse, zona, secao) IN ({keys}) "
           f"AND hora_bsb = {alvo} ORDER BY {', '.join(c + d for c in ORDEM.split(', '))} LIMIT 1")
    return f.q(sql)[0], sql


def curiosidades(con: duckdb.DuckDBPyConnection) -> dict:
    f = Fatos(con)
    BR, ZZ = "sigla_uf <> 'ZZ'", "sigla_uf = 'ZZ'"

    # The total is the TSE's official turnout; the log misses the sections without a log.
    sql = """SELECT sum(a.comparecimento) FILTER (WHERE a.sigla_uf <> 'ZZ'), sum(a.comparecimento) FILTER (WHERE a.sigla_uf = 'ZZ'),
                    sum(a.comparecimento), count(DISTINCT a.id_municipio_tse) FILTER (WHERE a.sigla_uf = 'ZZ' AND a.comparecimento > 0),
                    (SELECT sum(votos) FROM r2.secao_dia)
             FROM r2.aptos a"""
    br, zz, tot, cidades_zz, log = f.q(sql)[0]
    f.add("total", 1, f"{fmt(tot)} votos",
          f"{fmt(br)} no Brasil e {fmt(zz)} em {cidades_zz} cidades no exterior, segundo o TSE. "
          f"Os logs das urnas registram {fmt(log)} deles com hora.",
          None, {"uf": "BR"}, tot, sql)

    (uf, mun, z, s, _, t), sql = voto_extremo(f, "true", False)
    l = f.lugar(uf, mun, z, s)
    fm = f.q(f"SELECT fuso_minutos FROM r2.fuso_municipio WHERE sigla_uf = '{uf}' AND id_municipio_tse = '{mun}'")[0][0]
    local = t + timedelta(minutes=fm)
    f.add("primeiro_voto", 2, "O primeiro voto da eleição",
          f"Em {f.onde(l)}, às {hfala(hora(local))} de domingo. Em Brasília, era {dia_label(t)}.",
          hora(t), l, None, sql)
    f.itens[-1]["hora_local"] = hora(local)

    sql = f"""SELECT sum(votos), count(DISTINCT id_municipio_tse) FROM r2.votos_minuto
              WHERE {ZZ} AND minuto_bsb < TIMESTAMP '{DIA} 08:00:00'"""
    n_antes, c_antes = f.q(sql)[0]
    f.add("exterior_antes", 2, "Antes de o Brasil abrir",
          f"Quando as urnas do Brasil abriram, às 8h, {fmt(n_antes)} brasileiros já tinham votado em {c_antes} cidades no exterior.",
          "08:00", {"uf": "ZZ"}, n_antes, sql)

    (uf, mun, z, s, _, t), sql = voto_extremo(f, BR, False)
    l = f.lugar(uf, mun, z, s)
    seg = t.hour * 3600 + t.minute * 60 + t.second - 8 * 3600
    f.add("primeiro_voto_brasil", 2, "O primeiro voto no Brasil",
          f"{seg} segundos depois das 8h, em {f.onde(l)}.", hora(t), l, seg, sql)

    sql = f"SELECT count(*) FILTER (WHERE abertura >= TIMESTAMP '{DIA} 08:00:00' AND abertura < TIMESTAMP '{DIA} 08:01:00'), count(*) FILTER (WHERE abertura < TIMESTAMP '{DIA} 08:00:00'), count(*) FROM r2.secao_dia WHERE {BR}"
    no_minuto, antes, n_br = f.q(sql)[0]
    f.add("abertura_tie", 2, "Todas abriram juntas",
          f"{fmt(no_minuto)} urnas abriram no minuto das 8h." + (" Nenhuma antes." if antes == 0 else f" {fmt(antes)} antes."),
          "08:00", {"uf": "BR"}, no_minuto, sql)

    sql = f"SELECT strftime(min(abertura), '%H:%M'), strftime(median(abertura), '%H:%M') FROM r2.secao_dia WHERE sigla_uf = 'AC'"
    ac_min, ac_med = f.q(sql)[0]
    f.add("abertura", 3, "O país abre de uma vez",
          "No mesmo minuto, de Brasília ao Acre, onde ainda eram 6h da manhã.",
          "08:00", {"uf": "BR"}, n_br, sql)
    f.itens[-1]["nota"] = f"Abertura no Acre, hora de Brasília: primeira {ac_min}, mediana {ac_med}."

    sql = "SELECT minuto_bsb, sum(votos) v FROM r2.votos_minuto GROUP BY 1 ORDER BY v DESC, minuto_bsb LIMIT 1"
    m, v = f.q(sql)[0]
    f.add("pico", 3, "O pico", f"{fmt(v)} votos em um minuto.", m.strftime("%H:%M"), {"uf": "BR"}, v, sql)

    sql = f"""WITH c AS (SELECT sigla_uf, id_municipio_tse, minuto_bsb,
                sum(votos) OVER (PARTITION BY sigla_uf, id_municipio_tse ORDER BY minuto_bsb) acc,
                sum(votos) OVER (PARTITION BY sigla_uf, id_municipio_tse) tot FROM r2.votos_minuto WHERE {BR})
              SELECT sigla_uf, id_municipio_tse, min(minuto_bsb) m, any_value(tot) FROM c
              WHERE tot >= 1000 AND acc >= tot / 2.0 GROUP BY 1, 2 ORDER BY m, 1, 2 LIMIT 1"""
    uf, mun, m, tot_c = f.q(sql)[0]
    l = f.lugar(uf, mun)
    f.add("metade_primeira", 4, f"{l['municipio']}, metade às {hfala(m.strftime('%H:%M'))}",
          f"A primeira cidade com mais de mil eleitores a chegar à metade dos votos. {fmt(tot_c)} votos no dia.",
          m.strftime("%H:%M"), l, tot_c, sql)

    sql = f"""SELECT sigla_uf, sum(votos) FILTER (WHERE hour(minuto_bsb) = 11) h11,
                     sum(votos) FILTER (WHERE hour(minuto_bsb) = 12) h12
              FROM r2.votos_minuto WHERE {BR} AND CAST(minuto_bsb AS DATE) = DATE '{DIA}' GROUP BY 1 ORDER BY 1"""
    rows = f.q(sql)
    cai = [(u, h12 / h11) for u, h11, h12 in rows if h11]
    cai.sort(key=lambda x: x[1])
    n_cai = sum(1 for _, r in cai if r < 1)
    br11, br12 = sum(r[1] for r in rows), sum(r[2] for r in rows)
    sobe = [UFNOME[u] for u, r in cai if r >= 1]
    f.add("almoco", 4, "Na hora do almoço, o país desacelera",
          f"Das 12h às 13h, {fmt(br12)} votos, contra {fmt(br11)} das 11h às 12h. "
          + (f"{n_cai} de {len(cai)} estados votaram menos." if sobe else "Todos os estados votaram menos.")
          + (f" Só {', '.join(sobe)} votaram mais." if 0 < len(sobe) <= 3 else ""),
          "12:00", {"uf": "BR"}, round(100 * (1 - br12 / br11)), sql)

    ids = ", ".join(f"'{x}'" for x in SOLIMOES)
    sql = f"""WITH m AS (SELECT id_municipio_tse FROM br_bd_diretorios_brasil.municipio WHERE id_municipio IN ({ids})),
              v AS (SELECT minuto_bsb, sum(votos) votos FROM r2.votos_minuto JOIN m USING (id_municipio_tse)
                    WHERE sigla_uf = 'AM' GROUP BY 1),
              c AS (SELECT minuto_bsb, sum(votos) OVER (ORDER BY minuto_bsb) acc, sum(votos) OVER () tot FROM v)
              SELECT min(minuto_bsb), any_value(tot) FROM c WHERE acc >= 0.9 * tot"""
    m, tot_s = f.q(sql)[0]
    sql_br = f"""WITH v AS (SELECT minuto_bsb, sum(votos) votos FROM r2.votos_minuto WHERE {BR} GROUP BY 1),
                 c AS (SELECT minuto_bsb, sum(votos) OVER (ORDER BY minuto_bsb) acc, sum(votos) OVER () tot FROM v)
                 SELECT min(minuto_bsb) FROM c WHERE acc >= 0.9 * tot"""
    m_br = f.q(sql_br)[0][0]
    # The local clock of most of the nine towns (by town count): polls open at 8h Brasilia.
    sql_fu = f"""SELECT fuso_minutos, count(*) n FROM r2.fuso_municipio WHERE sigla_uf = 'AM' AND id_municipio_tse IN
                 (SELECT id_municipio_tse FROM br_bd_diretorios_brasil.municipio WHERE id_municipio IN ({ids}))
                 GROUP BY 1 ORDER BY n DESC LIMIT 1"""
    fu, n_fu = f.q(sql_fu)[0]
    if n_fu * 2 <= len(SOLIMOES):
        raise ValueError("no local clock holds most of Alto Solimões; rewrite the solimoes line")
    local = m + timedelta(minutes=fu)
    f.add("solimoes", 4, f"Alto Solimões, 90% às {hfala(m.strftime('%H:%M'))}",
          f"Nos nove municípios do Alto Solimões, no Amazonas, nove em cada dez eleitores já tinham votado. "
          f"O Brasil só chegou lá às {hfala(m_br.strftime('%H:%M'))}. Na maioria deles, o relógio local marcava "
          f"{hfala(local.strftime('%H:%M'))}: a urna abriu às {8 + fu // 60}h da manhã.",
          m.strftime("%H:%M"), {"uf": "AM", "municipio": "Alto Solimões", "lat": -4.25, "lon": -69.94}, tot_s,
          sql + " ; " + sql_br + " ; " + sql_fu)

    sql = f"""SELECT s.sigla_uf, s.id_municipio_tse, s.zona, s.secao, s.votos, a.aptos
              FROM r2.secao_dia s JOIN r2.aptos a USING (sigla_uf, id_municipio_tse, zona, secao)
              WHERE s.votos = a.aptos ORDER BY s.votos DESC, 1, 2, 3, 4 LIMIT 1"""
    uf, mun, z, s, v, ap = f.q(sql)[0]
    l = f.lugar(uf, mun, z, s)
    f.add("secao_cheia", 4, f"{v} de {ap}", f"Em {f.onde(l)}, a maior seção do país em que todos os eleitores votaram.",
          None, l, v, sql)

    tot1e8 = 100_000_000
    sql_m = f"""WITH c AS (SELECT minuto_bsb, sum(votos) v FROM r2.votos_minuto GROUP BY 1),
                a AS (SELECT minuto_bsb, v, sum(v) OVER (ORDER BY minuto_bsb) acc FROM c)
                SELECT minuto_bsb, acc - v FROM a WHERE acc >= {tot1e8} ORDER BY minuto_bsb LIMIT 1"""
    m, antes_m = f.q(sql_m)[0]
    k = tot1e8 - antes_m
    sql = (f"WITH v AS ({VOTO_BSB}) SELECT * FROM v WHERE date_trunc('minute', hora_bsb) = TIMESTAMP '{m}' "
           f"ORDER BY {ORDEM} LIMIT 1 OFFSET {k - 1}")
    uf, mun, z, s, _, t = f.q(sql)[0]
    l = f.lugar(uf, mun, z, s)
    f.add("cem_milhoes", 4, "100 milhões de votos", f"O voto de número 100.000.000 entrou às {hfala(hora(t))}, em {f.onde(l)}.",
          hora(t), l, tot1e8, sql_m + " ; " + sql)

    sql = f"""SELECT sigla_uf, id_municipio_tse, zona, secao, abertura, primeiro_voto,
                     epoch(primeiro_voto - abertura) / 60 espera
              FROM r2.secao_dia WHERE {BR} AND votos > 0 AND abertura IS NOT NULL
              ORDER BY espera DESC, 1, 2, 3, 4 LIMIT 1"""
    uf, mun, z, s, ab, pv, esp = f.q(sql)[0]
    l = f.lugar(uf, mun, z, s)
    f.add("espera", 4, f"{int(esp // 60)} horas sem ninguém" if esp >= 120 else f"{round(esp)} minutos sem ninguém",
          f"Em {f.onde(l)}, a urna abriu às {hfala(hora(ab))}. O primeiro eleitor votou às {hfala(hora(pv))}.",
          hora(pv), l, round(esp), sql)

    sql = f"""SELECT count(*) FILTER (WHERE quedas > 0), count(*) FROM r2.secao_dia WHERE {BR}"""
    n_q, n_all = f.q(sql)[0]
    sql2 = f"""SELECT sigla_uf, id_municipio_tse, zona, secao, min_bateria FROM r2.secao_dia
               WHERE {BR} ORDER BY min_bateria DESC, 1, 2, 3, 4 LIMIT 1"""
    uf, mun, z, s, mb = f.q(sql2)[0]
    l = f.lugar(uf, mun, z, s)
    horas_b = mb / 60
    f.add("sem_luz", 5, "A luz caiu. A eleição não parou",
          f"{fmt(n_q)} urnas passaram para a bateria em algum momento do dia. Toda urna tem bateria própria. "
          f"Em {f.onde(l)}, uma delas votou {int(horas_b)} horas e {round(mb % 60)} minutos na bateria."
          if horas_b >= 1 else f"{fmt(n_q)} urnas passaram para a bateria em algum momento do dia.",
          None, {"uf": "BR"}, n_q, sql + " ; " + sql2)

    sql = f"""SELECT sigla_uf, id_municipio_tse, hour(primeira_queda) h, count(*) n FROM r2.secao_dia
              WHERE {BR} AND quedas > 0 AND min_bateria >= 10 GROUP BY 1, 2, 3 ORDER BY n DESC, 1, 2, 3 LIMIT 1"""
    uf, mun, h, n = f.q(sql)[0]
    l = f.lugar(uf, mun)
    f.add("bateria_cidade", 5, f"{l['municipio']}, {n} urnas na bateria",
          f"Entre {h}h e {h + 1}h, {n} urnas de {l['municipio']} ficaram ao menos dez minutos na bateria. A votação seguiu.",
          f"{h:02d}:00", l, n, sql)

    sql = f"""SELECT count(*) FILTER (WHERE n_logs > 1), count(*) FILTER (WHERE contingencia) FROM r2.secao_dia WHERE {BR}"""
    n2, nc = f.q(sql)[0]
    f.add("trocadas", 5, "Urnas trocadas", f"Em {fmt(n2)} seções, uma urna substituiu outra durante o dia.",
          None, {"uf": "BR"}, n2, sql)

    f.add("fechamento", 8, "Os portões fecham", "Quem já estava na fila ainda vota.", "17:00", {"uf": "BR"}, None,
          "-- rule: polls close at 17:00 Brasilia; no query")

    sql = f"""SELECT sigla_uf, id_municipio_tse, max(encerramento) fim, count(*) n FROM r2.secao_dia
              WHERE {BR} AND encerramento IS NOT NULL GROUP BY 1, 2 ORDER BY fim, 1, 2 LIMIT 1"""
    uf, mun, fim, n = f.q(sql)[0]
    l = f.lugar(uf, mun)
    f.add("primeira_fim", 8, "A primeira cidade a terminar",
          f"Em {f.onde(l)}, {'a única seção' if n == 1 else f'as {n} seções'} já tinha{'' if n == 1 else 'm'} encerrado às {hora(fim)}.",
          hora(fim)[:5], l, n, sql)

    sql = f"""SELECT sigla_uf, sum(votos) FROM r2.votos_minuto WHERE {BR}
              AND minuto_bsb >= TIMESTAMP '{DIA} 17:15:00' GROUP BY 1 ORDER BY 2 DESC"""
    rows = f.q(sql)
    f.add("stf", 8, "O STF estende a votação até as 19h",
          f"Depois das 17h15, {fmt(sum(r[1] for r in rows))} votos: "
          + ", ".join(f"{fmt(n)} {em(u)}" for u, n in rows[:3]) + ".",
          "17:15", {"uf": rows[0][0]}, sum(r[1] for r in rows), sql, certo=False)

    (uf, mun, z, s, _, t), sql = voto_extremo(f, "id_municipio_tse = (SELECT id_municipio_tse FROM br_bd_diretorios_brasil.municipio WHERE id_municipio = '2605459')", True)
    l = f.lugar(uf, mun, z, s)
    f.add("noronha", 8, f"Fernando de Noronha, {hfala(hora(t))}", "O último voto da ilha.", hora(t), l, None, sql)

    (uf, mun, z, s, _, t), sql = voto_extremo(f, BR, True)
    l = f.lugar(uf, mun, z, s)
    f.add("ultimo_voto", 8, "O último voto no Brasil", f"Em {f.onde(l)}, às {hfala(hora(t))}.", hora(t), l, None, sql)

    (uf, mun, z, s, _, t), sql = voto_extremo(f, ZZ, True)
    l = f.lugar(uf, mun, z, s)
    fm = f.q(f"SELECT fuso_minutos FROM r2.fuso_municipio WHERE sigla_uf = '{uf}' AND id_municipio_tse = '{mun}'")[0][0]
    local = t + timedelta(minutes=fm)
    f.add("ultimo_voto_exterior", 8, "O último voto da eleição",
          f"Em {f.onde(l)}, às {hfala(hora(t))} de Brasília. Lá eram {hfala(hora(local))}.", hora(t), l, None, sql)
    f.itens[-1]["hora_local"] = hora(local)

    return {"mock": False, "itens": f.itens}


# W3: the closing urna's steps from the close to the log file, one line per step (FIM_PASSOS).
# Only these fixed messages leave the lake: other closing lines carry título numbers.
FIM_PASSOS = [
    "Operador selecionou: Encerrar votação",
    "Procedimento de encerramento confirmado",
    "Gerando relatório [BU] [INÍCIO]",
    "Imprimindo relatório [BU] via nº [1]",
    "Fim de impressão",
    "Gerando arquivo de resultado [bu.dat] + [Início]",
    "Gerando arquivo de resultado [log.jez] + [Início]",
]
_fim_in = ", ".join("'" + m.replace("'", "''") + "'" for m in FIM_PASSOS)
FIM_LOG_SQL = f"""
WITH d AS (
    SELECT sigla_uf, id_municipio_tse, zona, secao, arquivo_hash, linha, data_hora, mensagem
    FROM br_tse_urna_logs.eventos
    WHERE ano = {ANO} AND turno = {TURNO} AND arquivo_membro = 'logd.dat'
      AND CAST(data_hora AS DATE) = DATE '{DIA}' AND mensagem IN ({_fim_in})
),
enc AS (
    SELECT sigla_uf, id_municipio_tse, zona, secao, arquivo_hash, max(linha) AS l0
    FROM d WHERE mensagem = '{FIM_PASSOS[0]}' GROUP BY ALL
)
SELECT d.sigla_uf, d.id_municipio_tse, d.zona, d.secao, d.arquivo_hash, d.linha, d.mensagem,
       d.data_hora - to_minutes(f.fuso_minutos) AS hora_bsb
FROM d
JOIN enc USING (sigla_uf, id_municipio_tse, zona, secao, arquivo_hash)
JOIN main.fuso_municipio f
  ON f.ano = {ANO} AND f.turno = {TURNO} AND f.sigla_uf = d.sigla_uf AND f.id_municipio_tse = d.id_municipio_tse
WHERE d.linha >= enc.l0"""


def r2_views(con: duckdb.DuckDBPyConnection) -> None:
    names = {"fuso": "fuso_municipio", "votos_minuto": "votos_minuto", "secao": "secao_dia",
             "aptos": "aptos", "coleta": "secoes_coleta", "fim_log": "fim_log"}
    con.execute("CREATE SCHEMA IF NOT EXISTS r2")
    for c, v in names.items():
        con.execute(f"CREATE OR REPLACE VIEW r2.{v} AS SELECT * FROM c_{c}")


def cs_sections() -> list[dict]:
    """Every section of round 2 in the results-site lists (data/raw/cs), with its `ha` time."""
    rows = []
    raw = Path(config.load().raw) / "cs"
    for f in sorted(raw.glob(f"*-p{int(config.ELECTIONS[(ANO, TURNO)].id_pleito):06d}-cs.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for a in d["abr"]:
            for m in a["mu"]:
                for z in m["zon"]:
                    for s in z["sec"]:
                        rows.append({"uf": a["cd"], "mun": m["cd"], "zona": z["cd"], "secao": s["ns"],
                                     "da": s.get("da"), "ha": s.get("ha"), "nsp": s.get("nsp")})
    return rows


def chegada() -> dict:
    """W4: sections counted per minute, from the `ha` of each section in cs.json (Brasilia time;
    sample check in P4 W4: the first count, about 2 minutes after the TSE received it).
    `nacional` and `uf` are Brazil, the shape the page reads; `exterior` is abroad, on its own
    clock (Asia counts from 01:51). An aggregated section (nsp) has no own `ha`."""
    def minuto(r):
        d = int(r["da"].split("/")[0]) - 25  # days from the vote
        h, m, _ = r["ha"].split(":")
        return d * 1440 + int(h) * 60 + int(m)

    def hhmm(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    def curva(rows):
        mins = [(r["uf"].upper(), minuto(r)) for r in rows]
        start, end = min(m for _, m in mins), max(m for _, m in mins)
        nac, uf = [0] * (end - start + 1), {}
        for u, m in mins:
            nac[m - start] += 1
            uf.setdefault(u, [0] * len(nac))[m - start] += 1
        return {"inicio": hhmm(start), "fim": hhmm(end), "total": len(mins), "nacional": nac,
                "uf": dict(sorted(uf.items()))}

    rows = [r for r in cs_sections() if r["ha"] and r["da"]]
    br = curva([r for r in rows if r["uf"] != "zz"])
    zz = curva([r for r in rows if r["uf"] == "zz"])
    return {"mock": False, "fonte": "resultados.tse.jus.br, cs.json, campo ha (hora de Brasília)",
            **br, "exterior": {k: zz[k] for k in ("inicio", "fim", "total", "nacional")}}


HORAS = list(range(8, 20))  # the page's hour bands, Brasília


def hm_(ts) -> str | None:
    return ts.strftime("%H:%M") if ts is not None else None


def cs_minuto(r) -> int:
    """Minutes after 00:00 of election day of a section's `ha` (a later day adds 1440)."""
    h, m, _ = r["ha"].split(":")
    return (int(r["da"].split("/")[0]) - 25) * 1440 + int(h) * 60 + int(m)


def mediana(xs: list[int]) -> int | None:
    xs = sorted(xs)
    return xs[(len(xs) - 1) // 2] if xs else None


def chegadas() -> dict[tuple, int]:
    """(UF, municipio, zona, secao) -> minute its result was first counted (`ha`)."""
    return {(r["uf"].upper(), r["mun"].zfill(5), r["zona"].zfill(4), r["secao"].zfill(4)): cs_minuto(r)
            for r in cs_sections() if r["ha"] and r["da"]}


def hhmm_(m: int | None) -> str | None:
    return None if m is None else f"{m // 60:02d}:{m % 60:02d}"


def cidades(con: duckdb.DuckDBPyConnection) -> None:
    """W3: cidades/<UF>.json, Brazil only (the town search has no city abroad yet). votos and
    aptos are the TSE's official turnout and electorate; pico, metade and horas come from the
    log's votes per minute; fechamento is the median close, chegada the median `ha`. No name:
    the page has it from towns.json, and MG stays near the 33 KB gzip budget (37 KB)."""
    base = con.execute("""
        SELECT a.sigla_uf, a.id_municipio_tse, sum(a.comparecimento), sum(a.aptos), count(*),
               max(s.ultimo_voto), quantile_disc(s.encerramento, 0.5)
        FROM r2.aptos a LEFT JOIN r2.secao_dia s USING (sigla_uf, id_municipio_tse, zona, secao)
        WHERE a.sigla_uf <> 'ZZ' GROUP BY 1, 2""").fetchall()
    curva: dict[tuple, list] = {}
    for uf, mun, minuto, v in con.execute("""SELECT sigla_uf, id_municipio_tse, minuto_bsb, votos
            FROM r2.votos_minuto WHERE sigla_uf <> 'ZZ' ORDER BY 1, 2, 3""").fetchall():
        curva.setdefault((uf, mun), []).append((minuto, v))
    cheg: dict[tuple, list] = {}
    for (uf, mun, _, _), m in chegadas().items():
        cheg.setdefault((uf, mun), []).append(m)
    por_uf: dict[str, dict] = {}
    for uf, mun, votos, aptos, secoes, ultimo, fecha in base:
        c = curva.get((uf, mun), [])
        horas = [0] * len(HORAS)
        for minuto, v in c:
            horas[min(max(minuto.hour, HORAS[0]), HORAS[-1]) - HORAS[0]] += v
        total, acc, metade = sum(v for _, v in c), 0, None
        for minuto, v in c:
            acc += v
            if acc * 2 >= total:
                metade = hm_(minuto)
                break
        pico = hm_(max(c, key=lambda x: x[1])[0]) if c else None
        por_uf.setdefault(uf, {})[mun] = {
            "votos": int(votos), "aptos": int(aptos), "secoes": secoes,
            "pico": pico, "metade": metade, "ultimo_voto": hm_(ultimo), "horas": horas,
            "fechamento": hm_(fecha), "chegada": hhmm_(mediana(cheg.get((uf, mun), []))),
        }
    for uf, cs in sorted(por_uf.items()):
        dump(OUT / f"cidades/{uf}.json", {"mock": False, "uf": uf, "horas": HORAS, "cidades": cs})


def sample_aux(fraction: float, seed: int, rps: float) -> None:
    """W4 check: fetch aux.json for a random sample of sections and keep each hash's `hr`
    next to the section's `ha` from cs.json. One JSON line per section in
    $BRASILDB_DATA/site_v2_aux_sample.jsonl; a rerun skips sections already there."""
    import httpx

    settings = config.load()
    pleito = config.ELECTIONS[(ANO, TURNO)].id_pleito
    out = Path(os.environ.get("BRASILDB_DATA", "data")) / "site_v2_aux_sample.jsonl"
    done = set()
    if out.exists():
        done = {tuple(json.loads(x)["key"]) for x in out.read_text().splitlines() if x.strip()}
    rows = [r for r in cs_sections() if r["ha"]]
    rng = random.Random(seed)
    sample = [r for r in rows if rng.random() < fraction]
    todo = [r for r in sample if (r["uf"], r["mun"], r["zona"], r["secao"]) not in done]
    print(f"sample {len(sample)} sections, {len(todo)} to fetch", flush=True)
    gap = 1.0 / rps
    with httpx.Client(timeout=30) as client, out.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(todo):
            k = SectionKey(r["uf"], r["mun"], r["zona"], r["secao"])
            t = time.time()
            for attempt in range(3):
                try:
                    resp = client.get(aux_url(settings.results_base, pleito, k))
                    break
                except httpx.HTTPError:
                    time.sleep(2 * (attempt + 1))
            else:
                continue
            rec = {"key": [r["uf"], r["mun"], r["zona"], r["secao"]], "ha": r["ha"], "status": resp.status_code}
            if resp.status_code == 200:
                rec["hashes"] = [{"dr": h.get("dr"), "hr": h.get("hr"), "st": h.get("st")}
                                 for h in resp.json().get("hashes", [])]
            fh.write(json.dumps(rec) + "\n")
            if i % 500 == 0:
                print(f"{i}/{len(todo)}", flush=True)
            time.sleep(max(0.0, gap - (time.time() - t)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cache", "amostra-aux", "curiosidades", "chegada", "cidades"])
    ap.add_argument("--fraction", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rps", type=float, default=10)
    ap.add_argument("--only", nargs="*", help="cache: rebuild only these tables (fuso votos_minuto secao aptos coleta fim_log)")
    a = ap.parse_args()
    if a.step == "cache":
        build_cache(a.only)
    elif a.step == "amostra-aux":
        sample_aux(a.fraction, a.seed, a.rps)
    elif a.step == "curiosidades":
        con = duckdb.connect(str(cache_path()))
        r2_views(con)
        dump(OUT / "curiosidades.json", curiosidades(con))
    elif a.step == "chegada":
        dump(OUT / "chegada.json", chegada())
    elif a.step == "cidades":
        con = duckdb.connect(str(cache_path()), read_only=True)
        cidades(con)


if __name__ == "__main__":
    main()
