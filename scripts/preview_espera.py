"""Private, loopback-only preview. Media stays outside Git and is never downloaded."""
import argparse
import json
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[1] / "docs/site/espera-prototype"
MEDIA = {
    "/private-media/niteroi.jpg": "curadoria-primeira/niteroi-felipe-publicada.jpg",
    "/private-media/bh.jpg": "curadoria-primeira/bh-publicada.jpg",
    "/private-media/pt.jpg": "curadoria-segunda/pt-reel-poster.jpg",
}

def percent(value):
    return f"{value:.2f}".replace(".", ",")

def render():
    content = json.loads((SITE / "content.json").read_text())
    values = {}
    sources = []
    for scene in content["scenes"]:
        for key, value in scene.items():
            if isinstance(value, str):
                values[f'{scene["id"]}_{key}'] = escape(value, quote=True)
        sources.append(
            f'<li><a href="{escape(scene["source"], quote=True)}">'
            f'{escape(scene["title"])}</a><span>{escape(scene["time"])}'
            f' · {escape(scene.get("credit", "InfoMoney · parciais jornalísticas"))}</span></li>'
        )
    records = next(s["partials"] for s in content["scenes"] if s["id"] == "apuracao")
    cards = []
    for index, item in enumerate(records, 1):
        rows = []
        for key, name in (("lula", "Lula"), ("flavio", "Flávio Bolsonaro")):
            css = " opponent" if key == "flavio" else ""
            rows.append(
                f'<div class="candidate-line {key}"><span>{name}</span>'
                f'<b>{percent(item[key])}<small>%</small></b></div>'
                f'<div class="bar{css}" aria-hidden="true">'
                f'<span style="width: {item[key]}%"></span></div>'
            )
        cards.append(
            f'<article class="count-beat {escape(item["tone"])}" id="parcial-{index}" '
            f'aria-labelledby="beat-title-{index}"><div class="beat-frame">'
            f'<div class="beat-top"><span>DOMINGO, 25 OUTUBRO</span>'
            f'<time>{item["time"]}</time><span>0{index} / 04</span></div>'
            f'<div class="beat-body"><div class="beat-story">'
            f'<h3 id="beat-title-{index}">{escape(item["heading"])}<br>'
            f'<em>{escape(item["turn"])}</em></h3>'
            f'<p>{escape(item["line"])}</p></div>'
            f'<div class="beat-score"><p class="score-label">PRESIDENTE · VOTOS VÁLIDOS</p>'
            + "".join(rows)
            + f'<p class="coverage"><b>{percent(item["counted"])}%</b> das urnas apuradas</p>'
            f'</div></div><div class="beat-bottom"><p>{escape(item["coda"])}</p>'
            f'<a href="#' + (f'parcial-{index + 1}' if index < 3 else 'confirmacao')
            + '">Continuar ↓</a></div>'
            f'<details class="beat-source"><summary>InfoMoney · {item["time"]} · fonte e contexto</summary>'
            '<p>Horário da atualização jornalística, em Brasília. Recorte documental, não contagem ao vivo. '
            'Os intervalos não são interpolados. As frases de espera são voz editorial, não medição de sentimentos.</p>'
            f'<a href="{values["apuracao_source"]}">Consultar o liveblog ↗</a></details>'
            '</div></article>'
        )
    values["partials"] = "".join(cards)
    for key, value in content["confirmation"].items():
        values[f"confirmation_{key}"] = escape(value, quote=True)
    sources.append(f'<li><a href="{values["confirmation_source"]}">Confirmação matemática · relato da Exame</a>'
                   f'<span>{values["confirmation_limit"]}</span></li>')
    result = content["result"]
    values["result_source"] = escape(result["source"], quote=True)
    values["result_scope"] = escape(result["scope"])
    for candidate in ("lula", "flavio"):
        values[f"{candidate}_percent"] = percent(result[candidate]["percent"])
        values[f"{candidate}_width"] = str(result[candidate]["percent"])
        values[f"{candidate}_votes"] = escape(result[candidate]["votes"])
    sources.append(f'<li><a href="{values["result_source"]}">Resultado final nacional · TSE</a></li>')
    values["sources"] = "<ol class=\"sources-list\">" + "".join(sources) + "</ol>"
    return Template((SITE / "index.html").read_text()).substitute(values).encode()

class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, media_root, **kwargs):
        self.media_root = media_root
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.respond()

    def do_HEAD(self):
        self.respond(head=True)

    def respond(self, head=False):
        # Exact allowlist: no directory listing or access to research source files.
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path in ("/", "/espera-prototype"):
            self.send_response(302)
            self.send_header("Location", "/espera-prototype/")
            self.end_headers()
            return
        if path == "/espera-prototype/":
            body, mime = render(), "text/html; charset=utf-8"
        elif path in ("/espera-prototype/style.css", "/espera-prototype/counting.css", "/espera-prototype/script.js"):
            name = path.rsplit("/", 1)[-1]
            body = (SITE / name).read_bytes()
            mime = "text/css" if name.endswith(".css") else "text/javascript"
        elif path in MEDIA:
            file = self.media_root / MEDIA[path]
            if not file.is_file():
                self.send_error(404, "Private research image not provided")
                return
            body, mime = file.read_bytes(), "image/jpeg"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        if not head:
            self.wfile.write(body)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", required=True, type=Path,
                        help="Private research folder containing the two curadoria subfolders")
    parser.add_argument("--port", type=int, default=52018)
    args = parser.parse_args()
    missing = [name for name in MEDIA.values() if not (args.media_root / name).is_file()]
    if missing:
        parser.error("Missing private media: " + ", ".join(missing))
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                partial(Handler, media_root=args.media_root.resolve()))
    print(f"Private preview: http://127.0.0.1:{args.port}/espera-prototype/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
