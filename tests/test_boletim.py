"""BU files (boletim de urna) -> boletim_urna_secao: real Acre rows, CKAN lookup, SHA-512 check."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx
import yaml

from brasildb import cli
from brasildb.tse.csv_tables import fetch_zip_member, read_boletim_urna_secao

FIXTURES = Path(__file__).parent / "fixtures"
BWEB = FIXTURES / "bweb_2t_ac_sample.csv"  # 2 sections of Acre, round 2 of 2026, both offices
CATALOG = Path(__file__).parents[1] / "catalog.yaml"
ARROW_FOR = {"VARCHAR": pa.string(), "INTEGER": pa.int32(), "TIMESTAMP": pa.timestamp("us")}


def test_columns_match_catalog_names_types_and_order():
    cols = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["br_tse_eleicoes"]["boletim_urna_secao"]["columns"]
    table = read_boletim_urna_secao(str(BWEB))
    assert [(f.name, f.type) for f in table.schema] == [(n, ARROW_FOR[t]) for n, t in cols.items()]


def test_one_row_per_section_with_its_times():
    rows = {r["secao"]: r for r in read_boletim_urna_secao(str(BWEB)).to_pylist()}
    assert sorted(rows) == ["0036", "0131"]
    r = rows["0131"]
    assert (r["sigla_uf"], r["id_municipio_tse"], r["zona"], r["ano"], r["turno"]) == ("AC", "01538", "0008", 2026, 2)
    # aux.json hashes[].hr of this section is 19:58:25 too
    assert r["data_hora_recebimento"] == datetime(2026, 10, 25, 19, 58, 25)
    assert r["data_hora_geracao"] == datetime(2026, 10, 26, 7, 42, 38)
    assert r["tipo_urna"] == "Apurada"


def test_a_section_with_two_different_rows_raises(tmp_path: Path):
    lines = BWEB.read_bytes().splitlines(keepends=True)
    changed = lines[1].replace(b"2026-10-25 19:33:26", b"2026-10-25 20:00:00")
    assert changed != lines[1]
    bad = tmp_path / "bweb.csv"
    bad.write_bytes(b"".join([lines[0], lines[1], changed]))
    with pytest.raises(ValueError, match="more than one distinct row"):
        read_boletim_urna_secao(str(bad))


def test_boletim_files_reads_hash_resources_and_keeps_the_newest():
    base = "https://cdn.test/buweb"
    package = {"resources": [
        {"url": f"{base}/bweb_2t_AC_261020260742.zip"},
        {"url": f"{base}/bweb_2t_AC_261020260742.zip.sha512"},
        {"url": f"{base}/bweb_2t_RR_261020260742.zip.sha512"},  # RR lists only its hash file
        {"url": f"{base}/bweb_2t_RR_261020260742.zip.sha512"},
        {"url": f"{base}/bweb_2t_SP_251020262300.zip.sha512"},
        {"url": f"{base}/bweb_2t_SP_261020260742.zip.sha512"},
        {"url": f"{base}/bweb_1t_SP_051020261403.zip.sha512"},
    ]}
    assert cli.boletim_files(package, 2) == {
        "AC": (f"{base}/bweb_2t_AC_261020260742.zip", "bweb_2t_AC_261020260742.csv"),
        "RR": (f"{base}/bweb_2t_RR_261020260742.zip", "bweb_2t_RR_261020260742.csv"),
        "SP": (f"{base}/bweb_2t_SP_261020260742.zip", "bweb_2t_SP_261020260742.csv"),
    }


def _zip(member: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, data)
    return buf.getvalue()


def test_fetch_zip_member_checks_sha512(tmp_path: Path):
    url = "https://cdn.test/bweb_2t_AC_1.zip"
    payload = _zip("bweb_2t_AC_1.csv", b"x")
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, content=payload))
        with pytest.raises(ValueError, match="SHA-512"):
            fetch_zip_member(url, "bweb_2t_AC_1.csv", str(tmp_path / "bad"), sha512="00" * 64)
        assert not (tmp_path / "bad" / "bweb_2t_AC_1.csv").exists()
        good = fetch_zip_member(url, "bweb_2t_AC_1.csv", str(tmp_path / "ok"),
                                sha512=hashlib.sha512(payload).hexdigest())
    assert good.read_bytes() == b"x"
