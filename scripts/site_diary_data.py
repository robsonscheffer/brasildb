"""Build the v3 diary's public, allowlisted data. Never publish raw log messages.

Run from the repo: BRASILDB_DATA=/path/to/data uv run python scripts/site_diary_data.py
The prototype deliberately covers one section, not a general section browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from brasildb import config, lake

SECTION = dict(ano=2026, turno=2, sigla_uf="MG", id_municipio_tse="41238",
               zona="0331", secao="0060")
DAY = config.ELECTIONS[(2026, 2)].data
# main.fuso_municipio: Belo Horizonte has the same clock as Brasília.
FUSO = 0
ROOT = Path(__file__).resolve().parent.parent


def clock(value: datetime) -> str:
    return (value - timedelta(hours=FUSO)).strftime("%H:%M:%S")


def national_events(totals: dict) -> list[dict]:
    counts = totals["national"]
    total = sum(counts)
    accumulated, cumulative = 0, []
    for count in counts:
        accumulated += count
        cumulative.append(accumulated)
    milestones = [
        (next(i for i, n in enumerate(cumulative) if n >= 1_000_000),
         "1 milhão", "de votos registrados no país", "million"),
        (counts.index(max(counts)),
         f'{max(counts):,}'.replace(",", "."), "votos no minuto mais movimentado", "peak"),
        (next(i for i, n in enumerate(cumulative) if n >= total / 2),
         "Metade dos votos", "registrados nos logs do país neste dia", "half"),
        (next(i for i, n in enumerate(cumulative) if n >= 100_000_000),
         "100 milhões", "de votos registrados no país", "hundred-million"),
    ]
    return [
        dict(time=f"{(totals['start'] + minute) // 60:02}:{(totals['start'] + minute) % 60:02}:00",
             type="national", label=label, detail=detail, key=key,
             precision="minute", source="totals")
        for minute, label, detail, key in milestones
    ]


def build_diary(rows: list[dict], cs: dict, totals: dict, final: dict) -> dict:
    day = sorted((r for r in rows if r["data_hora"].date() == DAY),
                 key=lambda r: (r["data_hora"], r["linha"]))
    if not day or len({r["arquivo_membro"] for r in day}) != 1:
        raise ValueError("This one-urna prototype expects exactly one election-day log.")
    models = {r["valor"] for r in day if r["tipo_evento"] == "modelo_urna"}
    if len(models) != 1:
        raise ValueError("Expected one recorded urna model.")
    model = models.pop()
    vote_rows = [r for r in day if r["tipo_evento"] == "voto_computado"]
    if not vote_rows:
        raise ValueError("No votes for the selected day.")
    first, last = vote_rows[0]["data_hora"], vote_rows[-1]["data_hora"]
    energy = [r for r in day if r["tipo_evento"] == "energia"]
    switches = [r for r in energy if r["valor"] == "bateria" and first < r["data_hora"] < last]
    episodes = []
    for switch in switches:
        following = next((r for r in energy if (r["data_hora"], r["linha"]) >
                          (switch["data_hora"], switch["linha"])), None)
        returned = following if following and following["valor"] == "rede" else None
        episodes.append(dict(
            start=clock(switch["data_hora"]),
            end=clock(returned["data_hora"]) if returned else None,
            seconds=int((returned["data_hora"] - switch["data_hora"]).total_seconds()) if returned else None,
        ))

    events, votes, started, reported = [], 0, False, set()
    for row in day:
        kind, value = row["tipo_evento"], row["valor"]
        event_type, label = None, None
        if kind == "urna_ligada" and not started:
            event_type, label, started = "boot", "URNA LIGADA", True
        elif kind == "urna_pronta":
            event_type, label = "open", "PRONTA PARA RECEBER VOTOS"
        elif kind == "voto_computado":
            votes += 1
            event_type, label = "vote", "VOTO COMPUTADO"
        elif kind == "energia" and value in ("rede", "bateria"):
            event_type = "battery" if value == "bateria" else "mains"
            label = "OPERANDO NA BATERIA" if value == "bateria" else "OPERANDO NA REDE"
        elif kind == "relatorio" and value in ("ZERÉSIMA", "BU") and value not in reported:
            reported.add(value)
            event_type = "zero" if value == "ZERÉSIMA" else "bulletin"
            label = "ZERÉSIMA IMPRESSA" if value == "ZERÉSIMA" else "BOLETIM DE URNA IMPRESSO"
        elif kind == "encerramento":
            event_type, label = "close", "VOTAÇÃO ENCERRADA"
        # These are periodic connection reports, NOT power-on events. The missing
        # energia=rede transition must not become a claim of eight hours without power.
        elif (kind == "urna_ligada" and switches and
              row["data_hora"] > switches[-1]["data_hora"] and
              "conectada na rede CA" in row["mensagem"]):
            event_type, label = "network-report", "CONEXÃO À REDE REGISTRADA"
        if event_type:
            events.append(dict(time=clock(row["data_hora"]), type=event_type,
                               label=label, votes=votes, line=row["linha"], source="log"))

    arrivals = [
        section for area in cs["abr"] for town in area["mu"]
        if town["cd"] == SECTION["id_municipio_tse"]
        for zone in town["zon"] if zone["cd"] == SECTION["zona"]
        for section in zone["sec"] if section["ns"] == SECTION["secao"]
    ]
    if len(arrivals) != 1 or arrivals[0]["da"] != DAY.strftime("%d/%m/%Y"):
        raise ValueError("Expected one same-day TSE section record.")
    arrival = arrivals[0]
    if not (final["s"]["st"] == final["s"]["ts"] and final["dg"] == DAY.strftime("%d/%m/%Y")):
        raise ValueError("Expected the final national file with 100% of sections totalized.")
    events += national_events(totals)
    events += [
        dict(time=arrival["ha"], type="arrival", label="RESULTADO REGISTRADO NO TSE",
             votes=votes, source="cs"),
        dict(time=final["hg"], type="final", label="100% DAS SEÇÕES TOTALIZADAS",
             votes=votes, source="national-final"),
    ]
    events.sort(key=lambda e: (e["time"], e.get("line", 0)))
    count = 0
    for event in events:
        if event["type"] == "vote":
            count += 1
        event["votes"] = count

    return dict(
        schema=1,
        section={**SECTION, "municipio": "Belo Horizonte", "date": DAY.isoformat(),
                 "urna": day[0]["id_urna"], "model": model, "timezone": "America/Sao_Paulo"},
        summary=dict(votes=votes, first_vote=clock(first), last_vote=clock(last),
                     battery_switches=len(switches), battery_episodes=episodes,
                     arrival=arrival["ha"], national_total=sum(totals["national"]),
                     totalized_sections=int(final["s"]["st"]),
                     final_totalization=final["ht"], final_file_generated=final["hg"]),
        events=events,
        notes=[
            "Reconstrução editorial. A fita não é uma zerésima nem um boletim oficial.",
            "Horários do relógio da urna, no fuso de Brasília. Não são um relógio auditado.",
            "Cada VOTO COMPUTADO é um registro do log. A fita não identifica eleitores nem suas escolhas.",
            "Os marcos nacionais têm precisão de um minuto e usam os logs coletados, não a apuração.",
            "A segunda entrada em bateria não tem retorno explícito no evento energia. "
            "Há registros posteriores de conexão à rede. Não é possível afirmar a duração da falta de energia.",
            "ha é o horário registrado no arquivo de seções do TSE, não uma prova da primeira transmissão.",
            "23:27:02 é a geração do arquivo nacional final, que já mostra 100%. "
            "Não é o instante em que o resultado foi definido.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, help="Optional cached Parquet for this section")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/site/v3/data/secao.json")
    args = parser.parse_args()
    settings = config.load()
    con = lake.connect(settings.lake) if not args.events else duckdb.connect()
    source = "br_tse_urna_logs.eventos"
    if args.events:
        con.read_parquet(str(args.events)).create_view("cached")
        source = "cached"
    where = " and ".join(f"{key} = ?" for key in SECTION)
    cursor = con.execute(f"select * from {source} where {where}", list(SECTION.values()))
    rows = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
    paths = {
        "cs": Path(settings.raw) / "cs/mg-p003221-cs.json",
        "national-final": Path(settings.raw) / "cs/br-c0001-e006258-u.json",
        "totals": ROOT / "docs/site/data/totals.json",
    }
    inputs = {key: json.loads(path.read_text()) for key, path in paths.items()}
    diary = build_diary(rows, inputs["cs"], inputs["totals"], inputs["national-final"])
    diary["sources"] = {
        key: dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for key, path in paths.items()
    }
    archive = (Path(settings.raw) / "2026/2/mg" /
               f"{rows[0]['arquivo_hash'][:12]}-o03221mg4123803310060-log.jez")
    diary["sources"]["log"] = dict(
        file=archive.name, member="logd.dat",
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(diary, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(diary['events'])} records, {diary['summary']['votes']} votes -> {args.out}")


if __name__ == "__main__":
    main()
