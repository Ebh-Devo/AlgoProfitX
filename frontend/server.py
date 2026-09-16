import os
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(os.environ.get("STATIC_ROOT", "/app/dist")).resolve()
API_ORIGIN = os.environ.get("API_PUBLIC_ORIGIN", "https://api.algoprofitx.com").rstrip("/")
API_TARGET = urlsplit(API_ORIGIN)
MAX_PROXY_BODY_BYTES = 8 * 1024 * 1024
MAX_TRAILER_BYTES = 8 * 1024
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
FORWARDED_REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "cookie",
    "user-agent",
    "x-csrf-token",
    "x-request-id",
}

if API_TARGET.scheme != "https" or not API_TARGET.hostname or API_TARGET.query or API_TARGET.fragment:
    raise RuntimeError("API_PUBLIC_ORIGIN must be an HTTPS origin")


class SpaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; font-src 'self'; "
            f"img-src 'self' data:; connect-src 'self' {API_ORIGIN}; "
            "manifest-src 'self'; upgrade-insecure-requests",
        )
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def send_head(self):
        requested = urlsplit(self.path).path
        candidate = ROOT / requested.lstrip("/")
        if requested != "/" and not candidate.exists() and "." not in candidate.name:
            self.path = "/index.html"
        return super().send_head()

    def _is_api_request(self) -> bool:
        return urlsplit(self.path).path.startswith("/api/")

    def _read_chunked_body(self) -> tuple[bool, bytes | None]:
        body = bytearray()
        while True:
            size_line = self.rfile.readline(128)
            if not size_line or not size_line.endswith(b"\r\n"):
                self.send_error(400, "Invalid chunked request body")
                return False, None
            try:
                size = int(size_line[:-2].split(b";", 1)[0].strip(), 16)
            except ValueError:
                self.send_error(400, "Invalid chunked request body")
                return False, None
            if size < 0 or len(body) + size > MAX_PROXY_BODY_BYTES:
                self.send_error(413, "Request body too large")
                return False, None
            if size == 0:
                trailer_bytes = 0
                while True:
                    trailer = self.rfile.readline(MAX_TRAILER_BYTES + 1)
                    trailer_bytes += len(trailer)
                    if not trailer or trailer_bytes > MAX_TRAILER_BYTES:
                        self.send_error(400, "Invalid chunked request body")
                        return False, None
                    if trailer == b"\r\n":
                        return True, bytes(body)
            chunk = self.rfile.read(size)
            if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                self.send_error(400, "Invalid chunked request body")
                return False, None
            body.extend(chunk)

    def _read_request_body(self) -> tuple[bool, bytes | None]:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower().strip()
        if transfer_encoding:
            if transfer_encoding != "chunked":
                self.send_error(400, "Unsupported Transfer-Encoding")
                return False, None
            return self._read_chunked_body()
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return False, None
        if content_length < 0 or content_length > MAX_PROXY_BODY_BYTES:
            self.send_error(413, "Request body too large")
            return False, None
        if not content_length:
            return True, None
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self.send_error(400, "Incomplete request body")
            return False, None
        return True, body

    def _proxy_api_request(self) -> None:
        body_ok, body = self._read_request_body()
        if not body_ok:
            return

        request_headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() in FORWARDED_REQUEST_HEADERS
        }
        if body is not None:
            request_headers["Content-Length"] = str(len(body))

        upstream_path = f"{API_TARGET.path.rstrip('/')}{self.path}"
        connection = http.client.HTTPSConnection(
            API_TARGET.hostname,
            API_TARGET.port or 443,
            timeout=30,
        )
        try:
            connection.request(self.command, upstream_path, body=body, headers=request_headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                lowered = name.lower()
                if lowered not in HOP_BY_HOP_HEADERS and lowered not in {"server", "date"}:
                    self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                while chunk := response.read(64 * 1024):
                    self.wfile.write(chunk)
        except (OSError, ValueError, http.client.HTTPException):
            self.send_error(502, "API upstream unavailable")
        finally:
            connection.close()

    def do_GET(self) -> None:
        if self._is_api_request():
            self._proxy_api_request()
        else:
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._is_api_request():
            self._proxy_api_request()
        else:
            super().do_HEAD()

    def do_POST(self) -> None:
        self._proxy_api_request() if self._is_api_request() else self.send_error(405)

    def do_PUT(self) -> None:
        self._proxy_api_request() if self._is_api_request() else self.send_error(405)

    def do_PATCH(self) -> None:
        self._proxy_api_request() if self._is_api_request() else self.send_error(405)

    def do_DELETE(self) -> None:
        self._proxy_api_request() if self._is_api_request() else self.send_error(405)

    def do_OPTIONS(self) -> None:
        self._proxy_api_request() if self._is_api_request() else self.send_error(405)


if __name__ == "__main__":
    port = int(
        os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT")
        or os.environ.get("PORT")
        or "8000"
    )
    ThreadingHTTPServer(("0.0.0.0", port), SpaHandler).serve_forever()
