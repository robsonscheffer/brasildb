"""Tests for brasildb.tse.logparse on a real Roraima log (round 2, section 0001 of zone 0008)."""
from __future__ import annotations

import io
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pytest

from brasildb.tse.logparse import extract_logd, parse_logd, parse_logd_stats

FIXTURE = Path(__file__).parent / "fixtures" / "o03221rr0308500080001-log.jez"


@pytest.fixture(scope="module")
def logd() -> bytes:
    return extract_logd(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def parsed(logd: bytes) -> tuple[list[dict], int]:
    return parse_logd_stats(logd)


def test_extract_logd_finds_member_case_insensitively(logd: bytes) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pasta/LOGD.DAT", b"linha\n")
    assert extract_logd(buf.getvalue()) == b"linha\n"
    assert logd.count(b"\n") == 8453


def test_extract_logd_missing_member_raises() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("outro.txt", b"x")
    with pytest.raises(KeyError):
        extract_logd(buf.getvalue())


def test_all_lines_parse_and_none_skipped(parsed: tuple[list[dict], int]) -> None:
    rows, skipped = parsed
    assert skipped == 0
    assert len(rows) == 8453
    assert rows[0]["linha"] == 1
    assert rows[-1]["linha"] == 8453


def test_first_row_fields(parsed: tuple[list[dict], int]) -> None:
    row = parsed[0][0]
    assert row["data_hora"] == datetime(2026, 9, 23, 8, 11, 57)
    assert row["nivel"] == "INFO"
    assert row["id_urna"] == "02299969"
    assert row["componente"] == "LOGD"
    assert row["autenticador"] == "8FAB71A2975D7C33"
    assert "operações do logd" in row["mensagem"]  # latin-1 decoded, not mojibake
    assert row["tipo_evento"] is None
    assert row["valor"] is None


def test_voto_computado_counts_by_election_day(parsed: tuple[list[dict], int]) -> None:
    rows, _ = parsed
    dias = Counter(
        r["data_hora"].date() for r in rows if r["tipo_evento"] == "voto_computado"
    )
    assert dias[date(2026, 10, 25)] == 187
    assert dias[date(2026, 10, 4)] == 217


def test_habilitacao_valor_is_biometrica(parsed: tuple[list[dict], int]) -> None:
    habil = [r for r in parsed[0] if r["tipo_evento"] == "habilitacao"]
    assert len(habil) == 377
    assert all(r["valor"] == "biométrica" for r in habil)


def test_voto_confirmado_valor_is_the_office(parsed: tuple[list[dict], int]) -> None:
    confirmados = [r for r in parsed[0] if r["tipo_evento"] == "voto_confirmado"]
    assert len(confirmados) == 1489
    assert Counter(r["valor"] for r in confirmados)["Presidente"] == 404
    assert {r["valor"] for r in confirmados} == {
        "Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual",
    }


def test_untyped_message_has_null_valor(parsed: tuple[list[dict], int]) -> None:
    untyped = [r for r in parsed[0] if r["tipo_evento"] is None]
    assert untyped
    assert all(r["valor"] is None for r in untyped)


def test_parse_logd_yields_same_rows_as_stats(logd: bytes, parsed: tuple[list[dict], int]) -> None:
    assert list(parse_logd(logd)) == parsed[0]


def test_bad_lines_are_skipped_and_counted() -> None:
    data = (
        b"04/10/2026 07:01:42\tINFO\t02299969\tVOTA\tlinha curta\n"  # 4 fields
        b"31/02/2026 07:01:42\tINFO\t02299969\tVOTA\tdata invalida\tAAAA\n"  # bad date
        b"04/10/2026 07:01:42\tINFO\t02299969\tVOTA\tO voto do eleitor foi computado\tBBBB\r\n"
        b"\n"  # empty line inside the file
    )
    rows, skipped = parse_logd_stats(data)
    assert skipped == 3
    assert len(rows) == 1
    assert rows[0]["linha"] == 3
    assert rows[0]["tipo_evento"] == "voto_computado"
    assert rows[0]["autenticador"] == "BBBB"  # CR stripped
