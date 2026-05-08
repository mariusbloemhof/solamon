"""Bootstrap config loaded from /etc/solamon/bootstrap.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class BootstrapConfig:
    schema_version: str
    site_slug: str
    cloud_url: str
    bearer_token: str
    device_host: str
    device_unit_id: int
    log_level: str = "INFO"
    publish_interval_seconds: float = 10.0

    @property
    def mqtt_host(self) -> str:
        parsed = urlparse(self.cloud_url)
        return parsed.hostname or self.cloud_url.removeprefix("https://").split("/")[0]

    @property
    def mqtt_username(self) -> str:
        return f"solamon-{self.site_slug}"

    @property
    def mqtt_password(self) -> str:
        return self.bearer_token

    @property
    def acuvim_topic(self) -> str:
        return f"solamon/{self.site_slug}/acuvim/{self.device_unit_id}/data"

    @property
    def heartbeat_topic(self) -> str:
        return f"solamon/{self.site_slug}/heartbeat"


def load_bootstrap(path: Path) -> BootstrapConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = [
        "schema_version",
        "site_slug",
        "cloud_url",
        "bearer_token",
        "device_host",
        "device_unit_id",
    ]
    missing = [key for key in required if key not in raw]
    if missing:
        raise KeyError(f"missing bootstrap config fields: {', '.join(missing)}")
    config = BootstrapConfig(
        schema_version=str(raw["schema_version"]),
        site_slug=str(raw["site_slug"]),
        cloud_url=str(raw["cloud_url"]).rstrip("/"),
        bearer_token=str(raw["bearer_token"]),
        device_host=str(raw["device_host"]),
        device_unit_id=int(raw["device_unit_id"]),
        log_level=str(raw.get("log_level", "INFO")),
        publish_interval_seconds=float(raw.get("publish_interval_seconds", 10.0)),
    )
    _validate_bootstrap(config)
    return config


def _validate_bootstrap(config: BootstrapConfig) -> None:
    if config.schema_version != "1.0":
        raise ValueError(f"unsupported bootstrap schema_version: {config.schema_version}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", config.site_slug):
        raise ValueError("site_slug must be 2-63 chars of lowercase letters, digits, or hyphens")
    parsed = urlparse(config.cloud_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("cloud_url must be an https URL")
    if not config.bearer_token.strip():
        raise ValueError("bearer_token must be non-empty")
    if not config.device_host.strip() or any(char.isspace() for char in config.device_host):
        raise ValueError("device_host must be a host name or IP address without whitespace")
    if not 1 <= config.device_unit_id <= 247:
        raise ValueError("device_unit_id must be in Modbus range 1..247")
    if config.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    if config.publish_interval_seconds <= 0:
        raise ValueError("publish_interval_seconds must be positive")
