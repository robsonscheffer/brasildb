"""Tests for cs.json parsing and sampling, on the real Roraima section list (no network)."""
from __future__ import annotations

import json
from pathlib import Path

from brasildb.tse.paths import SectionKey
from brasildb.tse.sections import SectionEntry, parse_cs, sample_sections

FIXTURE = Path(__file__).parent / "fixtures" / "cs_rr_3221.json"


def _rr() -> list[SectionEntry]:
    return parse_cs(json.loads(FIXTURE.read_text(encoding="utf-8")), "rr")


def test_parse_cs_counts_every_section():
    entries = _rr()
    assert len(entries) == 1627
    assert sum(1 for e in entries if e.principal is not None) == 108


def test_parse_cs_keys_are_padded_and_lower_case_uf():
    entries = _rr()
    assert all(e.key.sigla_uf == "rr" for e in entries)
    assert all(len(e.key.id_municipio_tse) == 5 for e in entries)
    assert all(len(e.key.zona) == 4 and len(e.key.secao) == 4 for e in entries)


def test_parse_cs_principal_and_aggregated():
    by_key = {e.key: e for e in _rr()}
    principal = by_key[SectionKey("rr", "03123", "0007", "0012")]
    assert principal.aggregated == ("0120",)
    assert principal.principal is None

    aggregated = by_key[SectionKey("rr", "03123", "0007", "0120")]
    assert aggregated.principal == "0012"
    assert aggregated.aggregated == ()


def test_sample_full_uf_keeps_every_entry():
    entries = _rr()
    out = sample_sections({"rr": entries}, fraction=0.0, seed=1, full_ufs={"rr"})
    assert out == sorted(entries, key=lambda e: e.key)


def test_sample_fraction_one_keeps_every_entry():
    entries = _rr()
    out = sample_sections({"rr": entries}, fraction=1.0, seed=1, full_ufs=set())
    assert len(out) == 1627


def test_sample_is_deterministic_for_a_seed():
    by_uf = {"rr": _rr()}
    first = sample_sections(by_uf, fraction=0.3, seed=42, full_ufs=set())
    second = sample_sections(by_uf, fraction=0.3, seed=42, full_ufs=set())
    other = sample_sections(by_uf, fraction=0.3, seed=7, full_ufs=set())
    assert first == second
    assert first != other


def test_sample_keeps_aggregated_entries_only_with_their_principal():
    entries = _rr()
    sample = sample_sections({"rr": entries}, fraction=0.3, seed=42, full_ufs=set())
    keys = {e.key for e in sample}

    principals_in = {
        (e.key.id_municipio_tse, e.key.zona, e.key.secao)
        for e in sample
        if e.principal is None
    }
    for e in entries:
        if e.principal is None:
            assert (e.key in keys) == ((e.key.id_municipio_tse, e.key.zona, e.key.secao) in principals_in)
        else:
            points_to_sampled = (e.key.id_municipio_tse, e.key.zona, e.principal) in principals_in
            assert (e.key in keys) == points_to_sampled


def test_sample_is_sorted_by_key():
    sample = sample_sections({"rr": _rr()}, fraction=0.3, seed=42, full_ufs=set())
    assert [e.key for e in sample] == sorted(e.key for e in sample)
