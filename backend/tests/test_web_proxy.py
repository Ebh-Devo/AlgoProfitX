"""Behavior of the same-origin web proxy (frontend/server.py) against a fake local upstream."""

import http.client
import importlib.util
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = REPO_ROOT / "frontend" / "server.py"


def load_server(monkeypatch, app_env="development", api_origin=None, static_root=None):
    if app_env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", app_env)
    if api_origin is None:
        monkeypatch.delenv("API_PUBLIC_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("API_PUBLIC_ORIGIN", api_origin)
    if static_root is not None:
        monkeypatch.setenv("STATIC_ROOT", str(static_root))
    spec = importlib.util.spec_from_file_location("frontend_server_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeUpstream:
    def __init__(self):
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                if self.path.startswith("/api/v1/slow"):
                    outer.release.wait(timeout=2)
                status = {"/api/v1/gone": 410, "/api/v1/conflict": 409, "/api/v1/none": 204}.get(
                    self.path.split("?")[0], 200
                )
                payload = b"" if status == 204 else b'{"ok":true}'
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "algoprofitx_csrf=abc; Domain=catalystappsail.in; Path=/; Secure")
                self.send_header(
                    "Set-Cookie",
                    "algoprofitx_refresh=r; Path=/api/v1/auth; HttpOnly; Secure; SameSite=Strict",
                )
                self.send_header("Keep-Alive", "timeout=5")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = False  # server_close() then joins in-flight handlers
        self.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stack(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "app.js").write_text("console.log(1)")
    server = load_server(monkeypatch, static_root=tmp_path)
    upstream = FakeUpstream()
    monkeypatch.setattr(
        server,
        "open_upstream_connection",
        lambda: http.client.HTTPConnection("127.0.0.1", upstream.port, timeout=server.UPSTREAM_TIMEOUT_SECONDS),
    )
    monkeypatch.setattr(server.SpaHandler, "log_message", lambda *args, **kwargs: None)
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), server.SpaHandler)
    proxy.daemon_threads = False
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    yield server, upstream, proxy.server_address[1]
    upstream.release.set()
    proxy.shutdown()
    proxy.server_close()
    upstream.close()
    thread.join(timeout=5)
    upstream.thread.join(timeout=5)


def request(port, method, target, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, target, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    result = (response.status, dict(response.getheaders()), data, response.msg.get_all("Set-Cookie") or [])
    connection.close()
    return result


def raw(port, payload: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := sock.recv(4096):
            chunks.append(chunk)
    return b"".join(chunks)


def test_forwards_allowed_headers_and_preserves_status_and_body(stack):
    server, upstream, port = stack
    status, headers, data, _ = request(
        port,
        "POST",
        "/api/v1/conflict?x=1",
        {
            "Authorization": "Bearer t",
            "Cookie": "algoprofitx_csrf=c; algoprofitx_refresh=r",
            "X-CSRF-Token": "c",
            "Content-Type": "application/json",
            "X-Evil": "1",
            "X-Forwarded-Host": "evil.example",
            "Host": "attacker.example",
        },
        b'{"a":1}',
    )
    assert (status, data) == (409, b'{"ok":true}')
    seen = upstream.requests[-1]
    assert seen["method"] == "POST" and seen["path"] == "/api/v1/conflict?x=1"
    assert seen["body"] == b'{"a":1}'
    assert seen["headers"]["authorization"] == "Bearer t"
    assert seen["headers"]["x-csrf-token"] == "c"
    assert "algoprofitx_refresh=r" in seen["headers"]["cookie"]
    assert "x-evil" not in seen["headers"] and "x-forwarded-host" not in seen["headers"]
    assert seen["headers"]["host"].startswith("127.0.0.1")  # never the client-supplied Host


@pytest.mark.parametrize("method", ["GET", "HEAD", "PATCH", "DELETE"])
def test_other_allowed_methods_are_forwarded(stack, method):
    _, upstream, port = stack
    status, *_ = request(port, method, "/api/v1/health")
    assert status == 200
    assert upstream.requests[-1]["method"] == method


def test_no_content_status_is_preserved(stack):
    _, _, port = stack
    status, _, data, _ = request(port, "GET", "/api/v1/none")
    assert (status, data) == (204, b"")


def test_chunked_request_bodies_are_reassembled(stack):
    _, upstream, port = stack
    payload = (
        b"POST /api/v1/x HTTP/1.1\r\nHost: web\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\nConnection: close\r\n\r\n"
        b"4\r\n{\"a\"\r\n4\r\n:1}\n\r\n0\r\n\r\n"
    )
    response = raw(port, payload)
    assert response.startswith(b"HTTP/1.0 200") or response.startswith(b"HTTP/1.1 200")
    assert upstream.requests[-1]["body"] == b'{"a":1}\n'
    assert "transfer-encoding" not in upstream.requests[-1]["headers"]


def test_set_cookie_is_host_only_and_all_cookies_survive(stack):
    _, _, port = stack
    _, headers, _, cookies = request(port, "GET", "/api/v1/auth/session")
    assert len(cookies) == 2
    assert not any("domain=" in cookie.lower() for cookie in cookies)
    csrf = next(cookie for cookie in cookies if cookie.startswith("algoprofitx_csrf"))
    assert "Secure" in csrf and "Path=/" in csrf
    refresh = next(cookie for cookie in cookies if cookie.startswith("algoprofitx_refresh"))
    assert "HttpOnly" in refresh and "SameSite=Strict" in refresh and "Path=/api/v1/auth" in refresh


def test_hop_by_hop_response_headers_are_not_forwarded(stack):
    _, _, port = stack
    _, headers, _, _ = request(port, "GET", "/api/v1/health")
    lowered = {name.lower() for name in headers}
    assert "keep-alive" not in lowered


@pytest.mark.parametrize(
    "target",
    [
        "/api/v2/x",
        "/api/internal",
        "/api",
        "/api/",
        "/api/v1/../health",
        "/api/v1/./x",
        "/api/v1//x",
        "/api/v1/%2e%2e/health",
        "/api/v1/%2E%2E/health",
        "/api/v1/a%2fb",
        "/api/v1/a%5cb",
        "/api/v1/a%00b",
        "/api/v1/a\\b",
        "/api/v1/" + "a" * 3000,
    ],
)
def test_requests_outside_the_api_prefix_or_with_tricks_never_reach_upstream(stack, target):
    _, upstream, port = stack
    before = len(upstream.requests)
    response = raw(port, f"GET {target} HTTP/1.1\r\nHost: web\r\nConnection: close\r\n\r\n".encode())
    assert response.split(b" ", 2)[1] == b"400"
    assert len(upstream.requests) == before


def test_absolute_form_and_authority_targets_are_not_open_proxying(stack):
    _, upstream, port = stack
    for line in (
        b"GET http://evil.example/api/v1/x HTTP/1.1",
        b"GET https://evil.example/api/v1/x HTTP/1.1",
        b"CONNECT evil.example:443 HTTP/1.1",
    ):
        raw(port, line + b"\r\nHost: web\r\nConnection: close\r\n\r\n")
    assert upstream.requests == []


@pytest.mark.parametrize("method", ["PUT", "OPTIONS", "TRACE"])
def test_unsupported_methods_are_rejected_without_forwarding(stack, method):
    _, upstream, port = stack
    status, *_ = request(port, method, "/api/v1/x")
    assert status in (405, 501)
    assert upstream.requests == []


def test_non_api_posts_are_rejected(stack):
    _, upstream, port = stack
    status, *_ = request(port, "POST", "/login", body=b"x")
    assert status == 405 and upstream.requests == []


def test_oversized_declared_body_is_refused_before_forwarding(stack):
    server, upstream, port = stack
    response = raw(
        port,
        (
            f"POST /api/v1/x HTTP/1.1\r\nHost: web\r\nContent-Length: {server.MAX_PROXY_BODY_BYTES + 1}\r\n"
            "Connection: close\r\n\r\n"
        ).encode(),
    )
    assert response.split(b" ", 2)[1] == b"413" and upstream.requests == []


def test_unsupported_transfer_encoding_is_refused(stack):
    _, upstream, port = stack
    response = raw(
        port,
        b"POST /api/v1/x HTTP/1.1\r\nHost: web\r\nTransfer-Encoding: gzip\r\nConnection: close\r\n\r\n",
    )
    assert response.split(b" ", 2)[1] == b"400" and upstream.requests == []


def test_upstream_timeout_maps_to_504_and_refusal_to_502(stack, monkeypatch):
    server, upstream, port = stack
    monkeypatch.setattr(
        server,
        "open_upstream_connection",
        lambda: http.client.HTTPConnection("127.0.0.1", upstream.port, timeout=0.3),
    )
    status, *_ = request(port, "GET", "/api/v1/slow")
    assert status == 504
    class RefusedConnection(http.client.HTTPConnection):
        def request(self, *args, **kwargs):
            raise ConnectionRefusedError("upstream refused the connection")

    monkeypatch.setattr(server, "open_upstream_connection", lambda: RefusedConnection("127.0.0.1", 1))
    status, _, data, _ = request(port, "GET", "/api/v1/x")
    assert status == 502 and b"127.0.0.1" not in data


def test_static_files_spa_fallback_and_security_headers(stack):
    server, upstream, port = stack
    status, headers, data, _ = request(port, "GET", "/")
    assert status == 200 and b"spa" in data
    assert headers["Content-Security-Policy"] == server.CSP
    assert "connect-src 'self';" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY" and headers["X-Content-Type-Options"] == "nosniff"
    status, _, data, _ = request(port, "GET", "/some/client/route")
    assert status == 200 and b"spa" in data
    status, _, data, _ = request(port, "GET", "/app.js")
    assert status == 200 and data.startswith(b"console")
    assert upstream.requests == []


def test_csp_is_restrictive_for_every_environment(monkeypatch):
    for app_env in ("development", "production"):
        csp = load_server(monkeypatch, app_env=app_env).CSP
        assert "connect-src 'self';" in csp
        assert "*" not in csp and "http" not in csp and "unsafe-eval" not in csp
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp


@pytest.mark.parametrize("app_env", [None, "", "staging", "Production"])
def test_server_fails_closed_without_a_known_environment(monkeypatch, app_env):
    with pytest.raises(RuntimeError, match="APP_ENV"):
        load_server(monkeypatch, app_env=app_env)


def test_upstream_defaults_and_overrides_are_limited_to_approved_origins(monkeypatch):
    dev = load_server(monkeypatch, app_env="development")
    assert dev.UPSTREAM_ORIGIN == "https://algoprofitx-api-50045554365.development.catalystappsail.in"
    prod = load_server(monkeypatch, app_env="production")
    assert prod.UPSTREAM_ORIGIN == "https://api.algoprofitx.com"
    prod_catalyst = load_server(
        monkeypatch, app_env="production", api_origin="https://algoprofitx-api-50045554365.catalystappsail.in/"
    )
    assert prod_catalyst.UPSTREAM_ORIGIN == "https://algoprofitx-api-50045554365.catalystappsail.in"
    for app_env, origin in (
        ("production", "https://algoprofitx-api-50045554365.development.catalystappsail.in"),
        ("development", "https://api.algoprofitx.com"),
        ("development", "http://algoprofitx-api-50045554365.development.catalystappsail.in"),
        ("production", "https://evil.example"),
        ("production", "https://api.algoprofitx.com@evil.example"),
        ("production", "https://api.algoprofitx.com/extra"),
    ):
        with pytest.raises(RuntimeError, match="API_PUBLIC_ORIGIN"):
            load_server(monkeypatch, app_env=app_env, api_origin=origin)


def test_environment_table_has_no_secrets_and_matches_backend_policy():
    import json

    table = json.loads((REPO_ROOT / "frontend" / "environments.json").read_text())
    assert set(table) == {"development", "production"}
    blob = json.dumps(table).lower()
    assert not any(word in blob for word in ("token", "secret", "password", "apikey"))
    assert table["production"]["webOrigin"] == "https://www.algoprofitx.com"
