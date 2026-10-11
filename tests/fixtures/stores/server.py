"""
server.py - Serve the static fixture stores on 127.0.0.1.

Each store directory holds the pages of one fake shop plus a fixtures.json
with its ground truth. StoreServer serves one store from a background thread
(stdlib http.server only), records every request it answers, and never serves
fixtures.json.

Routing for a normal store:
    /                 -> index.html
    /a/b  or /a/b/    -> a/b.html, else a/b/index.html
    /robots.txt etc.  -> the file itself (.txt / .xml / .json other than fixtures.json)
    anything else     -> 404

The "blocked" store answers every path, robots.txt included, with 403 and a
Cloudflare-style challenge body.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlsplit

STORES_DIR = Path(__file__).resolve().parent
STORE_NAMES = ("shopify_basic", "woocommerce_promo", "blocked")

NOT_FOUND_BODY = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>404 Not Found</title></head><body><main><h1>404 Page Not Found</h1>"
    "<p>The page you were looking for does not exist.</p></main></body></html>"
)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
}


def load_ground_truth(store: str) -> Dict:
    """Return the parsed fixtures.json for a store."""
    with open(STORES_DIR / store / "fixtures.json", encoding="utf-8") as f:
        return json.load(f)


class StoreServer:
    """One fixture store served on 127.0.0.1 from a daemon thread."""

    def __init__(self, store: str, host: str = "127.0.0.1", port: int = 0):
        if store not in STORE_NAMES:
            raise ValueError(f"unknown fixture store: {store}")
        self.store = store
        self.root = STORES_DIR / store
        self.truth = load_ground_truth(store)
        self.extra_headers: Dict[str, str] = self.truth.get("response_headers", {})
        self.requests: List[Dict] = []
        self._lock = threading.Lock()
        self._httpd = ThreadingHTTPServer((host, port), self._make_handler())
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "StoreServer":
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name=f"fixture-{self.store}", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "StoreServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def request_log(self) -> List[Dict]:
        with self._lock:
            return list(self.requests)

    def _record(self, method: str, path: str, status: int, user_agent: str) -> None:
        with self._lock:
            self.requests.append({
                "ts": time.time(), "method": method, "path": path,
                "status": status, "user_agent": user_agent,
            })

    def resolve(self, raw_path: str) -> Optional[Path]:
        """Map a request path to a file in the store, or None for 404."""
        path = unquote(urlsplit(raw_path).path)
        rel = path.strip("/")
        if not rel:
            candidates = [self.root / "index.html"]
        else:
            candidates = [self.root / f"{rel}.html", self.root / rel / "index.html"]
            if Path(rel).suffix in (".txt", ".xml", ".json") and Path(rel).name != "fixtures.json":
                candidates.append(self.root / rel)
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_file() and self.root in resolved.parents:
                return resolved
        return None

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "fixture"
            sys_version = ""

            def log_message(self, *args) -> None:
                pass

            def version_string(self) -> str:
                return server.extra_headers.get("Server", "fixture")

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for key, value in server.extra_headers.items():
                    if key.lower() not in ("content-type", "server"):
                        self.send_header(key, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                server._record(self.command, self.path, status, self.headers.get("User-Agent", ""))

            def _answer(self) -> None:
                if server.store == "blocked":
                    host = self.headers.get("Host", "127.0.0.1")
                    body = (server.root / "challenge.html").read_text(encoding="utf-8")
                    self._send(403, body.replace("__HOST__", host).encode("utf-8"),
                               "text/html; charset=UTF-8")
                    return
                target = server.resolve(self.path)
                if target is None:
                    self._send(404, NOT_FOUND_BODY.encode("utf-8"), CONTENT_TYPES[".html"])
                    return
                self._send(200, target.read_bytes(),
                           CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

            def do_GET(self) -> None:
                self._answer()

            def do_HEAD(self) -> None:
                self._answer()

        return Handler


def start_all(stores=STORE_NAMES) -> Dict[str, StoreServer]:
    """Start one server per store; caller must stop() each."""
    return {name: StoreServer(name).start() for name in stores}


if __name__ == "__main__":
    servers = start_all()
    for name, srv in servers.items():
        print(f"{name}: {srv.base_url}")
    print("Ctrl+C to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        for srv in servers.values():
            srv.stop()
