"""Section list from cs.json, and the sample drawn from it. Keys follow brasildb.tse.paths."""
from __future__ import annotations

import random
from dataclasses import dataclass

from brasildb.tse.paths import SectionKey


@dataclass(frozen=True)
class SectionEntry:
    """One section from cs.json. principal is set when this section is aggregated into another."""

    key: SectionKey
    principal: str | None  # secao of the section it was aggregated into (cs "nsp"), else None
    aggregated: tuple[str, ...]  # secoes aggregated into this one (cs "nsa"), else ()


def parse_cs(cs: dict, uf: str) -> list[SectionEntry]:
    """One entry per section in abr[].mu[].zon[].sec[]. Codes are zero-padded strings."""
    sigla = uf.lower()
    out: list[SectionEntry] = []
    for estado in cs["abr"]:
        for mun in estado["mu"]:
            id_mun = str(mun["cd"]).zfill(5)
            for zona in mun["zon"]:
                zon = str(zona["cd"]).zfill(4)
                for sec in zona["sec"]:
                    nsp = sec.get("nsp")
                    out.append(
                        SectionEntry(
                            key=SectionKey(sigla, id_mun, zon, str(sec["ns"]).zfill(4)),
                            principal=str(nsp).zfill(4) if nsp is not None else None,
                            aggregated=tuple(str(n).zfill(4) for n in sec.get("nsa", ())),
                        )
                    )
    return out


def sample_sections(
    by_uf: dict[str, list[SectionEntry]],
    fraction: float,
    seed: int,
    full_ufs: set[str],
) -> list[SectionEntry]:
    """Every entry of full_ufs. Elsewhere, a random fraction of principal sections, with the
    aggregated entries that point to them. Same seed gives the same sample; sorted by key."""
    out: list[SectionEntry] = []
    rng = random.Random(seed)
    for uf in sorted(by_uf):
        entries = by_uf[uf]
        if uf in full_ufs:
            out.extend(entries)
            continue
        principals = sorted(
            (e for e in entries if e.principal is None), key=lambda e: e.key
        )
        k = max(1, round(len(principals) * fraction)) if principals else 0
        chosen = {e.key for e in rng.sample(principals, k)}
        # An aggregated section stays in the sample when its principal does.
        chosen_by_principal = {(key.id_municipio_tse, key.zona, key.secao) for key in chosen}
        for e in entries:
            if e.principal is None:
                if e.key in chosen:
                    out.append(e)
            elif (e.key.id_municipio_tse, e.key.zona, e.principal) in chosen_by_principal:
                out.append(e)
    return sorted(out, key=lambda e: e.key)
