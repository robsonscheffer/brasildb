"""Write mock data for the v2 walk (docs/site/v2/data/) in the P3 contract shapes.

Every file carries "mock": true so the page labels it "dados simulados". The real build
(scripts/site_data.py, task W1) writes the same paths and shapes with "mock": false.
Town names, votes and the national curve come from v1's real files; the rest is simulated.

    python3 scripts/site_v2_mock.py
"""

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "docs/site/data"
OUT = ROOT / "docs/site/v2/data"
HORAS = list(range(8, 20))  # hour bands 08h..19h, Brasília time


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def national_hour_shares(totals) -> list[float]:
    """Share of the day's votes cast in each hour band, from v1's real national curve."""
    start, nat = totals["start"], totals["national"]
    per = [0.0] * len(HORAS)
    for m, v in enumerate(nat):
        h = (start + m) // 60
        if h in HORAS:
            per[HORAS.index(h)] += v
    s = sum(per)
    return [p / s for p in per]


def urna(towns, totals):
    """Screen 1: the first vote, then the first minute of the country as log lines.
    The first-minute count is real (v1 totals); which towns and seconds are simulated."""
    lines = [
        ("07:00:02", "INICIO", "Urna ligada"),
        ("07:01:15", "ZERESIMA", "Zerésima impressa: 0 votos para cada candidato"),
        ("08:00:01", "ABERTURA", "Urna pronta para receber votos"),
        ("08:00:09", "VOTO", "Eleitor habilitado por biometria"),
        ("08:00:19", "VOTO", "O voto foi computado"),
    ]
    rng = random.Random(58653)
    t = 8 * 3600 + 19
    for n in range(2, 13):
        t += rng.randint(35, 95)
        lines.append((f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}", "VOTO", "O voto foi computado"))
    # First minute: towns drawn by size, seconds 19..59, as many lines as fit a phone scroll.
    rng2 = random.Random(800)
    pool = [i for i, v in enumerate(towns["votos"]) if v]
    weights = [towns["votos"][i] for i in pool]
    picks = rng2.choices(pool, weights=weights, k=160)
    secs = sorted(rng2.randint(20, 59) for _ in picks)
    minuto = [{"hora": f"08:00:{sc:02d}", "municipio": towns["nome"][i], "uf": towns["uf"][i]} for sc, i in zip(secs, picks)]
    return {
        "mock": True,
        "secao": {"uf": "RJ", "municipio": "Niterói", "zona": "0071", "secao": "0132", "votos": None},
        "linhas": [{"hora": h, "tipo": k, "texto": x} for h, k, x in lines],
        "primeiro_minuto": {"votos": totals["national"][480 - totals["start"]], "linhas": minuto},
        "fonte": "Log da urna, TSE (dados abertos)",
    }


def curiosidades():
    """Screens 2 to 5 and 8. "certo": true marks a value already checked (v1 beats or the secao_dia query notes)."""
    def item(id, tela, titulo, texto, hora, lugar, valor=None, certo=False):
        return {"id": id, "tela": tela, "titulo": titulo, "texto": texto, "hora": hora,
                "lugar": lugar, "valor": valor, "certo": certo, "sql": None}
    coords = {"Niterói": (-22.88, -43.10), "Espinosa": (-14.93, -42.82), "Jacareacanga": (-6.22, -57.75),
              "Cedro do Abaeté": (-19.15, -45.71), "Belo Horizonte": (-19.92, -43.94),
              "São Paulo": (-23.55, -46.63), "Paraíso do Sul": (-29.67, -53.14),
              "Fernando de Noronha": (-3.85, -32.42), "Santa Maria de Jetibá": (-20.03, -40.74),
              "Itajubá": (-22.43, -45.45), "Tomazina": (-23.78, -49.95), "Cuiabá": (-15.60, -56.10),
              "Marajó": (-1.68, -50.48), "Alto Solimões": (-3.50, -68.20), "BA": (-12.97, -38.50)}

    def place(it):
        key = it["lugar"].get("municipio") or it["lugar"]["uf"]
        if key in coords:
            it["lugar"]["lat"], it["lugar"]["lon"] = coords[key]
        return it

    def L(uf, mun=None, zona=None, secao=None):
        return {k: v for k, v in {"uf": uf, "municipio": mun, "zona": zona, "secao": secao}.items() if v}

    return {
        "mock": True,
        "itens": [place(it) for it in [
            item("primeiro_voto", 2, "O primeiro voto do país", "Dezoito segundos depois de a urna abrir, alguém em Niterói votou.", "08:00:19", L("RJ", "Niterói", "0071", "0132"), 18, True),
            item("abertura_tie", 2, "Todas abriram juntas", "473.844 urnas abriram no mesmo minuto, às 8h. Nenhuma antes.", "08:00", L("BR"), 473844, True),
            item("abertura", 3, "O país abre de uma vez", "No mesmo minuto, de Brasília ao Acre, onde ainda são 6h da manhã.", "08:00", L("BR"), 497896, True),
            item("pico", 3, "O pico", "420 mil votos por minuto.", "08:07", L("BR"), 420000, True),
            item("jacareacanga", 4, "Jacareacanga, metade às 10h07", "Foi a primeira cidade do país a chegar à metade dos votos.", "10:07", L("PA", "Jacareacanga"), None, True),
            item("almoco", 4, "O Nordeste para para almoçar", "São Paulo e Rio, quase não.", "12:00", L("NE"), None, True),
            item("solimoes", 4, "Alto Solimões, nove em dez", "No Amazonas, nove em cada dez já votaram.", "13:55", L("AM", "Alto Solimões"), None, True),
            item("jetiba", 4, "612 de 612", "Em Santa Maria de Jetibá, a maior seção do país. Todos os eleitores vieram.", None, L("ES", "Santa Maria de Jetibá", "0009", "0085"), 612, True),
            item("espinosa", 4, "Três horas de espera", "Em Espinosa, a urna abriu às 8h. O primeiro eleitor chegou às 11h15.", "11:15:48", L("MG", "Espinosa", "0109", "0094"), 195, True),
            item("granizo", 5, "Granizo em Belo Horizonte", "163 locais de votação sem luz. As urnas seguiram na bateria.", "13:00", L("MG", "Belo Horizonte"), 163, True),
            item("quedas", 5, "54 vezes sem luz", "Em Paraíso do Sul, a luz caiu 54 vezes. A urna votou 7 horas na bateria.", None, L("RS", "Paraíso do Sul", "0157", "0478"), 54, True),
            item("sem_luz", 5, "Uma em cada oito", "62.409 urnas ficaram sem luz em algum momento. Nenhuma parou de votar.", None, L("BR"), 62409, True),
            item("trocadas", 5, "Urnas trocadas", "Em 1.842 seções, uma urna substituiu outra no meio do dia.", None, L("BR"), 1842, True),
            item("fechamento", 8, "Os portões fecham", "Quem já estava na fila ainda vota.", "17:00", L("BR"), None, True),
            item("primeira_fim", 8, "A primeira cidade a terminar", "Cedro do Abaeté, às 16h36.", "16:36", L("MG", "Cedro do Abaeté"), None, True),
            item("stf", 8, "O STF estende a votação até as 19h", "Na Bahia, a votação segue.", "17:15", L("BA"), None, True),
            item("noronha", 8, "Fernando de Noronha, 18h49", "O último voto fora das grandes cidades.", "18:49:09", L("PE", "Fernando de Noronha", "0004", "0372"), 223, True),
            item("ultimo_voto", 8, "O último voto", "Em São Paulo, às 19h06.", "19:06:21", L("SP", "São Paulo", "0001", "0405"), None, True),
        ]],
    }


def cidades(towns, shares):
    """Per state: each town's facts and votes per hour band. Votes are real (v1); hours simulated."""
    rng = random.Random(7)
    by_uf: dict[str, dict] = {}
    for i, tid in enumerate(towns["id"]):
        uf, votos = towns["uf"][i], towns["votos"][i]
        jitter = [s * (1 + rng.uniform(-0.25, 0.25)) for s in shares]
        tot = sum(jitter)
        horas = [round(votos * j / tot) for j in jitter]
        acc, metade = 0, None
        for k, h in enumerate(horas):
            acc += h
            if metade is None and acc >= votos / 2:
                metade = f"{HORAS[k]:02d}:{rng.randint(0, 59):02d}"
        by_uf.setdefault(uf, {})[tid] = {
            "nome": towns["nome"][i], "votos": votos, "aptos": towns["aptos"][i],
            "secoes": towns["secoes"][i], "pico": hhmm(int(towns["pico_min"][i])),
            "metade": metade, "ultimo_voto": f"17:{rng.randint(5, 59):02d}", "horas": horas,
            "fechamento": f"17:{rng.randint(1, 25):02d}", "chegada": hhmm(17 * 60 + 30 + rng.randint(0, 150)),
        }
    for uf, cs in by_uf.items():
        dump(OUT / f"cidades/{uf}.json", {"mock": True, "uf": uf, "horas": HORAS, "cidades": cs})


def secoes():
    """Per state and zona: each section's day. Only three mock zonas; the page handles a miss."""
    rng = random.Random(331)
    for uf, zona, mun, n in [("MG", "0331", "Belo Horizonte", 420), ("SP", "0001", "São Paulo", 380), ("RS", "0060", "Pelotas", 300)]:
        ss = {}
        for k in range(1, n + 1):
            votos = rng.randint(180, 330)
            close = 17 * 60 + rng.randint(0, 40)
            arr = 17 * 60 + 20 + rng.randint(0, 200)
            ss[f"{k:04d}"] = {
                "municipio": mun, "abertura": "08:00", "primeiro_voto": f"08:0{rng.randint(0, 4)}",
                "ultimo_voto": hhmm(close - rng.randint(1, 5)), "encerramento": hhmm(close),
                "votos": votos, "aptos": votos + rng.randint(40, 90), "chegada": hhmm(arr),
            }
        dump(OUT / f"secoes/{uf}/{zona}.json", {"mock": True, "uf": uf, "zona": zona, "secoes": ss})


def chegada(ufs):
    """Bulletins arriving in Brasília per minute, 17:04 to 23:27. Simulated logistic curve."""
    start, end = 17 * 60 + 4, 23 * 60 + 27
    n = end - start + 1
    total = 497896

    def curve(scale, mid, width):
        cdf = [1 / (1 + math.exp(-(m - mid) / width)) for m in range(n)]
        lo, hi = cdf[0], cdf[-1]
        cum = [round(scale * (c - lo) / (hi - lo)) for c in cdf]
        return [cum[0]] + [cum[k] - cum[k - 1] for k in range(1, n)]

    rng = random.Random(23)
    return {
        "mock": True, "inicio": hhmm(start), "fim": hhmm(end), "total": total,
        "nacional": curve(total, 70, 22),
        "uf": {uf: curve(total // len(ufs), rng.randint(45, 110), rng.randint(15, 30)) for uf in ufs},
    }


def main():
    towns = json.loads((V1 / "towns.json").read_text())
    totals = json.loads((V1 / "totals.json").read_text())
    dump(OUT / "urna.json", urna(towns, totals))
    dump(OUT / "curiosidades.json", curiosidades())
    cidades(towns, national_hour_shares(totals))
    secoes()
    dump(OUT / "chegada.json", chegada(sorted(set(towns["uf"]))))
    print("mock written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
