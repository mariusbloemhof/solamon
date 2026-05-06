def test_can_import_cloud_app():
    import cloud_app
    assert cloud_app.__name__ == "cloud_app"


def test_settings_loads_required_fields(monkeypatch):
    from cloud_app.config import Settings
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("JWT_SECRET", "test")
    monkeypatch.setenv("MQTT_HOST", "mqtt")
    monkeypatch.setenv("MQTT_USERNAME", "solamon-cloud")
    monkeypatch.setenv("MQTT_PASSWORD", "p")
    monkeypatch.setenv("DOMAIN", "example.com")
    s = Settings.from_env()
    assert s.database_url == "postgresql://x"
    assert s.jwt_secret == "test"


def test_settings_missing_field_raises(monkeypatch):
    import pytest
    from cloud_app.config import Settings
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        Settings.from_env()
