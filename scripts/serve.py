#!/usr/bin/env python3
"""Preview site/ locally the way GitHub Pages serves it.

    python scripts/serve.py          # http://localhost:8000
    python scripts/serve.py 8080

The site's links have no .html on them (/career, /round?s=...), because
GitHub Pages serves /career from career.html. Python's plain
`http.server` doesn't, so every internal link would 404 locally; this one
tries the .html file when the clean path doesn't exist. Stdlib only.
"""
import http.server
import os
import sys
from functools import partial
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        full = super().translate_path(path)
        if not os.path.exists(full) and os.path.exists(full + ".html"):
            return full + ".html"
        return full


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(CleanUrlHandler, directory=str(SITE)))
    print(f"Serving {SITE} at http://localhost:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
