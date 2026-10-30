from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("site_v2_check", ROOT / "scripts/site_v2_check.py")
site_v2_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_v2_check)


def _site(tmp_path: Path, html: str) -> Path:
    (tmp_path / "data").mkdir()
    fato = {"id": "total", "titulo": "128.236.074 votos", "texto": "Em São Paulo, às 19h06.",
            "hora": "19:06:21", "valor": 128236074, "sql": "SELECT 1"}
    (tmp_path / "data/curiosidades.json").write_text(json.dumps({"mock": False, "itens": [fato]}))
    (tmp_path / "index.html").write_text(html)
    return tmp_path


def test_the_published_page_has_a_source_for_every_number():
    assert site_v2_check.check() == []


def test_a_typed_number_without_a_source_is_reported(tmp_path):
    html = ('<meta name="description" content="128.236.074 votos, o último às 19h06.">'
            "<p>127.854.844 votos às 18:30.</p><script>const V = 127854844; const t = `${x[1019]} votos`;</script>")
    assert site_v2_check.check(_site(tmp_path, html)) == ["texto: 127854844", "texto: 18:30", "script: 127854844"]
