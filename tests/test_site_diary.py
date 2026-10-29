"""The diary's public payload is smaller than, and never a dump of, the raw log."""
import hashlib
import json
from datetime import datetime

import pytest

from scripts.site_diary_data import ROOT, build_diary


def inputs():
    def row(time, kind, value=None, message="PRIVATE-MESARIO-IDENTIFIER"):
        return dict(data_hora=datetime.fromisoformat("2026-10-25T" + time),
                    tipo_evento=kind, valor=value, mensagem=message, id_urna="02322500",
                    arquivo_membro="logd.dat", linha=0)

    rows = [
        row("07:04:30", "urna_ligada"),
        row("07:04:55", "modelo_urna", "UE2022"),
        row("07:05:12", "energia", "bateria"),
        row("07:06:59", "energia", "rede"),
        row("07:16:14", "relatorio", "ZERÉSIMA"),
        row("08:00:01", "urna_pronta"),
        row("08:01:53", "voto_computado"),
        row("08:06:59", "urna_ligada", message="Urna ligada conectada na rede CA"),
        row("08:38:26", "energia", "bateria"),
        row("08:39:43", "voto_computado"),
        row("08:43:03", "energia", "rede"),
        row("08:43:04", "energia", "bateria"),
        row("10:06:59", "urna_ligada", message="Urna ligada conectada na rede CA"),
        row("16:50:16", "voto_computado"),
        row("17:00:06", "encerramento"),
        row("17:00:42", "relatorio", "BU"),
        row("17:00:45", "relatorio", "BU"),
        row("17:01:00", "mesario_registrado", "PRIVATE-MESARIO-IDENTIFIER"),
        row("17:01:01", "identificador", "PRIVATE-VOTER-IDENTIFIER"),
    ]
    for i, item in enumerate(rows):
        item["linha"] = i + 1
    old = row("08:01:53", "voto_computado")
    old["data_hora"] = datetime(2026, 10, 4, 8, 1, 53)
    rows.append(old)
    cs = {"abr": [{"mu": [{"cd": "41238", "zon": [{"cd": "0331", "sec": [
        {"ns": "0060", "da": "25/10/2026", "ha": "19:09:38"},
    ]}]}]}]}
    totals = {"start": 480, "national": [0, 1_000_000, 49_000_000, 50_000_000, 1_000_000]}
    final = {"dg": "25/10/2026", "hg": "23:27:02", "ht": "23:26:38",
             "s": {"st": "499248", "ts": "499248"}}
    return rows, cs, totals, final


def test_diary_allowlists_events_and_fields():
    diary = build_diary(*inputs())
    text = json.dumps(diary)
    assert "PRIVATE" not in text
    for field in ("mensagem", "valor", "identificador", "mesario_registrado"):
        assert f'"{field}"' not in text
    assert diary["summary"]["votes"] == 3
    assert [e["votes"] for e in diary["events"] if e["type"] == "vote"] == [1, 2, 3]
    assert [e["time"] for e in diary["events"]] == sorted(e["time"] for e in diary["events"])
    assert sum(e["type"] == "bulletin" for e in diary["events"]) == 1


def test_periodic_connection_reports_are_not_reboots():
    diary = build_diary(*inputs())
    assert sum(e["type"] == "boot" for e in diary["events"]) == 1
    reports = [e for e in diary["events"] if e["type"] == "network-report"]
    assert [e["time"] for e in reports] == ["10:06:59"]


def test_missing_return_is_unknown_not_eight_hours_of_battery():
    diary = build_diary(*inputs())
    assert diary["summary"]["battery_switches"] == 2
    assert diary["summary"]["battery_episodes"] == [
        {"start": "08:38:26", "end": "08:43:03", "seconds": 277},
        {"start": "08:43:04", "end": None, "seconds": None},
    ]


def test_national_minutes_and_tse_publication_keep_their_meanings():
    diary = build_diary(*inputs())
    national = [e for e in diary["events"] if e["type"] == "national"]
    assert len(national) == 4
    assert all(e["precision"] == "minute" for e in national)
    assert diary["events"][-2]["time"] == "19:09:38"
    assert diary["events"][-1]["time"] == "23:27:02"
    assert diary["summary"]["final_totalization"] == "23:26:38"


def test_refuse_a_missing_section_or_unfinished_national_file():
    rows, cs, totals, final = inputs()
    cs["abr"][0]["mu"][0]["zon"][0]["sec"][0]["ns"] = "9999"
    with pytest.raises(ValueError, match="same-day"):
        build_diary(rows, cs, totals, final)
    rows, cs, totals, final = inputs()
    final["s"]["st"] = "1"
    with pytest.raises(ValueError, match="100%"):
        build_diary(rows, cs, totals, final)


def test_refuse_multiple_urnas_in_this_single_urna_prototype():
    rows, cs, totals, final = inputs()
    rows[0]["arquivo_membro"] = "replaced.jez/logd.dat"
    with pytest.raises(ValueError, match="one election-day log"):
        build_diary(rows, cs, totals, final)


def test_committed_payload_matches_the_site_totals_and_274_votes():
    diary = json.loads((ROOT / "docs/site/v3/data/secao.json").read_text())
    totals_path = ROOT / "docs/site/data/totals.json"
    totals = json.loads(totals_path.read_text())
    assert diary["summary"]["votes"] == 274
    assert diary["summary"]["national_total"] == sum(totals["national"])
    assert diary["sources"]["totals"]["sha256"] == hashlib.sha256(totals_path.read_bytes()).hexdigest()
    votes = [e for e in diary["events"] if e["type"] == "vote"]
    assert [e["votes"] for e in votes] == list(range(1, 275))
    assert all(set(e) <= {"time", "type", "label", "votes", "line", "source"} for e in votes)
    assert votes[0]["time"] == diary["summary"]["first_vote"]
    assert votes[-1]["time"] == diary["summary"]["last_vote"]
    assert diary["summary"]["battery_episodes"][1]["seconds"] is None
    assert [e["time"] for e in diary["events"]] == sorted(e["time"] for e in diary["events"])
