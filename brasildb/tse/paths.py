"""Section keys and results-site URLs. Shared by every TSE module; keep it small."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class SectionKey:
    """One polling section. All codes are zero-padded strings, as on the results site."""

    sigla_uf: str  # lower case, e.g. "rr"
    id_municipio_tse: str  # 5 digits, e.g. "03085"
    zona: str  # 4 digits, e.g. "0008"
    secao: str  # 4 digits, e.g. "0001"


def cs_url(base: str, uf: str, id_pleito: str) -> str:
    """Section list for one state: {base}/{pleito}/config/{uf}/{uf}-p00{pleito}-cs.json"""
    return f"{base}/{id_pleito}/config/{uf}/{uf}-p{int(id_pleito):06d}-cs.json"


def _section_dir(base: str, id_pleito: str, k: SectionKey) -> str:
    return f"{base}/{id_pleito}/dados/{k.sigla_uf}/{k.id_municipio_tse}/{k.zona}/{k.secao}"


def aux_url(base: str, id_pleito: str, k: SectionKey) -> str:
    """Index of one section's files (hashes[].arq[] with nm and tp)."""
    p = f"p{int(id_pleito):06d}"
    return (f"{_section_dir(base, id_pleito, k)}/"
            f"{p}-{k.sigla_uf}-m{k.id_municipio_tse}-z{k.zona}-s{k.secao}-aux.json")


def file_url(base: str, id_pleito: str, k: SectionKey, hash_: str, name: str) -> str:
    """A file listed in aux.json, e.g. o03221rr0308500080001-log.jez."""
    return f"{_section_dir(base, id_pleito, k)}/{hash_}/{name}"
