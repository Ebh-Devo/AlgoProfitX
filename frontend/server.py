import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(os.environ.get("STATIC_ROOT", "/app/dist")).resolve()
ENVIRONMENTS = json.loads(
    (Path(__file__).resolve().parent / "environments.json").read_text(encoding="utf-8")
)


def api_origin_for(app_env: str | None) -> str:
    """Return the single API origin the CSP may connect to; never a default."""
    if app_env not in ENVIRONMENTS:
        raise RuntimeError("APP_ENV must be one of: " + ", ".join(sorted(ENVIRONMENTS)))
    return ENVIRONMENTS[app_env]["apiOrigin"]


def content_security_policy(app_env: str | None) -> str:
    return (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        f"img-src 'self' data:; connect-src 'self' {api_origin_for(app_env)}; "
        "manifest-src 'self'; upgrade-insecure-requests"
    )


CSP = content_security_policy(os.environ.get("APP_ENV"))


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


if __name__ == "__main__":
    port = int(
        os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT")
        or os.environ.get("PORT")
        or "8000"
    )
    ThreadingHTTPServer(("0.0.0.0", port), SpaHandler).serve_forever()
