"""Build the replay map's data files (P2 T3/T4) from votos_minuto and a towns table.

Inputs:
  --votos    Parquet of main.votos_minuto for one round
             (brasildb sql "copy (select * from main.votos_minuto where turno=2) to 'vm.parquet'")
  --towns    CSV with id_municipio_tse, id_municipio, nome, sigla_uf, lat, lon, aptos, secoes
  --borders  IBGE GeoJSON of the state borders (api/v3/malhas/paises/BR, intrarregiao=UF)
  --out      directory, gets towns.json, frames.png, totals.json, borders.json

frames.png is a grayscale image: one column per town (towns.json order), one row per minute
from 08:00 Brasilia. A pixel is how busy the town's urnas were that minute: 255 = 1.5 votes per
section per minute or more. A PNG costs a quarter of the raw bytes and the browser decodes it.
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

import duckdb

START = 8 * 60  # 08:00 Brasilia
END = 18 * 60 + 30  # 18:30, inclusive
FULL = 1.5  # votes per section per minute that count as fully lit


def png_gray(width: int, height: int, pixels: bytes) -> bytes:
    raw = b"".join(b"\x00" + pixels[y * width:(y + 1) * width] for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--votos", required=True)
    ap.add_argument("--towns", required=True)
    ap.add_argument("--borders", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    towns = con.execute(f"""
        select sigla_uf, id_municipio_tse, nome, round(lat, 3), round(lon, 3), aptos, secoes
        from read_csv('{a.towns}', header=true)
        where lat is not null and aptos > 0
        order by aptos desc, sigla_uf, id_municipio_tse
    """).fetchall()
    index = {(uf, mun): i for i, (uf, mun, *_) in enumerate(towns)}
    n = len(towns)
    minutes = END - START + 1

    pixels = bytearray(n * minutes)
    national = [0] * minutes
    by_uf: dict[str, list[int]] = {}
    for uf, mun, minuto, votos in con.execute(f"""
        select sigla_uf, id_municipio_tse,
               extract(hour from minuto_bsb) * 60 + extract(minute from minuto_bsb), votos
        from '{a.votos}'
    """).fetchall():
        m = int(minuto) - START
        if not 0 <= m < minutes or (uf, mun) not in index:
            continue
        i = index[(uf, mun)]
        secoes = towns[i][6] or 1
        pixels[m * n + i] = min(255, round(255 * votos / (secoes * FULL)))
        national[m] += votos
        by_uf.setdefault(uf, [0] * minutes)[m] += votos

    (out / "frames.png").write_bytes(png_gray(n, minutes, bytes(pixels)))
    (out / "towns.json").write_text(json.dumps({
        "uf": [t[0] for t in towns],
        "id": [t[1] for t in towns],
        "nome": [t[2] for t in towns],
        "lat": [t[3] for t in towns],
        "lon": [t[4] for t in towns],
        "aptos": [t[5] for t in towns],
        "secoes": [t[6] for t in towns],
    }, ensure_ascii=False, separators=(",", ":")))
    (out / "totals.json").write_text(json.dumps({
        "start": START, "minutes": minutes, "full": FULL,
        "aptos": sum(t[5] for t in towns),
        "national": national,
        "uf": dict(sorted(by_uf.items())),
    }, separators=(",", ":")))

    geo = json.loads(Path(a.borders).read_text())
    borders = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "Polygon" else [p for mp in g["coordinates"] for p in mp]
        for ring in polys:
            borders.append([[round(x, 2), round(y, 2)] for x, y in ring])
    (out / "borders.json").write_text(json.dumps(borders, separators=(",", ":")))

    sizes = {p.name: p.stat().st_size for p in out.iterdir()}
    print(f"{n} towns, {minutes} minutes, {sum(national):,} votes; files: {sizes}")


if __name__ == "__main__":
    main()
