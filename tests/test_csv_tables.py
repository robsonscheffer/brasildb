"""CSV loaders: catalog columns and types, real Roraima fixtures, and ZIP fetch with respx (no network)."""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx
import yaml

from brasildb.tse.csv_tables import fetch_zip_member, read_detalhe_votacao_secao, read_municipio

FIXTURES = Path(__file__).parent / "fixtures"
DETALHE = FIXTURES / "detalhe_votacao_secao_2026_BR_rr_sample.csv"
MUNICIPIO = FIXTURES / "municipio_tse_ibge_rr.csv"
CATALOG = Path(__file__).parents[1] / "catalog.yaml"

ARROW_FOR = {
    "VARCHAR": pa.string(),
    "INTEGER": pa.int32(),
    "BIGINT": pa.int64(),
    "DATE": pa.date32(),
    "BOOLEAN": pa.bool_(),
}


def _catalog_columns(dataset: str, table: str) -> dict[str, str]:
    """Catalog columns as {name: TYPE}, in catalog order (YAML mappings keep order)."""
    spec = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    return dict(spec[dataset][table]["columns"])


def _schema_pairs(table: pa.Table) -> list[tuple[str, pa.DataType]]:
    return [(f.name, f.type) for f in table.schema]


def _expected_pairs(dataset: str, table: str) -> list[tuple[str, pa.DataType]]:
    return [(name, ARROW_FOR[typ]) for name, typ in _catalog_columns(dataset, table).items()]


def test_catalog_types_are_mapped():
    """Every type the loaders use has an Arrow mapping in this test file."""
    used = set(_catalog_columns("br_tse_eleicoes", "detalhes_votacao_secao").values())
    used |= set(_catalog_columns("br_bd_diretorios_brasil", "municipio").values())
    assert used <= set(ARROW_FOR)


def test_detalhe_columns_match_catalog_names_types_and_order():
    table = read_detalhe_votacao_secao(str(DETALHE))
    assert _schema_pairs(table) == _expected_pairs("br_tse_eleicoes", "detalhes_votacao_secao")


def test_municipio_columns_match_catalog_names_types_and_order():
    table = read_municipio(str(MUNICIPIO))
    assert _schema_pairs(table) == _expected_pairs("br_bd_diretorios_brasil", "municipio")


def test_detalhe_row_count_covers_both_rounds():
    table = read_detalhe_votacao_secao(str(DETALHE))
    assert table.num_rows == 276  # 138 rows per round in the sample
    assert sorted(set(table.column("turno").to_pylist())) == [1, 2]


def test_detalhe_section_comparecimento_matches_log_check():
    """RR 03085/0008/0001: the urna log counts (187 round 2, 217 round 1) match turnout."""
    rows = read_detalhe_votacao_secao(str(DETALHE)).to_pylist()
    section = [
        r
        for r in rows
        if r["id_municipio_tse"] == "03085" and r["zona"] == "0008" and r["secao"] == "0001"
        and r["cargo"] == "Presidente"
    ]
    by_turno = {r["turno"]: r for r in section}
    assert by_turno[2]["comparecimento"] == 187
    assert by_turno[1]["comparecimento"] == 217
    assert by_turno[2]["data_eleicao"] == date(2026, 10, 25)
    assert by_turno[1]["data_eleicao"] == date(2026, 10, 4)
    assert by_turno[2]["sigla_uf"] == "RR"
    assert by_turno[2]["tipo_eleicao"] == "Eleição Ordinária"
    assert by_turno[2]["id_eleicao"] == "6258"
    assert by_turno[2]["modelo_urna"] == "UE 2022"


def test_detalhe_codes_are_zero_padded_and_uf_upper_case():
    rows = read_detalhe_votacao_secao(str(DETALHE)).to_pylist()
    assert {len(r["id_municipio_tse"]) for r in rows} == {5}
    assert {len(r["zona"]) for r in rows} == {4}
    assert {len(r["secao"]) for r in rows} == {4}
    assert {r["sigla_uf"] for r in rows} == {"RR"}


def test_detalhe_secao_instalada_is_boolean_from_sim_nao():
    rows = read_detalhe_votacao_secao(str(DETALHE)).to_pylist()
    assert {r["secao_instalada"] for r in rows} == {True}


def test_detalhe_null_placeholders_become_null(tmp_path):
    """#NULO, #NULO#, #NE, -1 and -3 are NULL; a real value is kept."""
    with DETALHE.open(encoding="latin-1", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        header = next(reader)
        row = next(reader)
    fields = dict(zip(header, row, strict=True))
    fields.update(
        {
            "QT_APTOS": "-1",
            "QT_COMPARECIMENTO": "#NULO",
            "QT_ABSTENCOES": "-3",
            "NR_LOCAL_VOTACAO": "#NE",
            "DS_MODELO_URNA": "#NULO#",
            "DS_CARGO": "Governador",
        }
    )
    path = tmp_path / "markers.csv"
    with path.open("w", encoding="latin-1", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(header)
        writer.writerow([fields[name] for name in header])

    (out,) = read_detalhe_votacao_secao(str(path)).to_pylist()
    assert out["aptos"] is None
    assert out["comparecimento"] is None
    assert out["abstencoes"] is None
    assert out["id_local_votacao"] is None
    assert out["modelo_urna"] is None
    assert out["cargo"] == "Governador"


def test_municipio_has_15_roraima_municipalities():
    rows = read_municipio(str(MUNICIPIO)).to_pylist()
    assert len(rows) == 15
    assert {r["sigla_uf"] for r in rows} == {"RR"}
    assert {len(r["id_municipio_tse"]) for r in rows} == {5}
    assert {len(r["id_municipio"]) for r in rows} == {7}


def test_municipio_boa_vista_codes():
    rows = {r["nome"]: r for r in read_municipio(str(MUNICIPIO)).to_pylist()}
    assert rows["Boa Vista"]["id_municipio_tse"] == "03018"
    assert rows["Boa Vista"]["id_municipio"] == "1400100"


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_fetch_zip_member_extracts_only_member_and_skips_second_download(tmp_path):
    url = "https://ckan.test/detalhe_votacao_secao_2026.zip"
    payload = _zip_bytes(
        {"outro.csv": b"nao", "detalhe_votacao_secao_2026_BR.csv": b"alvo"}
    )
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url).mock(return_value=httpx.Response(200, content=payload))

        path = fetch_zip_member(url, "detalhe_votacao_secao_2026_BR.csv", str(tmp_path))
        assert path == tmp_path / "detalhe_votacao_secao_2026_BR.csv"
        assert path.read_bytes() == b"alvo"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["detalhe_votacao_secao_2026_BR.csv"]

        again = fetch_zip_member(url, "detalhe_votacao_secao_2026_BR.csv", str(tmp_path))
        assert again == path
        assert route.call_count == 1


def test_fetch_zip_member_http_error_leaves_no_file(tmp_path):
    url = "https://ckan.test/missing.zip"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            fetch_zip_member(url, "detalhe_votacao_secao_2026_BR.csv", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_fetch_zip_member_missing_member_raises_and_leaves_no_file(tmp_path):
    url = "https://ckan.test/detalhe_votacao_secao_2026.zip"
    payload = _zip_bytes({"outro.csv": b"nao"})
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, content=payload))
        with pytest.raises(KeyError):
            fetch_zip_member(url, "detalhe_votacao_secao_2026_BR.csv", str(tmp_path))
    assert list(tmp_path.iterdir()) == []
