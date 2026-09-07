"""GitHub-hosted Docker smoke gate; never prints raw process logs or secrets."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError("Docker runtime verification command failed (output suppressed)")
    return result


def status(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


sha = os.environ["GITHUB_SHA"]
image = "algoprofitx-api:" + sha
config = json.loads(docker("image", "inspect", image).stdout)[0]
assert config["Os"] == "linux" and config["Architecture"] == "amd64"
assert config["Config"]["User"] == "10001:10001"
assert config["Config"]["WorkingDir"] == "/app"
assert "8000/tcp" in config["Config"]["ExposedPorts"]
assert config["Config"]["Labels"]["org.opencontainers.image.revision"] == sha
assert not any(item.split("=", 1)[0] in {
    "DATABASE_URL", "SECRET_KEY", "CATALYST_TOKEN", "PGSSLROOTCERT_B64"
} for item in config["Config"].get("Env", []))
docker("run", "--rm", "--entrypoint", "sh", image, "-c",
       "test ! -e /app/.env && test ! -d /app/.git && test ! -d /app/tests")

# Same app.main import/command as the previous Dockerfile: prove the diagnosed
# missing-settings crash with no environment configuration, without logging it.
baseline = docker("run", "--rm", "--entrypoint", "python", image,
                  "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
                  "--port", "8000", check=False)
assert baseline.returncode != 0
assert all(marker in baseline.stderr for marker in (
    "database_url", "secret_key", "Field required"
))
print("Original app.main startup reproduced: missing DATABASE_URL and SECRET_KEY")

key = secrets.token_urlsafe(48)
checks = []
for mode, env in (
    ("missing-development-config", []),
    ("missing-production-config", ["APP_ENV=production"]),
    ("configured-unreachable-db", ["APP_ENV=test", "DEBUG=false",
        "DATABASE_URL=postgresql+asyncpg://smoke:unused@127.0.0.1:5432/unused",
        "SECRET_KEY=" + key]),
):
    name = "algoprofitx-runtime-smoke"
    args = ["run", "--detach", "--name", name, "-p", "127.0.0.1:8000:8000"]
    for value in env:
        args.extend(["-e", value])
    try:
        docker(*args, image)
        for attempt in range(40):
            if status("/health/live") == 200:
                break
            time.sleep(1)
        assert status("/health/live") == 200, "Liveness unavailable"
        assert status("/health/ready") == 503, "Readiness must reject missing dependencies"
        if mode != "configured-unreachable-db":
            assert status("/api/v1/strategies") == 503
        else:
            # A normal application route exists when configuration is valid.
            assert status("/api/v1/strategies") in (401, 403)
        time.sleep(3)
        assert docker("inspect", name, "--format", "{{.State.Running}}").stdout.strip() == "true"
        logs = docker("logs", name)
        assert key not in logs.stdout + logs.stderr
        assert "input_value" not in logs.stdout + logs.stderr
        checks.append({"mode": mode, "live": 200, "ready": 503, "stays_running": True})
        print(mode + ": live=200, ready=503, process running")
    finally:
        docker("rm", "--force", name, check=False)

archive = Path(os.environ["RUNNER_TEMP"]) / "algoprofitx-api.tar"
docker("save", "--output", str(archive), image)
digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
archive.with_suffix(".tar.sha256").write_text(digest + "  algoprofitx-api.tar\n")
metadata = {
    "APP_SOURCE_REPO": "Ebhadmin/AlgoProfitX", "APP_SOURCE_SHA": sha,
    "DEPLOYMENT_REPO": "Ebh-Devo/algoprofitx-catalyst-connectivity-poc",
    "DEPLOYMENT_SHA": "c6e025501fc75f82bb31d80e01270480b8a052cc",
    "os": config["Os"], "architecture": config["Architecture"],
    "user": config["Config"]["User"], "workdir": config["Config"]["WorkingDir"],
    "entrypoint": config["Config"].get("Entrypoint"), "cmd": config["Config"]["Cmd"],
    "api_sha256": digest, "checks": checks,
}
(archive.parent / "api-runtime.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps(metadata, indent=2))
