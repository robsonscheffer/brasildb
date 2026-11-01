"""TSE and IBGE CSV loaders. Each returns a pyarrow Table with the catalog.yaml columns, in order.

Source files are latin-1, ";"-separated, with quoted strings and unquoted numbers. DuckDB reads
every column as text, then the SQL casts each one to its catalog type.
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

import duckdb
import httpx
import pyarrow as pa

# TSE placeholders for "no value". They become NULL in every column, since numeric
# columns would otherwise fail to cast.
_NULL_MARKERS = ("#NULO", "#NULO#", "#NE", "-1", "-3")

_ARROW = {
    "VARCHAR": pa.string(),
    "INTEGER": pa.int32(),
    "BIGINT": pa.int64(),
    "DATE": pa.date32(),
    "BOOLEAN": pa.bool_(),
    "TIMESTAMP": pa.timestamp("us"),
}


def _q(name: str) -> str:
    """Quote a source column name for SQL."""
    return '"' + name.replace('"', '""') + '"'


def _clean(src: str) -> str:
    """Source column with TSE null placeholders replaced by NULL."""
    markers = ", ".join(f"'{m}'" for m in _NULL_MARKERS)
    return f"(CASE WHEN {_q(src)} IN ({markers}) THEN NULL ELSE {_q(src)} END)"


# (catalog column, SQL expression over the raw CSV columns, catalog type)
_DETALHE = [
    ("ano", f"CAST({_clean('ANO_ELEICAO')} AS INTEGER)", "INTEGER"),
    ("turno", f"CAST({_clean('NR_TURNO')} AS INTEGER)", "INTEGER"),
    ("id_eleicao", _clean("CD_ELEICAO"), "VARCHAR"),
    ("tipo_eleicao", _clean("NM_TIPO_ELEICAO"), "VARCHAR"),
    ("data_eleicao", f"CAST(strptime({_clean('DT_ELEICAO')}, '%d/%m/%Y') AS DATE)", "DATE"),
    ("sigla_uf", f"upper({_clean('SG_UF')})", "VARCHAR"),
    ("id_municipio_tse", f"lpad({_clean('CD_MUNICIPIO')}, 5, '0')", "VARCHAR"),
    ("zona", f"lpad({_clean('NR_ZONA')}, 4, '0')", "VARCHAR"),
    ("secao", f"lpad({_clean('NR_SECAO')}, 4, '0')", "VARCHAR"),
    ("cargo", _clean("DS_CARGO"), "VARCHAR"),
    ("aptos", f"CAST({_clean('QT_APTOS')} AS BIGINT)", "BIGINT"),
    ("comparecimento", f"CAST({_clean('QT_COMPARECIMENTO')} AS BIGINT)", "BIGINT"),
    ("abstencoes", f"CAST({_clean('QT_ABSTENCOES')} AS BIGINT)", "BIGINT"),
    ("votos_nominais", f"CAST({_clean('QT_VOTOS_NOMINAIS')} AS BIGINT)", "BIGINT"),
    ("votos_brancos", f"CAST({_clean('QT_VOTOS_BRANCOS')} AS BIGINT)", "BIGINT"),
    ("votos_nulos", f"CAST({_clean('QT_VOTOS_NULOS')} AS BIGINT)", "BIGINT"),
    ("votos_legenda", f"CAST({_clean('QT_VOTOS_LEGENDA')} AS BIGINT)", "BIGINT"),
    ("votos_nulos_apu_sep", f"CAST({_clean('QT_VOTOS_ANULADOS_APU_SEP')} AS BIGINT)", "BIGINT"),
    ("id_local_votacao", _clean("NR_LOCAL_VOTACAO"), "VARCHAR"),
    (
        "secao_instalada",
        f"CASE {_clean('ST_SECAO_INSTALADA')} WHEN 'Sim' THEN TRUE WHEN 'Não' THEN FALSE END",
        "BOOLEAN",
    ),
    ("modelo_urna", _clean("DS_MODELO_URNA"), "VARCHAR"),
]

_VOTACAO = [
    ("ano", f"CAST({_clean('ANO_ELEICAO')} AS INTEGER)", "INTEGER"),
    ("turno", f"CAST({_clean('NR_TURNO')} AS INTEGER)", "INTEGER"),
    ("id_eleicao", _clean("CD_ELEICAO"), "VARCHAR"),
    ("sigla_uf", f"upper({_clean('SG_UF')})", "VARCHAR"),
    ("id_municipio_tse", f"lpad({_clean('CD_MUNICIPIO')}, 5, '0')", "VARCHAR"),
    ("zona", f"lpad({_clean('NR_ZONA')}, 4, '0')", "VARCHAR"),
    ("secao", f"lpad({_clean('NR_SECAO')}, 4, '0')", "VARCHAR"),
    ("cargo", _clean("DS_CARGO"), "VARCHAR"),
    ("numero_votavel", _clean("NR_VOTAVEL"), "VARCHAR"),
    ("nome_votavel", _clean("NM_VOTAVEL"), "VARCHAR"),
    ("sequencial_candidato", _clean("SQ_CANDIDATO"), "VARCHAR"),
    ("votos", f"CAST({_clean('QT_VOTOS')} AS BIGINT)", "BIGINT"),
    ("id_local_votacao", _clean("NR_LOCAL_VOTACAO"), "VARCHAR"),
]


def _ts(src: str) -> str:
    """'2026-10-25 19:42:19' as TIMESTAMP."""
    return f"CAST({_clean(src)} AS TIMESTAMP)"


_BOLETIM = [
    ("ano", f"CAST({_clean('ANO_ELEICAO')} AS INTEGER)", "INTEGER"),
    ("turno", f"CAST({_clean('NR_TURNO')} AS INTEGER)", "INTEGER"),
    ("sigla_uf", f"upper({_clean('SG_UF')})", "VARCHAR"),
    ("id_municipio_tse", f"lpad({_clean('CD_MUNICIPIO')}, 5, '0')", "VARCHAR"),
    ("zona", f"lpad({_clean('NR_ZONA')}, 4, '0')", "VARCHAR"),
    ("secao", f"lpad({_clean('NR_SECAO')}, 4, '0')", "VARCHAR"),
    ("id_local_votacao", _clean("NR_LOCAL_VOTACAO"), "VARCHAR"),
    ("secoes_agregadas", _clean("DS_SECOES_AGREGADAS"), "VARCHAR"),
    ("tipo_urna", _clean("DS_TIPO_URNA"), "VARCHAR"),
    ("id_urna", _clean("NR_URNA_EFETIVADA"), "VARCHAR"),
    ("data_hora_recebimento", _ts("DT_BU_RECEBIDO"), "TIMESTAMP"),
    ("data_hora_carga", _ts("DT_CARGA_URNA_EFETIVADA"), "TIMESTAMP"),
    ("data_hora_abertura", _ts("DT_ABERTURA"), "TIMESTAMP"),
    ("data_hora_encerramento", _ts("DT_ENCERRAMENTO"), "TIMESTAMP"),
    ("data_hora_emissao", _ts("DT_EMISSAO_BU"), "TIMESTAMP"),
    ("data_hora_geracao",
     f"strptime({_clean('DT_GERACAO')} || ' ' || {_clean('HH_GERACAO')}, '%d/%m/%Y %H:%M:%S')", "TIMESTAMP"),
]

_MUNICIPIO = [
    ("id_municipio", f"lpad({_q('CD_MUNICIPIO_IBGE')}, 7, '0')", "VARCHAR"),
    ("id_municipio_tse", f"lpad({_q('CD_MUNICIPIO_TSE')}, 5, '0')", "VARCHAR"),
    ("sigla_uf", f"upper({_q('SG_UF')})", "VARCHAR"),
    ("nome", _q("NM_MUNICIPIO_IBGE"), "VARCHAR"),
]


def _read(path: str, columns: list[tuple[str, str, str]], distinct: bool = False) -> pa.Table:
    select = ", ".join(f"{expr} AS {_q(name)}" for name, expr, _ in columns)
    source = str(path).replace("'", "''")
    sql = (
        f"SELECT {'DISTINCT ' if distinct else ''}{select} FROM read_csv('{source}', "
        "encoding='latin-1', delim=';', header=true, all_varchar=true)"
    )
    con = duckdb.connect()
    try:
        table = con.sql(sql).to_arrow_table()
    finally:
        con.close()
    schema = pa.schema([(name, _ARROW[typ]) for name, _, typ in columns])
    return table.cast(schema)


def read_detalhe_votacao_secao(path: str) -> pa.Table:
    """detalhe_votacao_secao_<ano>_<UF|BR>.csv as br_tse_eleicoes.detalhes_votacao_secao."""
    return _read(path, _DETALHE)


def read_votacao_secao(path: str) -> pa.Table:
    """votacao_secao_<ano>_<UF|BR>.csv as br_tse_eleicoes.votacao_secao."""
    return _read(path, _VOTACAO)


def read_boletim_urna_secao(path: str) -> pa.Table:
    """bweb_<turno>t_<UF>_<stamp>.csv as br_tse_eleicoes.boletim_urna_secao: one row per
    section. Raises if a section's times or urna differ between its rows, since then one row
    per section would hide data."""
    table = _read(path, _BOLETIM, distinct=True)
    keys = ["ano", "turno", "sigla_uf", "id_municipio_tse", "zona", "secao"]
    n_keys = table.group_by(keys).aggregate([]).num_rows
    if n_keys != table.num_rows:
        raise ValueError(f"{path}: {table.num_rows - n_keys} sections have more than one distinct row")
    return table


def read_municipio(path: str) -> pa.Table:
    """municipio_tse_ibge.csv as br_bd_diretorios_brasil.municipio."""
    return _read(path, _MUNICIPIO)


def fetch_zip_member(url: str, member: str, dest_dir: str, sha512: str | None = None) -> Path:
    """Stream the ZIP at url, extract only `member` into dest_dir, return its path.

    The ZIP is held in dest_dir only while it is read and is removed afterwards. If the member
    is already in dest_dir, nothing is downloaded. With sha512, a ZIP whose hash differs raises
    before anything is extracted.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / Path(member).name
    if target.exists():
        return target

    zip_path = dest / ".download.zip"
    try:
        with httpx.stream("GET", url, timeout=httpx.Timeout(60.0, read=300.0)) as response:
            response.raise_for_status()
            digest = hashlib.sha512()
            with zip_path.open("wb") as out:
                for chunk in response.iter_bytes():
                    out.write(chunk)
                    digest.update(chunk)
        if sha512 and digest.hexdigest() != sha512.lower():
            raise ValueError(f"{url}: SHA-512 does not match its .sha512 file")
        part = target.with_name(target.name + ".part")
        with zipfile.ZipFile(zip_path) as zf, zf.open(member) as src, part.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        part.replace(target)
    finally:
        zip_path.unlink(missing_ok=True)
    return target
