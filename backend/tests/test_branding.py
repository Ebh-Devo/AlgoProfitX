from app.core.config import Settings
from app.main import create_app
from app.instrument_identity import is_synthetic_equity_symbol


def test_default_application_name(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    settings = Settings(
        database_url="postgresql+asyncpg://example.invalid/app",
        secret_key="test-only-secret",
        _env_file=None,
    )
    assert settings.app_name == "AlgoProfitX"


def test_openapi_uses_configured_application_name(monkeypatch):
    monkeypatch.setenv("APP_NAME", "AlgoProfitX")
    from app.core.config import get_settings

    get_settings.cache_clear()
    application = create_app()
    assert application.title == "AlgoProfitX API"
    assert application.openapi()["info"]["title"] == "AlgoProfitX API"
    get_settings.cache_clear()


def test_current_and_legacy_synthetic_symbols_remain_supported():
    assert is_synthetic_equity_symbol("ALGOPROFITX_TEST_EQ")
    assert is_synthetic_equity_symbol("TRADEEBH_TEST_EQ")
