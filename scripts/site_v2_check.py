"""Every number the v2 walk shows has a source in its data files (P4 W6).

  python3 scripts/site_v2_check.py             # docs/site/v2: prints each number without a source, exits 1

A source is a fact in curiosidades.json that carries its SQL: its valor, its hora, and the
numbers of its titulo and texto (the data script builds those from the query). Checked:
- the page's visible text and its content, aria-label, title and alt attributes, outside
  <script> and <style>: numbers of 4 or more digits (128.236.074) and times (08:00:19, 19h06);
- numbers of 4 or more digits in the page's script strings ("128.236.074") and number
  literals of 6 or more digits (127854844);
- every fact whose texto has a number carries its sql.
A mock file is a source too, so the check runs on the mock as well.
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "docs/site/v2"
NUM = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{3})+(?![\d.])|(?<![\d.:])\d{4,}(?![\d.:])")
HORA = re.compile(r"\b(\d{2})(?::|h)(\d{2})(?::(\d{2}))?\b")
LITERAL = re.compile(r"(?<![\w.])\d{6,}(?![\w.])")
SEM_FONTE = {"2026", "2147483647"}  # the election year; the card's random generator (2^31 - 1)
STRING = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'|`[^`]*`")


def numeros(texto: str) -> set[str]:
    return {m.replace(".", "") for m in NUM.findall(texto)} - SEM_FONTE


def horas(texto: str) -> set[str]:
    """Times as HH:MM, so 19h06 and 19:06:21 both give 19:06."""
    return {f"{h}:{m}" for h, m, _ in HORA.findall(texto)}


class Texto(HTMLParser):
    """The text a reader sees or hears, without scripts and styles; scripts kept apart."""

    ATTRS = {"content", "aria-label", "title", "alt"}

    def __init__(self) -> None:
        super().__init__()
        self.visivel: list[str] = []
        self.scripts: list[str] = []
        self.dentro: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.dentro = tag
        self.visivel += [v for k, v in attrs if k in self.ATTRS and v]

    def handle_endtag(self, tag):
        if tag == self.dentro:
            self.dentro = None

    def handle_data(self, data):
        if self.dentro == "script":
            self.scripts.append(data)
        elif self.dentro is None:
            self.visivel.append(data)


def fontes(cur: dict) -> tuple[set[str], set[str], list[str]]:
    nums, hs, sem_sql = set(), set(), []
    for i in cur["itens"]:
        texto = f"{i.get('titulo') or ''} {i.get('texto') or ''}"
        if not i.get("sql") and not cur.get("mock") and (numeros(texto) or horas(texto)):
            sem_sql.append(i["id"])
            continue
        nums |= numeros(texto)
        hs |= horas(texto)
        if isinstance(i.get("valor"), (int, float)):
            nums.add(str(round(i["valor"])))
        if i.get("hora"):
            hs |= horas(i["hora"])
    return nums, hs, sem_sql


def check(site: Path = SITE) -> list[str]:
    cur = json.loads((site / "data/curiosidades.json").read_text())
    nums, hs, sem_sql = fontes(cur)
    p = Texto()
    p.feed((site / "index.html").read_text())
    visivel, scripts = " ".join(p.visivel), " ".join(p.scripts)
    falta = [f"fato sem sql: {i}" for i in sem_sql]
    falta += [f"texto: {n}" for n in sorted(numeros(visivel) - nums)]
    falta += [f"texto: {h}" for h in sorted(horas(visivel) - hs)]
    falta += [f"script: {n}" for n in sorted(numeros(re.sub(r"\$\{[^}]*\}", " ", " ".join(STRING.findall(scripts)))) - nums)]
    falta += [f"script: {n}" for n in sorted(set(LITERAL.findall(scripts)) - nums - SEM_FONTE)]
    return falta


def main() -> int:
    falta = check()
    for f in falta:
        print(f)
    return 1 if falta else 0


if __name__ == "__main__":
    sys.exit(main())
