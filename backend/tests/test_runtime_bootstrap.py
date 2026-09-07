"""Test cold imports without inheriting pytest's configured application modules."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("environment", ["development", "production"])
def test_missing_configuration_is_live_but_product_routes_fail_closed(environment):
    env = {k: v for k, v in os.environ.items() if k.upper() not in {
        "DATABASE_URL", "SECRET_KEY", "PGSSLROOTCERT", "PGSSLROOTCERT_B64"
    }}
    env["APP_ENV"] = environment
    code = '''
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.config import Settings
with patch.dict(Settings.model_config, {"env_file": None}):
    from app.runtime import app
with TestClient(app) as client:
    assert client.get('/health/live').status_code == 200
    for method, path in [('GET', '/health/ready'), ('POST', '/api/v1/auth/login'),
                         ('GET', '/api/v1/strategies'), ('GET', '/openapi.json')]:
        response = client.request(method, path)
        assert response.status_code == 503
        assert response.json() == {'status': 'unavailable', 'dependency': 'configuration'}
import sys
assert 'app.db.session' not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, "Cold bootstrap health contract failed"
    assert "ValidationError" not in result.stderr
    assert "input_value" not in result.stderr


def test_invalid_production_configuration_remains_unavailable():
    env = dict(os.environ, APP_ENV="production", DEBUG="true",
               DATABASE_URL="postgresql+asyncpg://test:sentinel-password@localhost/unused",
               SECRET_KEY="sentinel-secret-never-log")
    code = '''
from fastapi.testclient import TestClient
from app.runtime import app
with TestClient(app) as client:
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 503
    assert client.post('/api/v1/auth/login').status_code == 503
'''
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, "Invalid production configuration enabled the API"
    for marker in ("sentinel-password", "sentinel-secret-never-log", "input_value"):
        assert marker not in result.stdout + result.stderr
