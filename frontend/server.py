"""Static web server plus a restricted same-origin proxy to the AlgoProfitX API.

The browser only ever talks to this origin. Requests under ``/api/v1/`` are forwarded to one
fixed, HTTPS API origin that is validated against ``environments.json`` for the baked-in
``APP_ENV``. Nothing in a request can choose the upstream host, scheme, port or path prefix.
"""

import http.client
import json
import os
import re
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(os.environ.get("STATIC_ROOT", "/app/dist")).resolve()
ENVIRONMENTS = json.loads(
    (Path(__file__).resolve().parent / "environments.json").read_text(encoding="utf-8")
)

API_NAMESPACE = "/api"
API_PREFIX = "/api/v1"
MAX_PATH_BYTES = 2048
MAX_PROXY_BODY_BYTES = 8 * 1024 * 1024
MAX_TRAILER_BYTES = 8 * 1024
UPSTREAM_TIMEOUT_SECONDS = 30
PROXIED_METHODS = frozenset({"GET", "HEAD", "POST", "PATCH", "DELETE"})
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
DROPPED_RESPONSE_HEADERS = HOP_BY_HOP_HEADERS | {"server", "date"}
_ENCODED_PATH_TRICKS = re.compile(r"%(?:2e|2f|5c|00)", re.IGNORECASE)
_COOKIE_DOMAIN = re.compile(r";\s*domain=[^;]*", re.IGNORECASE)


def app_environment(app_env: str | None) -> str:
    """Return the validated environment name; there is no default."""
    if app_env not in ENVIRONMENTS:
        raise RuntimeError("APP_ENV must be one of: " + ", ".join(sorted(ENVIRONMENTS)))
    return app_env


def resolve_upstream_origin(app_env: str | None, configured: str | None) -> str:
    """The single API origin this process may proxy to.

    ``API_PUBLIC_ORIGIN`` may select among the origins approved for the environment, but it can
    never name anything else. With no value the environment's first approved origin is used.
    """
    allowed = ENVIRONMENTS[app_environment(app_env)]["allowedUpstreamApiOrigins"]
    origin = (configured or allowed[0]).rstrip("/")
    if origin not in allowed:
        raise RuntimeError(
            f"API_PUBLIC_ORIGIN is not an approved upstream for the {app_env} environment"
        )
    parts = urlsplit(origin)
    if parts.scheme != "https" or not parts.hostname or parts.path or parts.query or parts.fragment:
        raise RuntimeError("API_PUBLIC_ORIGIN must be a bare HTTPS origin")
    return origin


def content_security_policy(app_env: str | None) -> str:
    app_environment(app_env)
    return (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; "
        "manifest-src 'self'; upgrade-insecure-requests"
    )


def in_api_namespace(target: str) -> bool:
    """Whether a request target belongs to the proxied namespace (anything else is static)."""
    path = target.split("?", 1)[0]
    return path == API_NAMESPACE or path.startswith(API_NAMESPACE + "/")


def is_allowed_api_target(target: str) -> bool:
    """Whether a raw request target is a well-formed path under ``/api/v1/``."""
    if len(target.encode("utf-8", "replace")) > MAX_PATH_BYTES or not target.isascii():
        return False
    if any(ord(char) < 0x21 or ord(char) == 0x7F for char in target):
        return False
    path = target.split("?", 1)[0]
    if "#" in target or "\\" in target or _ENCODED_PATH_TRICKS.search(path):
        return False
    if path != API_PREFIX and not path.startswith(API_PREFIX + "/"):
        return False
    segments = path.split("/")[1:]
    if any(segment in {"", ".", ".."} for segment in segments[:-1]) or segments[-1] in {".", ".."}:
        return False
    return "//" not in path


def rewrite_set_cookie(value: str) -> str:
    """Cookies set through the proxy stay host-only for this origin (never domain-wide)."""
    return _COOKIE_DOMAIN.sub("", value)


APP_ENV = os.environ.get("APP_ENV")
CSP = content_security_policy(APP_ENV)
UPSTREAM_ORIGIN = resolve_upstream_origin(APP_ENV, os.environ.get("API_PUBLIC_ORIGIN"))
UPSTREAM = urlsplit(UPSTREAM_ORIGIN)


def open_upstream_connection() -> http.client.HTTPConnection:
    return http.client.HTTPSConnection(
        UPSTREAM.hostname, UPSTREAM.port or 443, timeout=UPSTREAM_TIMEOUT_SECONDS
    )


class SpaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
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
        if self.command not in PROXIED_METHODS:
            self.send_error(405, "Method not allowed")
            return
        if not is_allowed_api_target(self.path):
            self.send_error(400, "Invalid API path")
            return
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

        upstream_path = f"{UPSTREAM.path.rstrip('/')}{self.path}"
        connection = open_upstream_connection()
        try:
            connection.request(self.command, upstream_path, body=body, headers=request_headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                lowered = name.lower()
                if lowered in DROPPED_RESPONSE_HEADERS:
                    continue
                self.send_header(
                    name, rewrite_set_cookie(value) if lowered == "set-cookie" else value
                )
            self.end_headers()
            if self.command != "HEAD":
                while chunk := response.read(64 * 1024):
                    self.wfile.write(chunk)
        except (socket.timeout, TimeoutError):
            self.send_error(504, "API upstream timed out")
        except (OSError, ValueError, http.client.HTTPException):
            self.send_error(502, "API upstream unavailable")
        finally:
            connection.close()

    def do_GET(self) -> None:
        if in_api_namespace(self.path):
            self._proxy_api_request()
        else:
            super().do_GET()

    def do_HEAD(self) -> None:
        if in_api_namespace(self.path):
            self._proxy_api_request()
        else:
            super().do_HEAD()

    def _api_only(self) -> None:
        if in_api_namespace(self.path):
            self._proxy_api_request()
        else:
            self.send_error(405, "Method not allowed")

    do_POST = _api_only
    do_PATCH = _api_only
    do_DELETE = _api_only

    def do_PUT(self) -> None:
        self.send_error(405, "Method not allowed")

    def do_OPTIONS(self) -> None:
        self.send_error(405, "Method not allowed")


if __name__ == "__main__":
    port = int(
        os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT")
        or os.environ.get("PORT")
        or "8000"
    )
    ThreadingHTTPServer(("0.0.0.0", port), SpaHandler).serve_forever()
