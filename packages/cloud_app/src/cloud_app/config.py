"""Settings — loaded from env once at startup. SOLID-D: domain code receives
this rather than reading os.environ directly."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    http_port: int = 8000
    log_level: str = "INFO"
    domain: str | None = None
    # Bench-MVP fields — used by the composition root to map incoming Acuvim
    # MQTT messages to a known site + device row. Promoted to the per-site
    # provisioning record once the seed CLI graduates beyond bench mode.
    acuvim_topic: str = "solamon/+/acuvim/+/data"
    bench_site_slug: str | None = None
    bench_device_id: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            jwt_secret=os.environ["JWT_SECRET"],
            mqtt_host=os.environ["MQTT_HOST"],
            mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
            mqtt_username=os.environ.get("MQTT_USERNAME") or None,
            mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
            http_port=int(os.environ.get("HTTP_PORT", "8000")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            domain=os.environ.get("DOMAIN") or None,
            acuvim_topic=os.environ.get("ACUVIM_TOPIC", "solamon/+/acuvim/+/data"),
            bench_site_slug=os.environ.get("BENCH_SITE_SLUG") or None,
            bench_device_id=os.environ.get("BENCH_DEVICE_ID") or None,
        )
