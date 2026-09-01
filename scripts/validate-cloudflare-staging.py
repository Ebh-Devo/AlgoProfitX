"""Offline invariants for the Cloudflare Pages staging frontend contract."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HEADERS = ROOT / "frontend" / "public" / "_headers"
DIST_HEADERS = ROOT / "frontend" / "dist" / "_headers"
CONTRACT = ROOT / "deploy" / "cloudflare" / "pages-staging.md"
STAGING_API_BASE = "https://api-staging.algoprofitx.com/api/v1"
STAGING_API_ORIGIN = "https://api-staging.algoprofitx.com"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate() -> None:
    source = SOURCE_HEADERS.read_text(encoding="utf-8")
    built = DIST_HEADERS.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    require(built == source, "Vite build did not preserve public/_headers exactly")

    required_headers = (
        "Content-Security-Policy:",
        "Strict-Transport-Security: max-age=31536000",
        "X-Content-Type-Options: nosniff",
        "Referrer-Policy: strict-origin-when-cross-origin",
        "Permissions-Policy:",
        "X-Frame-Options: DENY",
    )
    for header in required_headers:
        require(header in built, f"missing frontend header: {header}")

    require(f"connect-src 'self' {STAGING_API_ORIGIN}" in built, "staging API CSP mismatch")
    require("script-src 'self'" in built, "strict script policy missing")
    require("frame-ancestors 'none'" in built, "CSP frame protection missing")
    require("'unsafe-eval'" not in built, "CSP must not permit unsafe-eval")
    require("script-src 'self' 'unsafe-inline'" not in built, "CSP must not permit inline scripts")
    require("/assets/*\n  Cache-Control: public, max-age=31536000, immutable" in built, "asset cache policy mismatch")
    require("/index.html\n  Cache-Control: no-cache, max-age=0, must-revalidate" in built, "HTML cache policy mismatch")

    combined = source + contract
    require("localhost" not in combined.lower(), "localhost is forbidden in staging deployment files")
    require("http:" not in combined.lower(), "insecure HTTP is forbidden in staging deployment files")
    require("https://api.algoprofitx.com" not in combined, "production API leaked into staging contract")
    require(STAGING_API_BASE in contract, "Pages production environment URL mismatch")
    for value in ("Roshan-Baghwar/TradeEBH", "`main`", "`frontend`", "`pnpm build`", "`dist`"):
        require(value in contract, f"missing Pages build contract value: {value}")


if __name__ == "__main__":
    try:
        validate()
    except (AssertionError, OSError) as error:
        print(f"Cloudflare staging validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print("Cloudflare staging frontend validation passed: dist/_headers and Pages contract")
