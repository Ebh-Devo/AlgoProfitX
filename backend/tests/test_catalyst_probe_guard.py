from types import SimpleNamespace

from app.core.config import AppEnvironment
from app.main import _catalyst_probe_crud_allowed


def _settings(app_env: AppEnvironment, enabled: bool = False):
    return SimpleNamespace(
        app_env=app_env,
        catalyst_probe_crud_enabled=enabled,
    )


def test_catalyst_crud_probe_is_off_by_default_even_in_development():
    # Unauthenticated write probes must never be implicitly exposed on a public AppSail.
    assert not _catalyst_probe_crud_allowed(_settings(AppEnvironment.DEVELOPMENT))


def test_catalyst_crud_probe_can_be_enabled_explicitly_in_development():
    assert _catalyst_probe_crud_allowed(_settings(AppEnvironment.DEVELOPMENT, enabled=True))


def test_catalyst_crud_probe_is_never_available_in_production():
    assert not _catalyst_probe_crud_allowed(
        _settings(AppEnvironment.PRODUCTION, enabled=True)
    )


def test_catalyst_crud_probe_requires_explicit_enablement_in_test():
    assert not _catalyst_probe_crud_allowed(_settings(AppEnvironment.TEST))
    assert _catalyst_probe_crud_allowed(_settings(AppEnvironment.TEST, enabled=True))
