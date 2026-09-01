"""Offline invariants for the review-only DigitalOcean staging App Spec."""

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "deploy" / "digitalocean" / "staging.yaml"
STAGING_FRONTEND = "https://staging.algoprofitx.com"
STAGING_API = "https://api-staging.algoprofitx.com"


def keyed(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["name"]): item for item in items}


def env_map(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["key"]): item for item in items}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate() -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    require(isinstance(spec, dict), "App Spec must parse to an object")
    require(spec["region"] == "blr", "App Platform region must be Bangalore (blr)")

    services = keyed(spec.get("services", []))
    jobs = keyed(spec.get("jobs", []))
    databases = keyed(spec.get("databases", []))
    require(set(services) == {"api"}, "exactly one API service is required")
    require("static_sites" not in spec, "DigitalOcean must not contain a frontend static site")
    require(set(jobs) == {"migrate"}, "exactly one migration job is required")
    require(set(databases) == {"staging-postgres"}, "managed staging DB attachment is required")

    api = services["api"]
    require(api["dockerfile_path"] == "backend/Dockerfile", "F1 Dockerfile must be used")
    require(api["source_dir"] == "backend", "backend must be the Docker build context")
    require(api["instance_count"] == 1, "staging API must start with one replica")
    require(api["health_check"]["http_path"] == "/health/ready", "readiness path mismatch")
    require(api["liveness_health_check"]["http_path"] == "/health/live", "liveness path mismatch")

    migration = jobs["migrate"]
    require(migration["kind"] == "PRE_DEPLOY", "migration must be a pre-deploy job")
    require(
        migration["run_command"]
        == "python -m alembic upgrade head && python -m alembic current --check-heads",
        "migration and head verification command mismatch",
    )

    app_env = env_map(spec["envs"])
    expected = {
        "APP_ENV": "production",
        "FRONTEND_PUBLIC_URL": STAGING_FRONTEND,
        "API_PUBLIC_URL": STAGING_API,
        "CORS_ALLOWED_ORIGINS": STAGING_FRONTEND,
        "MARKET_DATA_PROVIDER": "synthetic",
        "DATABASE_URL": "${staging-postgres.DATABASE_URL}",
    }
    for key, value in expected.items():
        require(app_env[key]["value"] == value, f"{key} staging value mismatch")
    require("SECRET_KEY" not in app_env, "SECRET_KEY must not be committed")

    serialized = SPEC_PATH.read_text(encoding="utf-8")
    require("https://www.algoprofitx.com" not in serialized, "production frontend leaked into staging")
    require("https://api.algoprofitx.com" not in serialized, "production API leaked into staging")
    require("PASSWORD=" not in serialized.upper(), "password-like assignment found")

    domains = {item["domain"] for item in spec["domains"]}
    require(
        domains == {"api-staging.algoprofitx.com"},
        "DigitalOcean must expose only the staging API domain",
    )
    ingress = spec["ingress"]["rules"]
    require(len(ingress) == 1, "DigitalOcean must contain only API ingress")
    require(
        ingress[0]["match"]["authority"]["exact"] == "api-staging.algoprofitx.com"
        and ingress[0]["component"]["name"] == "api",
        "staging API ingress mismatch",
    )


if __name__ == "__main__":
    try:
        validate()
    except (AssertionError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"DigitalOcean staging App Spec validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"DigitalOcean staging App Spec validation passed: {SPEC_PATH.relative_to(ROOT)}")
