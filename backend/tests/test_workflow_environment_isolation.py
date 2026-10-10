"""Static guarantees that CI/CD cannot silently pick an unintended environment."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ENVIRONMENTS = json.loads((REPO_ROOT / "frontend" / "environments.json").read_text())
DEV_API_URL = ENVIRONMENTS["development"]["allowedApiBaseUrls"][0]
PROD_API_URL = ENVIRONMENTS["production"]["allowedApiBaseUrls"][0]


def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def build_steps(text: str) -> dict[str, str]:
    """Map each 'Build ... frontend archive' step name to its body."""
    parts = re.split(r"\n      - ", text)
    return {part.splitlines()[0]: part for part in parts if "frontend archive" in part.splitlines()[0]}


def test_every_web_image_build_declares_environment_and_matching_api_url():
    steps = build_steps(workflow("build-catalyst.yml"))
    assert len(steps) == 2
    seen = {}
    for body in steps.values():
        env = re.search(r"^\s+APP_ENV=(\w+)$", body, re.MULTILINE).group(1)
        url = re.search(r"^\s+VITE_API_BASE_URL=(\S+)$", body, re.MULTILINE).group(1)
        assert f"-{env}" in body  # tag and archive name carry the environment
        assert f"algoprofitx-web-{env}.tar" in body
        seen[env] = url
    assert seen == {"development": DEV_API_URL, "production": PROD_API_URL}


def test_no_build_uses_an_unlabelled_web_image_or_archive():
    text = workflow("build-catalyst.yml")
    assert "algoprofitx-web.tar" not in text
    assert not re.search(r"algoprofitx-web:\$\{\{ github\.sha \}\}\s*$", text, re.MULTILINE)
    assert not re.search(r"algoprofitx-web:\$\{GITHUB_SHA\}(?!-)", text)


def test_ci_builds_each_environment_with_an_explicit_target():
    text = workflow("ci.yml")
    assert "VITE_APP_ENV: production" in text
    assert "VITE_APP_ENV: development" in text
    assert text.count("node scripts/check-environment.mjs") >= 2


def test_development_deploy_uses_fixed_target_and_only_the_development_web_image():
    text = workflow("deploy-catalyst-development.yml")
    for pinned in (
        'CATALYST_PROJECT_ID: "36851000000392052"',
        'CATALYST_ORG_ID: "60069781151"',
        "CATALYST_DC: in",
        "CATALYST_TARGET_ENVIRONMENT: Development",
    ):
        assert pinned in text
    # Dispatch inputs are limited to release provenance; none can pick a target.
    inputs = re.search(r"inputs:\n(.*?)\npermissions:", text, re.DOTALL).group(1)
    assert set(re.findall(r"^      (\w+):$", inputs, re.MULTILINE)) == {
        "release_run_id",
        "source_sha",
        "api_sha256",
        "web_sha256",
    }
    sources = re.findall(r'--source "docker-archive://[^"]+/release/([^"]+)"', text)
    assert sources == ["algoprofitx-api.tar", "algoprofitx-web-development.tar"]
    assert "algoprofitx-web-production.tar" not in " ".join(sources)


def test_no_workflow_deploys_to_production():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "CATALYST_TARGET_ENVIRONMENT: Production" not in text, path.name
        assert not re.search(r"--env(ironment)?[ =]+[Pp]roduction", text), path.name


def job_block(text: str, job: str) -> str:
    pattern = rf"^  {job}:\n(.*?)(?=^  [\w-]+:\n|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    assert match, job
    return match.group(1)


def test_web_builds_are_same_origin_for_each_environment():
    for env, table in ENVIRONMENTS.items():
        assert table["allowedApiBaseUrls"] == [f"{table['webOrigin']}/api/v1"], env


def test_ci_has_a_database_free_catalyst_runtime_job():
    ci = workflow("ci.yml")
    runtime = job_block(ci, "catalyst-runtime")
    assert "services:" not in runtime and "postgres" not in runtime.lower().replace("postgresql", "")
    assert "requirements-production.txt" in runtime
    assert "asyncpg|alembic|redis" in runtime
    backend = job_block(ci, "backend")
    assert "services:" in backend and "postgres" in backend  # legacy suite only


def test_container_smoke_test_runs_the_catalyst_provider_not_a_database():
    container = job_block(workflow("ci.yml"), "backend-container")
    assert "PERSISTENCE_PROVIDER=catalyst" in container
    assert "DATABASE_URL" not in container
    assert "APP_ENV=test" not in container
    assert "asyncpg|alembic|redis" in container


def test_no_workflow_selects_postgresql_or_the_worker_mode_for_a_deployed_runtime():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "PERSISTENCE_PROVIDER=postgresql" not in text.replace(
            "refused-postgresql", ""
        ) or path.name == "ci.yml", path.name
        assert "BACKTEST_EXECUTION_MODE=worker" not in text, path.name
