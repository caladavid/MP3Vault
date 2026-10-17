import http.server
import threading
from io import BytesIO

import pytest
from PIL import Image

from core import thumbnail


def _png(width, height):
    buf = BytesIO()
    Image.new("RGB", (width, height)).save(buf, "PNG")
    return buf.getvalue()


ROUTES = {
    "/ok": (lambda: _png(480, 360), "image/png"),
    "/bomb": (lambda: _png(5000, 5000), "image/png"),
    "/big": (lambda: b"\xff" * (thumbnail.THUMBNAIL_MAX_BYTES + 1), "image/jpeg"),
    "/html": (lambda: b"<html></html>", "text/html"),
}


@pytest.fixture(scope="module")
def server():
    bodies = {path: (make(), ctype) for path, (make, ctype) in ROUTES.items()}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body, ctype = bodies[self.path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_valid_thumbnail_is_resized(server):
    assert thumbnail.fetch_thumbnail(server + "/ok").size == thumbnail.THUMBNAIL_SIZE


@pytest.mark.parametrize("path, message", [
    ("/bomb", "dimensions"),
    ("/big", "too large"),
    ("/html", "not an image"),
])
def test_hostile_thumbnails_rejected(server, path, message):
    with pytest.raises(ValueError, match=message):
        thumbnail.fetch_thumbnail(server + path)
