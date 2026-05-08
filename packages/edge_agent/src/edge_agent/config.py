"""Bootstrap config loaded from /etc/solamon/bootstrap.yaml."""

from __future__ import annotations

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
    return BootstrapConfig(
        schema_version=str(raw["schema_version"]),
        site_slug=str(raw["site_slug"]),
        cloud_url=str(raw["cloud_url"]).rstrip("/"),
        bearer_token=str(raw["bearer_token"]),
        device_host=str(raw["device_host"]),
        device_unit_id=int(raw["device_unit_id"]),
        log_level=str(raw.get("log_level", "INFO")),
        publish_interval_seconds=float(raw.get("publish_interval_seconds", 10.0)),
    )
