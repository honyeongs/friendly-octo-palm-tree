"""Serve the packaged browser-local comparison tool on loopback."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files


class LocalHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; "
                         "script-src 'self'; img-src 'self' data:; connect-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def guess_type(self, path):
        if path.endswith(".js"):
            return "text/javascript"
        if path.endswith(".svg"):
            return "image/svg+xml"
        return super().guess_type(path)


def serve(port: int = 8765):
    directory = str(files("netsec").joinpath("web"))
    handler = partial(LocalHandler, directory=directory)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Local: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
