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


def urna():
    """Screen 1: the first minutes of one urna's log. Mock lines, real log format."""
    lines = [
        ("07:00:02", "INICIO", "Urna ligada"),
        ("07:01:15", "ZERESIMA", "Zerésima impressa: 0 votos para cada candidato"),
        ("07:58:40", "ABERTURA", "Urna pronta para receber votos"),
        ("08:00:00", "ABERTURA", "Seção aberta"),
        ("08:00:41", "VOTO", "Eleitor habilitado por biometria"),
        ("08:00:58", "VOTO", "O voto foi computado"),
    ]
    rng = random.Random(41238)
    t = 8 * 3600 + 58
    for n in range(2, 13):
        t += rng.randint(35, 95)
        lines.append((f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}", "VOTO", "O voto foi computado"))
    return {
        "mock": True,
        "secao": {"uf": "MG", "municipio": "Belo Horizonte", "zona": "0331", "secao": "0060", "votos": 274},
        "linhas": [{"hora": h, "tipo": k, "texto": x} for h, k, x in lines],
        "fonte": "Log da urna, TSE (dados abertos)",
    }


def curiosidades():
    """Screens 2 to 5 and 8. Facts marked "certo": true come from v1's checked beats."""
    def item(id, tela, titulo, texto, hora, lugar, valor=None, certo=False):
        return {"id": id, "tela": tela, "titulo": titulo, "texto": texto, "hora": hora,
                "lugar": lugar, "valor": valor, "certo": certo, "sql": None}
    return {
        "mock": True,
        "itens": [
            item("primeira_urna", 2, "A primeira urna a abrir", "Ligou antes de todas, numa escola do interior.", "07:00:02", {"uf": "AM", "municipio": "Tabatinga"}),
            item("primeiro_voto", 2, "O primeiro voto do país", "Oito horas em ponto, mais alguns segundos.", "08:00:03", {"uf": "PE", "municipio": "Recife"}),
            item("abertura", 3, "O país abre de uma vez", "No mesmo minuto, de Brasília ao Acre, onde ainda são 6h da manhã.", "08:00", {"uf": "BR"}, 497896, True),
            item("pico", 3, "O pico", "420 mil votos por minuto.", "08:07", {"uf": "BR"}, 420000, True),
            item("marajo", 4, "Marajó, metade às 10h26", "No Marajó, metade da cidade já votou.", "10:26", {"uf": "PA", "municipio": "Marajó"}, None, True),
            item("almoco", 4, "O Nordeste para para almoçar", "São Paulo e Rio, quase não.", "12:00", {"uf": "NE"}, None, True),
            item("solimoes", 4, "Alto Solimões, nove em dez", "No Amazonas, nove em cada dez já votaram.", "13:55", {"uf": "AM", "municipio": "Alto Solimões"}, None, True),
            item("granizo", 5, "Granizo em Belo Horizonte", "163 locais de votação sem luz. As urnas seguiram na bateria.", "13:00", {"uf": "MG", "municipio": "Belo Horizonte"}, 163, True),
            item("bateria", 5, "A urna que mais tempo votou na bateria", "Ficou sem luz e seguiu recebendo votos.", "13:04", {"uf": "MG", "municipio": "Belo Horizonte", "zona": "0331", "secao": "0060"}, 277),
            item("contingencia", 5, "Urnas trocadas no meio do dia", "Quando uma urna falha, outra assume com os mesmos votos.", None, {"uf": "BR"}, 1204),
            item("fila", 5, "A fila mais longa", "A última pessoa da fila votou horas depois do fechamento.", "19:06", {"uf": "SP", "municipio": "São Paulo"}),
            item("fechamento", 8, "Os portões fecham", "Quem já estava na fila ainda vota.", "17:00", {"uf": "BR"}, None, True),
            item("stf", 8, "O STF estende a votação até as 19h", "Na Bahia, a votação segue.", "17:15", {"uf": "BA"}, None, True),
            item("ultimo_voto", 8, "O último voto", "Em São Paulo, às 19h06.", "19:06", {"uf": "SP", "municipio": "São Paulo"}, None, True),
        ],
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
    dump(OUT / "urna.json", urna())
    dump(OUT / "curiosidades.json", curiosidades())
    cidades(towns, national_hour_shares(totals))
    secoes()
    dump(OUT / "chegada.json", chegada(sorted(set(towns["uf"]))))
    print("mock written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
