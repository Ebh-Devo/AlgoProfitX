import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(os.environ.get("STATIC_ROOT", "/app/dist")).resolve()
API_ORIGIN = os.environ.get("API_PUBLIC_ORIGIN", "https://api.algoprofitx.com")


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


if __name__ == "__main__":
    port = int(
        os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT")
        or os.environ.get("PORT")
        or "8000"
    )
    ThreadingHTTPServer(("0.0.0.0", port), SpaHandler).serve_forever()
