"""The package must ship the migration SQL + openapi.yaml. Both are
authoritative copies of the editorial files in docs/specs/cloud/."""
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parents[2]


def test_migration_sql_is_present():
    sql = (PKG / "migrations" / "0001_initial.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS app.site" in sql
    assert "CREATE TABLE IF NOT EXISTS timeseries.reading" in sql


def test_openapi_yaml_is_valid_yaml():
    raw = yaml.safe_load((PKG / "openapi.yaml").read_text(encoding="utf-8"))
    assert raw["openapi"].startswith("3.")
    assert "/auth/login" in raw["paths"]
    assert "/sites/{slug}/devices/{device_id}/snapshot" in raw["paths"]


def test_openapi_every_path_has_operationId():
    """Required for openapi-typescript SDK generation in the web UI."""
    raw = yaml.safe_load((PKG / "openapi.yaml").read_text(encoding="utf-8"))
    for path, ops in raw["paths"].items():
        for method, op in ops.items():
            if method in ("get", "post", "put", "delete", "patch"):
                assert "operationId" in op, f"{method.upper()} {path} missing operationId"
