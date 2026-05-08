from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from edge_agent.config import BootstrapConfig, load_bootstrap


def test_load_bootstrap_config(tmp_path: Path):
    path = tmp_path / "bootstrap.yaml"
    path.write_text(
        """
schema_version: "1.0"
site_slug: bench
cloud_url: https://cloud.amendi.dev
bearer_token: secret
device_host: 192.168.1.254
device_unit_id: 1
log_level: DEBUG
""",
        encoding="utf-8",
    )

    config = load_bootstrap(path)

    assert config.site_slug == "bench"
    assert config.mqtt_host == "cloud.amendi.dev"
    assert config.mqtt_username == "solamon-bench"
    assert config.acuvim_topic == "solamon/bench/acuvim/1/data"
    assert config.heartbeat_topic == "solamon/bench/heartbeat"


def test_load_bootstrap_rejects_missing_required_field(tmp_path: Path):
    path = tmp_path / "bootstrap.yaml"
    path.write_text("site_slug: bench\n", encoding="utf-8")

    with pytest.raises(KeyError):
        load_bootstrap(path)


def test_bootstrap_config_is_frozen():
    config = BootstrapConfig(
        schema_version="1.0",
        site_slug="bench",
        cloud_url="https://cloud.amendi.dev",
        bearer_token="secret",
        device_host="192.168.1.254",
        device_unit_id=1,
    )

    with pytest.raises(FrozenInstanceError):
        config.site_slug = "changed"
