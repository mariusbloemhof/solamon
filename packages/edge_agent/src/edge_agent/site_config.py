"""Cloud-fetched site config and cache handling."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import BootstrapConfig


@dataclass(frozen=True)
class Site:
    id: str
    slug: str
    name: str
    timezone: str = "UTC"


@dataclass(frozen=True)
class Device:
    id: str
    host: str
    port: int
    unit_id: int
    profile_slug: str


@dataclass(frozen=True)
class MqttConfig:
    broker_host: str
    broker_port: int
    username: str
    password: str
    client_id: str
    topic_prefix: str


@dataclass(frozen=True)
class SiteConfig:
    raw: dict[str, Any]
    site: Site
    device: Device
    profile: dict[str, Any]
    logical_metrics_catalog: dict[str, Any]
    mqtt: MqttConfig

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SiteConfig:
        site = raw["site"]
        device = raw["device"]
        mqtt = raw["mqtt"]
        site_slug = str(site["slug"])
        device_id = str(device["id"])
        topic_prefix = str(mqtt.get("topic_prefix", f"solamon/{site_slug}"))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", site_slug):
            raise ValueError("site.slug must be 2-63 chars of lowercase letters, digits, or hyphens")
        if not device_id:
            raise ValueError("device.id must be non-empty")
        if not str(device["host"]).strip():
            raise ValueError("device.host must be non-empty")
        if not 1 <= int(device.get("unit_id", 1)) <= 247:
            raise ValueError("device.unit_id must be in Modbus range 1..247")
        if topic_prefix != f"solamon/{site_slug}":
            raise ValueError("mqtt.topic_prefix must match solamon/{site.slug}")
        return cls(
            raw=raw,
            site=Site(
                id=str(site.get("id", "")),
                slug=str(site["slug"]),
                name=str(site.get("name", site["slug"])),
                timezone=str(site.get("timezone", "UTC")),
            ),
            device=Device(
                id=str(device["id"]),
                host=str(device["host"]),
                port=int(device.get("port", 502)),
                unit_id=int(device.get("unit_id", 1)),
                profile_slug=str(device["profile_slug"]),
            ),
            profile=raw["profile"],
            logical_metrics_catalog=raw["logical_metrics_catalog"],
            mqtt=MqttConfig(
                broker_host=str(mqtt["broker_host"]),
                broker_port=int(mqtt.get("broker_port", 8883)),
                username=str(mqtt["username"]),
                password=str(mqtt["password"]),
                client_id=str(mqtt.get("client_id", f"solamon-edge-{site['slug']}")),
                topic_prefix=topic_prefix,
            ),
        )


def fallback_site_config(bootstrap: BootstrapConfig) -> SiteConfig:
    """Minimal config for bench day when /edge/config is not implemented yet."""
    raw = {
        "site": {"id": bootstrap.site_slug, "slug": bootstrap.site_slug, "name": bootstrap.site_slug},
        "device": {
            "id": f"00000000-0000-4000-8000-{bootstrap.device_unit_id:012d}",
            "host": bootstrap.device_host,
            "port": 502,
            "unit_id": bootstrap.device_unit_id,
            "profile_slug": "acuvim_l",
        },
        "profile": {},
        "logical_metrics_catalog": {},
        "mqtt": {
            "broker_host": bootstrap.mqtt_host,
            "broker_port": 8883,
            "username": bootstrap.mqtt_username,
            "password": bootstrap.mqtt_password,
            "client_id": f"solamon-edge-{bootstrap.site_slug}",
            "topic_prefix": f"solamon/{bootstrap.site_slug}",
        },
    }
    return SiteConfig.from_dict(raw)


async def fetch_site_config(bootstrap: BootstrapConfig, bearer_token: str | None = None) -> SiteConfig:
    url = f"{bootstrap.cloud_url}/api/v1/edge/config/{bootstrap.site_slug}"
    headers = {"Authorization": f"Bearer {bearer_token or bootstrap.bearer_token}"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code in {401, 403}:
            raise PermissionError("bootstrap token rejected")
        response.raise_for_status()
        return SiteConfig.from_dict(response.json())


async def fetch_site_config_with_cached_token(
    bootstrap: BootstrapConfig,
    cache_path: Path,
) -> SiteConfig:
    try:
        return await fetch_site_config(bootstrap)
    except PermissionError:
        if not cache_path.exists():
            raise
        cached = load_cache(cache_path)
        if cached.mqtt.password == bootstrap.bearer_token:
            raise
        return await fetch_site_config(bootstrap, bearer_token=cached.mqtt.password)


def atomic_write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".site_config.tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def load_cache(path: Path) -> SiteConfig:
    return SiteConfig.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


async def load_or_fetch_site_config(
    bootstrap: BootstrapConfig,
    *,
    cache_path: Path = Path("/var/lib/solamon/site_config.yaml"),
    allow_fallback: bool = False,
) -> SiteConfig:
    try:
        config = await fetch_site_config_with_cached_token(bootstrap, cache_path)
        atomic_write_cache(cache_path, config.raw)
        return config
    except PermissionError:
        raise
    except Exception as exc:
        if cache_path.exists():
            return load_cache(cache_path)
        if allow_fallback:
            return fallback_site_config(bootstrap)
        raise RuntimeError("no_config_available") from exc
