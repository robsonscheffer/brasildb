"""Urna log parser: <name>-log.jez (a ZIP) -> logd.dat -> one dict per line.

Standard library only. Row keys match br_tse_urna_logs.eventos (catalog.yaml), minus the
partition and key columns that the caller adds.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import PurePosixPath

# Ordered: the first pattern that matches a message gives tipo_evento. Group 1, when present, is valor.
EVENT_TYPES: list[tuple[str, re.Pattern[str]]] = [
    ("voto_computado", re.compile(r"O voto do eleitor foi computado")),
    ("habilitacao", re.compile(r"Tipo de habilitação do eleitor \[(.+?)\]")),
    ("voto_confirmado", re.compile(r"Voto confirmado para \[(.+?)\]")),
    ("eleitor_habilitado", re.compile(r"Eleitor foi habilitado")),
    ("inicio_aplicacao", re.compile(r"Iniciando aplicação - (.+)")),
    ("urna_ligada", re.compile(r"Urna ligada (?:conectada na rede CA )?em")),
    ("correcao", re.compile(r"Eleitor corrigiu")),
    ("digital_capturada", re.compile(r"Capturada a digital")),
    ("contingencia", re.compile(r"Modo de carga da UE - Urna de contingência")),
]

_FIELDS = 6
_TIMESTAMP = "%d/%m/%Y %H:%M:%S"


def extract_logd(jez: bytes) -> bytes:
    """Return the logd.dat member of a log archive. The name match is case-insensitive."""
    with zipfile.ZipFile(io.BytesIO(jez)) as zf:
        for name in zf.namelist():
            if PurePosixPath(name).name.lower() == "logd.dat":
                return zf.read(name)
    raise KeyError("logd.dat not found in log archive")


def _classify(mensagem: str) -> tuple[str | None, str | None]:
    for tipo, rx in EVENT_TYPES:
        m = rx.search(mensagem)
        if m:
            return tipo, (m.group(1) if rx.groups else None)
    return None, None


def _lines(data: bytes) -> Iterator[dict | None]:
    """One item per line: the row dict, or None for a line that is skipped."""
    lines = data.decode("latin-1").split("\n")
    if lines and lines[-1] == "":  # the newline that ends the file is not a line
        lines.pop()
    for linha, line in enumerate(lines, start=1):
        if line.endswith("\r"):
            line = line[:-1]
        parts = line.split("\t")
        if len(parts) != _FIELDS:
            yield None
            continue
        try:
            data_hora = datetime.strptime(parts[0], _TIMESTAMP)
        except ValueError:
            yield None
            continue
        mensagem = parts[4]
        tipo_evento, valor = _classify(mensagem)
        yield {
            "linha": linha,
            "data_hora": data_hora,
            "nivel": parts[1],
            "id_urna": parts[2],
            "componente": parts[3],
            "mensagem": mensagem,
            "autenticador": parts[5],
            "tipo_evento": tipo_evento,
            "valor": valor,
        }


def parse_logd(data: bytes) -> Iterator[dict]:
    """Yield one dict per valid line of logd.dat (latin-1). Invalid lines are skipped."""
    for row in _lines(data):
        if row is not None:
            yield row


def parse_logd_stats(data: bytes) -> tuple[list[dict], int]:
    """Return (rows, number of skipped lines)."""
    rows: list[dict] = []
    skipped = 0
    for row in _lines(data):
        if row is None:
            skipped += 1
        else:
            rows.append(row)
    return rows, skipped
