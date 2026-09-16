import os
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(os.environ.get("STATIC_ROOT", "/app/dist")).resolve()
API_ORIGIN = os.environ.get("API_PUBLIC_ORIGIN", "https://api.algoprofitx.com").rstrip("/")
API_TARGET = urlsplit(API_ORIGIN)
MAX_PROXY_BODY_BYTES = 8 * 1024 * 1024
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

    def _proxy_api_request(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if content_length > MAX_PROXY_BODY_BYTES:
            self.send_error(413, "Request body too large")
            return

        body = self.rfile.read(content_length) if content_length else None
        request_headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() in FORWARDED_REQUEST_HEADERS
        }
        if content_length:
            request_headers["Content-Length"] = str(content_length)

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
