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
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    domain: str
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            jwt_secret=os.environ["JWT_SECRET"],
            mqtt_host=os.environ["MQTT_HOST"],
            mqtt_port=int(os.environ.get("MQTT_PORT", "8883")),
            mqtt_username=os.environ["MQTT_USERNAME"],
            mqtt_password=os.environ["MQTT_PASSWORD"],
            domain=os.environ["DOMAIN"],
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
