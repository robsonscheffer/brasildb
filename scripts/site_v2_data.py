"""Build the v2 walk's data files from the lake (P4). Same paths and shapes as the mock.

  uv run python scripts/site_v2_data.py cache          # once: lake views -> $BRASILDB_DATA/site_v2.duckdb
  uv run python scripts/site_v2_data.py curiosidades   # docs/site/data/curiosidades.json
  uv run python scripts/site_v2_data.py chegada        # docs/site/data/chegada.json
  uv run python scripts/site_v2_data.py cidades        # docs/site/data/cidades/<UF>.json
  uv run python scripts/site_v2_data.py secoes         # docs/site/data/secoes/<UF>/<municipio>-<zona>.json
  uv run python scripts/site_v2_data.py exterior       # docs/site/data/exterior.json (cities abroad)
  uv run python scripts/site_v2_data.py urna           # docs/site/data/urna.json
  uv run python scripts/site_v2_data.py frames         # docs/site/data/frames.png (the map's pixels) and totals.json (the curves)

Round 2 of 2026 only. Every time is Brasilia time (P4 D4). Every file carries "mock": false.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import struct
import sys
import time
import zlib
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brasildb import config, lake, sqlrun  # noqa: E402
from brasildb.tse.paths import SectionKey, aux_url  # noqa: E402

ANO, TURNO = 2026, 2
OUT = ROOT / "docs/site/data"


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
PAIS = {  # time zone -> country of every city abroad (each zone here holds one country); a miss fails loudly
    "Africa/Abidjan": "Costa do Marfim", "Africa/Accra": "Gana", "Africa/Addis_Ababa": "Etiópia",
    "Africa/Algiers": "Argélia", "Africa/Bamako": "Mali", "Africa/Bissau": "Guiné-Bissau",
    "Africa/Blantyre": "Malawi", "Africa/Brazzaville": "República do Congo", "Africa/Cairo": "Egito",
    "Africa/Casablanca": "Marrocos", "Africa/Conakry": "Guiné", "Africa/Dakar": "Senegal",
    "Africa/Dar_es_Salaam": "Tanzânia", "Africa/Douala": "Camarões", "Africa/Gaborone": "Botsuana",
    "Africa/Harare": "Zimbábue", "Africa/Johannesburg": "África do Sul",
    "Africa/Kinshasa": "República Democrática do Congo", "Africa/Lagos": "Nigéria",
    "Africa/Libreville": "Gabão", "Africa/Lome": "Togo", "Africa/Luanda": "Angola",
    "Africa/Lusaka": "Zâmbia", "Africa/Malabo": "Guiné Equatorial", "Africa/Maputo": "Moçambique",
    "Africa/Nairobi": "Quênia", "Africa/Ouagadougou": "Burkina Faso", "Africa/Porto-Novo": "Benin",
    "Africa/Sao_Tome": "São Tomé e Príncipe", "Africa/Tripoli": "Líbia", "Africa/Tunis": "Tunísia",
    "Africa/Windhoek": "Namíbia", "America/Antigua": "Antígua e Barbuda",
    "America/Argentina/Buenos_Aires": "Argentina", "America/Argentina/Cordoba": "Argentina",
    "America/Argentina/Mendoza": "Argentina", "America/Asuncion": "Paraguai",
    "America/Barbados": "Barbados", "America/Belize": "Belize", "America/Bogota": "Colômbia",
    "America/Caracas": "Venezuela", "America/Cayenne": "Guiana Francesa",
    "America/Chicago": "Estados Unidos", "America/Costa_Rica": "Costa Rica",
    "America/El_Salvador": "El Salvador", "America/Guatemala": "Guatemala",
    "America/Guayaquil": "Equador", "America/Guyana": "Guiana", "America/Havana": "Cuba",
    "America/Jamaica": "Jamaica", "America/La_Paz": "Bolívia", "America/Lima": "Peru",
    "America/Los_Angeles": "Estados Unidos", "America/Managua": "Nicarágua",
    "America/Mexico_City": "México", "America/Montevideo": "Uruguai", "America/Nassau": "Bahamas",
    "America/New_York": "Estados Unidos", "America/Panama": "Panamá",
    "America/Paramaribo": "Suriname", "America/Port-au-Prince": "Haiti",
    "America/Port_of_Spain": "Trinidad e Tobago", "America/Santiago": "Chile",
    "America/Santo_Domingo": "República Dominicana", "America/St_Lucia": "Santa Lúcia",
    "America/Tegucigalpa": "Honduras", "America/Toronto": "Canadá", "America/Vancouver": "Canadá",
    "Asia/Almaty": "Cazaquistão", "Asia/Amman": "Jordânia", "Asia/Baghdad": "Iraque",
    "Asia/Bahrain": "Bahrein", "Asia/Baku": "Azerbaijão", "Asia/Bangkok": "Tailândia",
    "Asia/Beirut": "Líbano", "Asia/Colombo": "Sri Lanka", "Asia/Damascus": "Síria",
    "Asia/Dhaka": "Bangladesh", "Asia/Dili": "Timor-Leste", "Asia/Dubai": "Emirados Árabes Unidos",
    "Asia/Hebron": "Palestina", "Asia/Ho_Chi_Minh": "Vietnã", "Asia/Hong_Kong": "China",
    "Asia/Jakarta": "Indonésia", "Asia/Jerusalem": "Israel", "Asia/Karachi": "Paquistão",
    "Asia/Kathmandu": "Nepal", "Asia/Kolkata": "Índia", "Asia/Kuala_Lumpur": "Malásia",
    "Asia/Kuwait": "Kuwait", "Asia/Manila": "Filipinas", "Asia/Muscat": "Omã",
    "Asia/Nicosia": "Chipre", "Asia/Pyongyang": "Coreia do Norte", "Asia/Qatar": "Catar",
    "Asia/Riyadh": "Arábia Saudita", "Asia/Seoul": "Coreia do Sul", "Asia/Shanghai": "China",
    "Asia/Singapore": "Singapura", "Asia/Taipei": "Taiwan", "Asia/Tbilisi": "Geórgia",
    "Asia/Tehran": "Irã", "Asia/Tokyo": "Japão", "Asia/Yangon": "Mianmar", "Asia/Yerevan": "Armênia",
    "Atlantic/Cape_Verde": "Cabo Verde", "Australia/Sydney": "Austrália",
    "Europe/Amsterdam": "Países Baixos", "Europe/Athens": "Grécia", "Europe/Belgrade": "Sérvia",
    "Europe/Berlin": "Alemanha", "Europe/Bratislava": "Eslováquia", "Europe/Brussels": "Bélgica",
    "Europe/Bucharest": "Romênia", "Europe/Budapest": "Hungria", "Europe/Copenhagen": "Dinamarca",
    "Europe/Dublin": "Irlanda", "Europe/Helsinki": "Finlândia", "Europe/Istanbul": "Turquia",
    "Europe/Kyiv": "Ucrânia", "Europe/Lisbon": "Portugal", "Europe/Ljubljana": "Eslovênia",
    "Europe/London": "Reino Unido", "Europe/Madrid": "Espanha", "Europe/Moscow": "Rússia",
    "Europe/Oslo": "Noruega", "Europe/Paris": "França", "Europe/Prague": "Tchéquia",
    "Europe/Rome": "Itália", "Europe/Sarajevo": "Bósnia e Herzegovina", "Europe/Sofia": "Bulgária",
    "Europe/Stockholm": "Suécia", "Europe/Tallinn": "Estônia", "Europe/Tirane": "Albânia",
    "Europe/Vienna": "Áustria", "Europe/Warsaw": "Polônia", "Europe/Zagreb": "Croácia",
    "Europe/Zurich": "Suíça", "Pacific/Auckland": "Nova Zelândia",
}
UFNOME = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
          "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
          "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
          "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná",
          "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima",
          "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
          "TO": "Tocantins"}


# Cities abroad whose TSE name is not the usual one in Portuguese or in the city's own language.
NOME_EXTERIOR = {
    "Barein": "Manama", "Dacca": "Daca", "Dar Es Salaam": "Dar es Salaam", "Kuaite": "Cidade do Kuwait",
    "Ciudad Del Este": "Ciudad del Este", "Salto Del Guairá": "Salto del Guairá", "Paso Los Libres": "Paso de los Libres",
    "Santa Cruz de La Sierra": "Santa Cruz de la Sierra", "Port Of Spain": "Port of Spain", "Saint Johns": "St. John's",
    "Kingston-Jamaica": "Kingston", "Panama": "Panamá", "Guatemala": "Cidade da Guatemala", "Mexico": "Cidade do México",
    "St Georges de Loyapock": "Saint-Georges-de-l'Oyapock",
}


def nome_pt(n: str) -> str:
    """'Rio De Janeiro' -> 'Rio de Janeiro': articles and 'e' lower case inside a name."""
    w = n.split(" ")
    return " ".join(x.lower() if k and x in ("De", "Do", "Da", "Dos", "Das", "E", "D'") else x
                    for k, x in enumerate(w))


def nome_exterior(n: str) -> str:
    """A TSE city name abroad, as the page shows it."""
    return NOME_EXTERIOR.get(nome_pt(n.title()), nome_pt(n.title()))


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
            self.nomes[("ZZ", i)] = (nome_exterior(n), tz)
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
          f"Das cidades com mil votos ou mais, a primeira a chegar à metade dos seus votos. Foram {fmt(tot_c)} no dia.",
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
          f"{hfala(local.strftime('%H:%M'))}, e a urna tinha aberto às {8 + fu // 60}h da manhã.",
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
    f.add("sem_luz", 5, "A luz caiu. A urna seguiu na bateria",
          f"{fmt(n_q)} urnas passaram para a bateria em algum momento do dia. "
          f"Em {f.onde(l)}, uma delas votou {int(horas_b)} horas e {round(mb % 60)} minutos na bateria."
          if horas_b >= 1 else f"{fmt(n_q)} urnas passaram para a bateria em algum momento do dia.",
          None, {"uf": "BR"}, n_q, sql + " ; " + sql2)

    sql = f"""SELECT sigla_uf, id_municipio_tse, hour(primeira_queda) h, count(*) n FROM r2.secao_dia
              WHERE {BR} AND quedas > 0 AND min_bateria >= 10 GROUP BY 1, 2, 3 ORDER BY n DESC, 1, 2, 3 LIMIT 1"""
    uf, mun, h, n = f.q(sql)[0]
    l = f.lugar(uf, mun)
    f.add("bateria_cidade", 5, f"{l['municipio']}, {n} urnas na bateria",
          f"Entre {h}h e {h + 1}h, {n} urnas de {l['municipio']} ficaram ao menos dez minutos na bateria.",
          f"{h:02d}:00", l, n, sql)

    sql = f"""SELECT count(*) FILTER (WHERE n_logs > 1), count(*) FILTER (WHERE contingencia) FROM r2.secao_dia WHERE {BR}"""
    n2, nc = f.q(sql)[0]
    f.add("trocadas", 5, "Urnas trocadas", f"Em {fmt(n2)} seções, uma urna de contingência substituiu outra durante o dia.",
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
# W2: the urna of the first vote in Brazil, from power-on to its twelfth vote. Only these
# event types leave the lake; mesário and título lines never do.
URNA_TIPOS = ("urna_ligada", "relatorio", "urna_pronta", "eleitor_habilitado", "voto_computado")


def urna(con: duckdb.DuckDBPyConnection, n_votos: int = 12, n_minuto: int = 160) -> dict:
    """urna.json: the section of the first vote in Brazil (D3 order) and its log lines on
    election day, then the first minute (08:00 to 08:00:59 Brasília) as n_minuto votes spread
    evenly over the minute's votes in D3 order. Times are Brasília."""
    f = Fatos(con)
    (uf, mun, z, sec, _, _), _ = voto_extremo(f, "sigla_uf <> 'ZZ'", False)
    votos = f.q(f"SELECT comparecimento FROM r2.aptos WHERE sigla_uf = '{uf}' AND id_municipio_tse = '{mun}' "
                f"AND zona = '{z}' AND secao = '{sec}'")[0][0]
    tipos = ", ".join(f"'{t}'" for t in URNA_TIPOS)
    linhas, n = [], 0
    for t, tipo, valor, msg in f.q(f"""
            SELECT e.data_hora - to_minutes(fu.fuso_minutos), e.tipo_evento, e.valor, e.mensagem
            FROM br_tse_urna_logs.eventos e
            JOIN r2.fuso_municipio fu USING (sigla_uf, id_municipio_tse)
            WHERE e.ano = {ANO} AND e.turno = {TURNO} AND e.sigla_uf = '{uf}' AND e.id_municipio_tse = '{mun}'
              AND e.zona = '{z}' AND e.secao = '{sec}' AND e.arquivo_membro = 'logd.dat'
              AND CAST(e.data_hora AS DATE) = DATE '{DIA}' AND e.tipo_evento IN ({tipos})
            ORDER BY e.linha"""):
        if tipo == "relatorio" and valor != "ZERÉSIMA":
            continue
        linhas.append({"hora": t.strftime("%H:%M:%S"), "tipo": tipo, "texto": msg})
        n += tipo == "voto_computado"
        if n == n_votos:
            break
    total = f.q(f"SELECT sum(votos) FROM r2.votos_minuto WHERE sigla_uf <> 'ZZ' "
                f"AND minuto_bsb = TIMESTAMP '{DIA} 08:00:00'")[0][0]
    rows = f.q(f"""WITH v AS ({VOTO_BSB} AND e.sigla_uf <> 'ZZ'
                   AND e.data_hora BETWEEN TIMESTAMP '{DIA} 05:59:00' AND TIMESTAMP '{DIA} 09:01:00')
                   SELECT sigla_uf, id_municipio_tse, hora_bsb FROM v
                   WHERE hora_bsb >= TIMESTAMP '{DIA} 08:00:00' AND hora_bsb < TIMESTAMP '{DIA} 08:01:00'
                   ORDER BY {ORDEM}""")
    if len(rows) != total:
        raise SystemExit(f"first minute: {len(rows)} votes in the log, {total} in votos_minuto")
    resto = rows[1:]  # the page shows the first vote on its own line
    passo = len(resto) / n_minuto
    minuto = [{"hora": r[2].strftime("%H:%M:%S"), "municipio": f.nomes[r[:2]], "uf": r[0]}
              for r in (resto[int(k * passo)] for k in range(min(n_minuto, len(resto))))]
    return {"mock": False,
            "secao": {"uf": uf, "municipio": f.nomes[(uf, mun)], "zona": z, "secao": sec, "votos": votos},
            "linhas": linhas,
            "primeiro_minuto": {"votos": total, "linhas": minuto},
            "fonte": "Log da urna, TSE (dados abertos); o primeiro minuto mostra 1 em cada "
                     f"{round(passo)} votos, em ordem de hora"}


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


def min_(ts) -> int | None:
    """Minutes after 00:00 of a timestamp's clock (what hm_ prints, as an integer)."""
    return ts.hour * 60 + ts.minute if ts is not None else None


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


def fusos(con: duckdb.DuckDBPyConnection) -> dict[tuple, int]:
    """(UF, municipio) -> minutes from Brasília to the urna's local time; 0 in Brazil (P4 D4)."""
    return defaultdict(int, {("ZZ", m): f for m, f in con.execute(
        "SELECT id_municipio_tse, fuso_minutos FROM main.fuso_exterior").fetchall()})


def local(ts, fuso: int):
    return None if ts is None else ts + timedelta(minutes=fuso)


def cidades(con: duckdb.DuckDBPyConnection) -> None:
    """W3: cidades/<UF>.json, and ZZ for the cities abroad. votos and aptos are the TSE's
    official turnout and electorate; pico, metade and horas come from the log's votes per
    minute; fechamento is the median close, chegada the median `ha`. Times are Brasília, and
    abroad the urna's local time (the one a voter there remembers) with the city's `fuso`.
    No name, aptos or secoes: the page has them from towns.json and exterior.json. Each town
    is one array: the `campos` scalars (times as minutes after 00:00) then the hour bands,
    to fit 33 KB gzip per state (MG was 37 KB)."""
    fuso = fusos(con)
    base = con.execute("""
        SELECT a.sigla_uf, a.id_municipio_tse, sum(a.comparecimento), sum(a.aptos), count(*),
               max(s.ultimo_voto), quantile_disc(s.encerramento, 0.5)
        FROM r2.aptos a LEFT JOIN r2.secao_dia s USING (sigla_uf, id_municipio_tse, zona, secao)
        GROUP BY 1, 2""").fetchall()
    curva: dict[tuple, list] = {}
    for uf, mun, minuto, v in con.execute("""SELECT sigla_uf, id_municipio_tse, minuto_bsb, votos
            FROM r2.votos_minuto ORDER BY 1, 2, 3""").fetchall():
        curva.setdefault((uf, mun), []).append((local(minuto, fuso[(uf, mun)]), v))
    cheg: dict[tuple, list] = {}
    for (uf, mun, _, _), m in chegadas().items():
        cheg.setdefault((uf, mun), []).append(m + fuso[(uf, mun)])
    por_uf: dict[str, dict] = {}
    for uf, mun, votos, aptos, secoes, ultimo, fecha in base:
        f = fuso[(uf, mun)]
        ultimo, fecha = local(ultimo, f), local(fecha, f)
        c = curva.get((uf, mun), [])
        horas = [0] * len(HORAS)
        for minuto, v in c:
            horas[min(max(minuto.hour, HORAS[0]), HORAS[-1]) - HORAS[0]] += v
        total, acc, metade = sum(v for _, v in c), 0, None
        for minuto, v in c:
            acc += v
            if acc * 2 >= total:
                metade = min_(minuto)
                break
        pico = min_(max(c, key=lambda x: x[1])[0]) if c else None
        mc = mediana(cheg.get((uf, mun), []))
        por_uf.setdefault(uf, {})[mun] = [
            int(votos), pico, metade, min_(ultimo), min_(fecha), mc,
            *([f] if uf == "ZZ" else []), *horas]
    for uf, cs in sorted(por_uf.items()):
        campos = ["votos", "pico", "metade", "ultimo_voto", "fechamento", "chegada"] + (["fuso"] if uf == "ZZ" else [])
        dump(OUT / f"cidades/{uf}.json", {"mock": False, "uf": uf, "hora": "local" if uf == "ZZ" else "Brasília",
                                          "horas": HORAS, "campos": campos, "cidades": cs})


def exterior(con: duckdb.DuckDBPyConnection) -> dict:
    """exterior.json: the cities abroad, for the strip under the map and the town search.
    One row per city with voters, east to west. primeiro and ultimo are the first and last
    vote in Brasília minutes after Sunday 00:00 (Saturday is negative). niveis is one digit
    per map minute (totals.json `start` and `minutes`): 0 outside the city's voting span, 1 to
    8 its 3-minute mean against its own peak, 1 also for a quiet minute inside the span."""
    tot = json.loads((FRAMES / "totals.json").read_text())
    start, minutes = tot["start"], tot["minutes"]
    dia0 = con.execute("SELECT data FROM main.eleicoes WHERE ano = ? AND turno = ?", [ANO, TURNO]).fetchone()[0]
    of = lambda ts: int((ts - datetime.combine(dia0, datetime.min.time())).total_seconds() // 60)
    votos: dict[str, dict[int, int]] = {}
    for mun, minuto, v in con.execute("""SELECT id_municipio_tse, minuto_bsb, votos
            FROM r2.votos_minuto WHERE sigla_uf = 'ZZ'""").fetchall():
        votos.setdefault(mun, {})[of(minuto)] = v
    cidades = []
    for mun, nome, tz, fuso, comp, aptos in con.execute("""
            SELECT f.id_municipio_tse, f.nome, f.tz, f.fuso_minutos, sum(a.comparecimento), sum(a.aptos)
            FROM main.fuso_exterior f JOIN r2.aptos a ON a.sigla_uf = 'ZZ' AND a.id_municipio_tse = f.id_municipio_tse
            GROUP BY ALL HAVING sum(a.aptos) > 0 ORDER BY f.fuso_minutos DESC, f.nome""").fetchall():
        v = votos.get(mun, {})
        c = {"id": mun, "nome": nome_exterior(nome), "pais": PAIS[tz], "fuso": fuso,
             "votos": int(comp), "aptos": int(aptos), "primeiro": min(v, default=None), "ultimo": max(v, default=None)}
        if v:
            mean3 = lambda m: (v.get(m - 1, 0) + v.get(m, 0) + v.get(m + 1, 0)) / 3
            peak = max(mean3(m) for m in v)
            c["niveis"] = "".join(
                "0" if not c["primeiro"] <= m <= c["ultimo"] else str(max(1, round(8 * mean3(m) / peak)))
                for m in range(start, start + minutes))
        cidades.append(c)
    return {"mock": False, "hora": "Brasília", "start": start, "minutes": minutes, "cidades": cidades}


SECAO_CAMPOS = ["abertura", "primeiro_voto", "ultimo_voto", "encerramento", "votos", "aptos", "chegada", "fim_log"]


def secoes(con: duckdb.DuckDBPyConnection) -> None:
    """W3: secoes/<UF>/<municipio>-<zona>.json, one file per town and zona (São Paulo alone has
    26.683 sections). Compact: `campos` names the fields once and each section is one row.
    Times are Brasília HH:MM; votos and aptos are official. fim_log holds FIM_PASSOS as
    seconds: the first step's second of the day, then each step's gap to the one before; the
    page holds the step texts. A section aggregated into another (cs `nsp`) is the principal's
    number as a string. Abroad (ZZ) every time is the urna's local time, like cidades/ZZ.json."""
    cheg = chegadas()
    fuso = fusos(con)
    passos: dict[tuple, dict] = {}
    for uf, mun, z, sec, h, linha, msg, t in con.execute(
            "SELECT sigla_uf, id_municipio_tse, zona, secao, arquivo_hash, linha, mensagem, hora_bsb "
            "FROM r2.fim_log ORDER BY 1, 2, 3, 4, 5, 6").fetchall():
        passos.setdefault((uf, mun, z, sec), {}).setdefault(h, []).append((msg, local(t, fuso[(uf, mun)])))
    def fim_log(k):
        logs = passos.get(k)
        if not logs:
            return None
        linhas = max(logs.values(), key=lambda ls: ls[0][1])  # the hash closed last
        out, i = [], 0
        for passo in FIM_PASSOS:  # the first line of each step, in order
            while i < len(linhas) and linhas[i][0] != passo:
                i += 1
            if i == len(linhas):
                break
            t = linhas[i][1]
            out.append(t.hour * 3600 + t.minute * 60 + t.second)
        return [x - (out[k - 1] if k else 0) for k, x in enumerate(out)]
    dia = {}
    for uf, mun, z, sec, ab, pv, uv, enc, votos, aptos in con.execute("""
            SELECT a.sigla_uf, a.id_municipio_tse, a.zona, a.secao, s.abertura, s.primeiro_voto,
                   s.ultimo_voto, s.encerramento, a.comparecimento, a.aptos
            FROM r2.aptos a JOIN r2.secao_dia s USING (sigla_uf, id_municipio_tse, zona, secao)
            WHERE s.encerramento IS NOT NULL""").fetchall():
        k, f = (uf, mun, z, sec), fuso[(uf, mun)]
        if k not in cheg:
            continue
        dia[k] = [hm_(local(ab, f)), hm_(local(pv, f)), hm_(local(uv, f)), hm_(local(enc, f)),
                  votos, aptos, hhmm_(cheg[k] + f), fim_log(k)]
    for r in cs_sections():
        if r["nsp"] is None:
            continue
        uf, mun, z = r["uf"].upper(), r["mun"].zfill(5), r["zona"].zfill(4)
        if (uf, mun, z, str(r["nsp"]).zfill(4)) in dia:
            dia[(uf, mun, z, r["secao"].zfill(4))] = str(r["nsp"]).zfill(4)
    arquivos: dict[tuple, dict] = {}
    for (uf, mun, z, sec), d in sorted(dia.items()):
        arquivos.setdefault((uf, mun, z), {})[sec] = d
    maior = (0, None)
    for (uf, mun, z), ss in arquivos.items():
        path = OUT / f"secoes/{uf}/{mun}-{z}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mock": False, "uf": uf, "municipio": mun, "zona": z,
                                    "campos": SECAO_CAMPOS, "secoes": ss},
                                   ensure_ascii=False, separators=(",", ":")))
        maior = max(maior, (path.stat().st_size, str(path.relative_to(ROOT))))
    print(f"secoes: {len(arquivos)} files, {len(dia)} sections; largest {maior[1]} {maior[0]} bytes")


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


FRAMES = ROOT / "docs/site/data"
LEVELS = 16  # the page draws 16 brightness buckets: round(((pixel / 255) ** 1.4) * 16)
GAMMA = 1.4  # v1 reads pixels the same way
STEP = 2  # every second bucket: 8 grey levels, the file falls from 1.27 MB to 0.87 MB
FLOOR = 1  # pixel of a town that still has votes to give: above 0, but dark (bucket 0)


def png_gray_up(width: int, height: int, pixels: bytes) -> bytes:
    """Grayscale PNG, every row stored as the difference to the row above (filter 2). A town
    is a column and a minute is a row, so a row differs little from the one before."""
    rows, prev = [], bytes(width)
    for y in range(height):
        row = pixels[y * width:(y + 1) * width]
        rows.append(b"\x00" + row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def frames(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild frames.png with the layout site_data.py wrote and both maps decode: one column
    per town (towns.json order), one row per minute from totals.json `start`, a pixel is the
    town's votes that minute against the peak of its 3-minute mean (255 = the peak).
    Changes against v1: the votes are the corrected round 2 (c_votos_minuto); brightness is
    cut to the 16 levels the page draws, which is what gets the file under 1 MB; a minute with
    votes, or a vote in the minute before or after, is never 0 (FLOOR). A quiet minute inside a
    town's voting span stays 0: lighting it put 123 towns on the map at 17:20, when 36 had a vote."""
    towns = json.loads((FRAMES / "towns.json").read_text())
    tot = json.loads((FRAMES / "totals.json").read_text())
    start, minutes, n = tot["start"], tot["minutes"], len(towns["id"])
    index = {(u, i): k for k, (u, i) in enumerate(zip(towns["uf"], towns["id"]))}
    counts = [[0] * minutes for _ in range(n)]
    national, por_uf = [0] * minutes, {}
    for uf, mun, minuto, votos in con.execute(f"""
        SELECT sigla_uf, id_municipio_tse, hour(minuto_bsb) * 60 + minute(minuto_bsb), votos
        FROM c_votos_minuto WHERE ano = {ANO} AND turno = {TURNO} AND sigla_uf <> 'ZZ'""").fetchall():
        m = minuto - start
        if (uf, mun) not in index:
            raise SystemExit(f"town {uf} {mun} is not in towns.json")
        if not 0 <= m < minutes:
            raise SystemExit(f"minute {minuto} is outside the frame range")
        counts[index[(uf, mun)]][m] += votos
        national[m] += votos
        por_uf.setdefault(uf, [0] * minutes)[m] += votos
    pixels = bytearray(n * minutes)
    for k, c in enumerate(counts):
        mean3 = [(c[max(0, m - 1)] + c[m] + c[min(minutes - 1, m + 1)]) / 3 for m in range(minutes)]
        peak = max(mean3) or 1
        voting = [m for m in range(minutes) if c[m]]
        end = voting[-1] if voting else -1
        for m in range(minutes):
            level = 0
            if not voting or not voting[0] <= m <= end:
                pass  # the centred mean would light the minute before the first vote
            elif mean3[m]:
                bucket = round(min(1.0, mean3[m] / peak) * LEVELS / STEP) * STEP
                level = round(255 * (bucket / LEVELS) ** (1 / GAMMA)) if bucket else FLOOR
            pixels[m * n + k] = level
    # The curves the pages draw (votes per minute, Brazil and per state) come from the same votes.
    tot.update(national=national, uf=dict(sorted(por_uf.items())))
    (FRAMES / "totals.json").write_text(json.dumps(tot, separators=(",", ":")))
    png = png_gray_up(n, minutes, bytes(pixels))
    (FRAMES / "frames.png").write_bytes(png)
    row = (17 * 60 + 36 - start) * n
    print(f"docs/site/data/frames.png: {len(png)} bytes, {n} towns x {minutes} minutes; "
          f"{sum(1 for k in range(n) if pixels[row + k])} towns lit at 17:36")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cache", "amostra-aux", "curiosidades", "chegada", "cidades", "secoes", "urna", "frames", "exterior"])
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
    elif a.step == "secoes":
        con = duckdb.connect(str(cache_path()), read_only=True)
        secoes(con)
    elif a.step == "exterior":
        dump(OUT / "exterior.json", exterior(duckdb.connect(str(cache_path()), read_only=True)))
    elif a.step == "urna":
        con = duckdb.connect(str(cache_path()), read_only=True)
        dump(OUT / "urna.json", urna(con))
    elif a.step == "frames":
        frames(duckdb.connect(str(cache_path()), read_only=True))


if __name__ == "__main__":
    main()
