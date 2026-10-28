"""Nested archives (a replaced urna's log inside the closing urna's), the new event types,
and the reparse command on raw files."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from brasildb import cli
from brasildb.tse.logparse import _classify, extract_logd, extract_logds

FIXTURE = Path(__file__).parent / "fixtures" / "o03221rr0308500080001-log.jez"


def _nested(outer_lines: bytes, inner_lines: bytes) -> bytes:
    """An archive shaped like a replaced urna's: logd.dat plus <id>.jez holding its own logd.dat."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("logd.dat", inner_lines)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("024722252510202615584201ME.jez", inner.getvalue())
        zf.writestr("logd.dat", outer_lines)
    return buf.getvalue()


LINE = "25/10/2026 10:00:0{i}\tINFO\t{urna}\tVOTA\tO voto do eleitor foi computado\t0123456789ABCDEF\n"


def test_extract_logds_returns_nested_first_then_outer() -> None:
    jez = _nested(b"outer\n", b"inner\n")
    assert extract_logds(jez) == [("024722252510202615584201ME.jez/logd.dat", b"inner\n"), ("logd.dat", b"outer\n")]
    assert extract_logd(jez) == b"outer\n"


def test_extract_logds_plain_archive_has_one_member() -> None:
    members = extract_logds(FIXTURE.read_bytes())
    assert [m for m, _ in members] == ["logd.dat"]
    assert members[0][1].count(b"\n") == 8453


def test_extract_logds_without_outer_raises() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.txt", b"")
    with pytest.raises(KeyError):
        extract_logds(buf.getvalue())


def test_parse_archive_keeps_both_urnas_apart() -> None:
    outer = "".join(LINE.format(i=i, urna="02472225") for i in range(2)).encode("latin-1")
    inner = "".join(LINE.format(i=i, urna="02418616") for i in range(3)).encode("latin-1")
    rows = cli.parse_archive("abc123", _nested(outer, inner))
    assert len(rows) == 5
    assert {(r["arquivo_membro"], r["id_urna"]) for r in rows} == {
        ("024722252510202615584201ME.jez/logd.dat", "02418616"), ("logd.dat", "02472225")}
    assert all(r["arquivo_hash"] == "abc123" and r["tipo_evento"] == "voto_computado" for r in rows)
    # linha restarts per member; the key is (arquivo_hash, arquivo_membro, linha)
    assert sorted(r["linha"] for r in rows if r["arquivo_membro"] == "logd.dat") == [1, 2]


@pytest.mark.parametrize("mensagem, tipo, valor", [
    ("Urna pronta para receber votos", "urna_pronta", None),
    ("Operador selecionou: Encerrar votação", "encerramento", None),
    ("Urna operando na bateria interna", "energia", "bateria"),
    ("Urna operando com rede elétrica", "energia", "rede"),
    ("Operando com a bateria interna", "energia", "bateria"),
    ("Urna operando com bateria interna", "energia", "bateria"),
    ("Identificação do Modelo de Urna: UE2020", "modelo_urna", "UE2020"),
    ("Versão da aplicação: 9.2.0.1 - Praia da Barra do Cahy", "versao_aplicacao", "9.2.0.1"),
    ("Solicita digital. Tentativa [2] de [4]", "solicita_digital", "2"),
    ("Timeout de reconhecimento do dedo. Tentativa [4] de [4]", "timeout_digital", None),
    ("Batimento de digitais retornou o score 1850", "score_digital", "1850"),
    ("Solicitação de dado pessoal do eleitor para habilitação manual", "habilitacao_manual", None),
    ("Identificador digitado pelo mesário foi: (CPF)", "identificador", "CPF"),
    ("Eleitor sem atividade por 30 segundos", "sem_atividade", "30"),
    ("Tecla indevida pressionada", "tecla_indevida", None),
    ("Tecla pressionada: BRANCO", "tecla", "BRANCO"),
    ("Justificativa recebida", "justificativa", None),
    ("Mesário 2 registrado", "mesario_registrado", "2"),
    ("Imprimindo relatório [BU] via nº [1]", "relatorio", "BU"),
    ("O voto do eleitor foi computado", "voto_computado", None),
    ("Espaço livre na MI [3.2 GB]", None, None),
])
def test_new_event_types(mensagem: str, tipo: str | None, valor: str | None) -> None:
    assert _classify(mensagem) == (tipo, valor)


def test_raw_name_pattern() -> None:
    m = cli.RAW_NAME.match("4737536b7055-o03221mg4371003130255-log.jez")
    assert m and m.groupdict() == {"hash": "4737536b7055", "pleito": "3221", "uf": "mg",
                                   "mun": "43710", "zona": "0313", "secao": "0255"}
    assert cli.RAW_NAME.match("o03221mg4371003130255-log.jez") is None


def test_reparse_writes_eventos_from_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw" / "2026" / "2" / "rr"
    raw.mkdir(parents=True)
    (raw / "0123456789ab-o03221rr0308500080001-log.jez").write_bytes(FIXTURE.read_bytes())
    monkeypatch.setenv("BRASILDB_DATA", str(tmp_path))
    monkeypatch.setenv("BRASILDB_PARSE_WORKERS", "1")
    out = tmp_path / "lake2"
    cli.main(["reparse", "--turno", "2", "--ufs", "rr", "--out", str(out)])
    con = __import__("brasildb.lake", fromlist=["connect"]).connect(str(out))
    n, hashes, membros = con.execute(
        "SELECT count(*), count(DISTINCT arquivo_hash), count(DISTINCT arquivo_membro) "
        "FROM br_tse_urna_logs.eventos WHERE sigla_uf='RR' AND id_municipio_tse='03085'").fetchone()
    assert (n, hashes, membros) == (8453, 1, 1)
