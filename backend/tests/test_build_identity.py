"""Build identity: the non-secret source SHA and CI build run id exposed on ``/api/version``.

Synthetic environment values only; nothing contacts a live service.
"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.build_info import UNKNOWN, build_identity
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "0123456789abcdef0123456789abcdef01234567"


async def fetch_version() -> dict:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/api/version")
    assert response.status_code == 200
    return response.json()


def test_populated_identity_is_returned(monkeypatch):
    monkeypatch.setenv("APP_SOURCE_SHA", SHA)
    monkeypatch.setenv("APP_BUILD_RUN_ID", "38054507517")
    assert build_identity() == {"sha": SHA, "build_run_id": "38054507517"}


def test_unset_or_empty_identity_is_an_empty_string_as_before(monkeypatch):
    monkeypatch.delenv("APP_SOURCE_SHA", raising=False)
    monkeypatch.delenv("APP_BUILD_RUN_ID", raising=False)
    assert build_identity() == {"sha": "", "build_run_id": ""}
    monkeypatch.setenv("APP_SOURCE_SHA", "")
    monkeypatch.setenv("APP_BUILD_RUN_ID", "")
    assert build_identity() == {"sha": "", "build_run_id": ""}


@pytest.mark.parametrize(
    "value",
    [
        "abc1234",  # abbreviated
        SHA.upper(),  # wrong case
        SHA + "0",  # too long
        "g" * 40,  # not hex
        f"{SHA}\nSECRET_KEY=leak",  # trailing content
        "postgresql://user:password@host/db",
    ],
)
def test_a_malformed_sha_is_replaced_by_unknown_never_echoed(monkeypatch, value):
    monkeypatch.setenv("APP_SOURCE_SHA", value)
    assert build_identity()["sha"] == UNKNOWN


@pytest.mark.parametrize("value", ["abc", "12 34", "-1", "1" * 21, "1\n2"])
def test_a_malformed_run_id_is_replaced_by_unknown_never_echoed(monkeypatch, value):
    monkeypatch.setenv("APP_BUILD_RUN_ID", value)
    assert build_identity()["build_run_id"] == UNKNOWN


@pytest.mark.asyncio
async def test_the_endpoint_returns_exactly_the_approved_fields_and_no_environment_values(monkeypatch):
    monkeypatch.setenv("APP_SOURCE_SHA", SHA)
    monkeypatch.setenv("APP_BUILD_RUN_ID", "42")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:Distinct-db-secret@host/db")
    monkeypatch.setenv("SECRET_KEY", "Distinct-signing-secret")
    monkeypatch.setenv("CATALYST_TOKEN", "Distinct-catalyst-token")
    body = await fetch_version()
    assert set(body) == {"repository", "sha", "build_run_id", "component"}
    assert body["sha"] == SHA and body["build_run_id"] == "42"
    text = str(body)
    assert "Distinct" not in text


@pytest.mark.asyncio
async def test_the_endpoint_keeps_the_empty_sha_when_nothing_was_baked_in(monkeypatch):
    monkeypatch.delenv("APP_SOURCE_SHA", raising=False)
    monkeypatch.delenv("APP_BUILD_RUN_ID", raising=False)
    body = await fetch_version()
    assert body["sha"] == "" and body["build_run_id"] == ""


@pytest.mark.asyncio
async def test_a_malformed_value_is_never_echoed_by_the_endpoint(monkeypatch):
    monkeypatch.setenv("APP_SOURCE_SHA", "postgresql://user:Distinct-pw@host/db")
    monkeypatch.setenv("APP_BUILD_RUN_ID", "Distinct-run")
    body = await fetch_version()
    assert body["sha"] == UNKNOWN and body["build_run_id"] == UNKNOWN
    assert "Distinct" not in str(body)


# ----------------------------------------------------------- build and deploy wiring (static)


def test_the_image_bakes_in_the_build_run_id_from_a_build_argument():
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert 'ARG BUILD_RUN_ID=""' in dockerfile
    assert "APP_BUILD_RUN_ID=${BUILD_RUN_ID}" in dockerfile
    assert "APP_SOURCE_SHA=${VCS_REF}" in dockerfile


def test_the_release_build_passes_the_commit_and_run_id():
    build = (REPO_ROOT / ".github" / "workflows" / "build-catalyst.yml").read_text(encoding="utf-8")
    assert "VCS_REF=${{ github.sha }}" in build
    assert "BUILD_RUN_ID=${{ github.run_id }}" in build


def test_the_development_deploy_verifies_the_reported_build_after_deploying():
    deploy = (REPO_ROOT / ".github" / "workflows" / "deploy-catalyst-development.yml").read_text(encoding="utf-8")
    assert deploy.index("Deploy API to Catalyst Development") < deploy.index("Verify the deployed API reports the released build")
    verify = deploy[deploy.index("Verify the deployed API reports the released build"):]
    # Fixed Development origin, strict comparison against both dispatch inputs, and a failing exit.
    assert "https://algoprofitx-api-50045554365.development.catalystappsail.in" in verify
    assert '"$sha" = "$SOURCE_SHA"' in verify and '"$run_id" = "$RELEASE_RUN_ID"' in verify
    assert verify.rstrip().endswith("exit 1")
    # The target is never taken from a dispatch input.
    assert "inputs." not in verify
