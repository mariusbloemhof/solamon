"""MQTT publish, heartbeat, and command-subscribe runtime."""

from __future__ import annotations

import asyncio
import json
import ssl
from itertools import groupby
from typing import Any

import asyncio_mqtt as mqtt
import structlog
from cachetools import TTLCache

from profile_loader.catalog import Catalog
from profile_loader.profile import Profile

from . import __version__
from .buffer.store import Buffer, BufferRow
from .command import CommandPayload, handle_command
from .metrics import EdgeMetrics
from .modbus.client import ModbusClient
from .now import now_utc
from .payloads import build_lwt
from .site_config import SiteConfig

log = structlog.get_logger()


def build_telemetry_payload(site_config: SiteConfig, block_name: str, timestamp: str, rows: list[BufferRow]) -> dict[str, Any]:
    quality_rank = {"good": 0, "uncertain": 1, "bad": 2}
    worst = max((row.quality for row in rows), key=lambda q: quality_rank.get(q, 0))
    return {
        "version": "1.0",
        "site_slug": site_config.site.slug,
        "device_id": site_config.device.id,
        "timestamp": timestamp,
        "block": block_name,
        "source": "modbus_poll",
        "quality": worst,
        "readings": {row.logical_metric_key: row.value for row in rows},
    }


async def publish_pending_batch(client: mqtt.Client, site_config: SiteConfig, buffer: Buffer) -> int:
    rows = await buffer.fetch_unpublished(limit=200)
    if not rows:
        return 0
    published = 0
    topic = f"{site_config.mqtt.topic_prefix}/telemetry/{site_config.device.id}"
    rows.sort(key=lambda row: (row.block_name, row.time, row.id))
    for (block_name, timestamp), grouped in groupby(rows, key=lambda row: (row.block_name, row.time)):
        group = list(grouped)
        await client.publish(
            topic,
            json.dumps(build_telemetry_payload(site_config, block_name, timestamp, group)),
            qos=1,
        )
        await buffer.mark_published([row.id for row in group])
        published += len(group)
    return published


async def publish_loop(client: mqtt.Client, site_config: SiteConfig, buffer: Buffer, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            count = await publish_pending_batch(client, site_config, buffer)
            if count:
                log.info("mqtt.telemetry_published", rows=count)
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except TimeoutError:
            pass


async def heartbeat_loop(
    client: mqtt.Client,
    site_config: SiteConfig,
    buffer: Buffer,
    metrics: EdgeMetrics,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        payload = {
            "version": "1.0",
            "site_slug": site_config.site.slug,
            "timestamp": now_utc(),
            "status": "online",
            "edge_version": __version__,
            "buffer_depth_seconds": await buffer.compute_buffer_depth_seconds(),
            "last_modbus_success": metrics.last_modbus_success_iso(),
            "modbus_errors_per_minute": metrics.modbus_errors_per_minute_total(),
            "halted_blocks": sorted(metrics.halted_blocks),
        }
        await client.publish(
            f"{site_config.mqtt.topic_prefix}/heartbeat",
            json.dumps(payload),
            qos=1,
            retain=True,
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass


async def command_loop(
    client: mqtt.Client,
    messages,
    site_config: SiteConfig,
    profile: Profile,
    catalog: Catalog,
    modbus: ModbusClient,
) -> None:
    recent: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1000, ttl=300)
    async for message in messages:
        try:
            cmd = CommandPayload.from_json(message.payload)
        except Exception as exc:
            log.error("command.parse_failed", error=str(exc))
            continue
        await handle_command(
            client=client,
            site_config=site_config,
            profile=profile,
            catalog=catalog,
            modbus=modbus,
            command=cmd,
            recent=recent,
        )


async def mqtt_loop(
    *,
    site_config: SiteConfig,
    profile: Profile,
    catalog: Catalog,
    buffer: Buffer,
    metrics: EdgeMetrics,
    modbus: ModbusClient,
    stop: asyncio.Event,
) -> None:
    backoff = 1.0
    will = mqtt.Will(
        topic=f"{site_config.mqtt.topic_prefix}/heartbeat",
        payload=json.dumps(build_lwt_for_site(site_config)),
        qos=1,
        retain=True,
    )
    while not stop.is_set():
        try:
            async with mqtt.Client(
                hostname=site_config.mqtt.broker_host,
                port=site_config.mqtt.broker_port,
                username=site_config.mqtt.username,
                password=site_config.mqtt.password,
                client_id=site_config.mqtt.client_id,
                clean_session=False,
                keepalive=60,
                tls_context=ssl.create_default_context(),
                will=will,
            ) as client:
                backoff = 1.0
                command_topic = f"{site_config.mqtt.topic_prefix}/commands/{site_config.device.id}"
                async with client.messages_for_topic(command_topic) as messages:
                    await client.subscribe(command_topic, qos=1)
                    await asyncio.gather(
                        publish_loop(client, site_config, buffer, stop),
                        heartbeat_loop(client, site_config, buffer, metrics, stop),
                        command_loop(client, messages, site_config, profile, catalog, modbus),
                    )
        except mqtt.MqttError as exc:
            log.warning("mqtt.disconnected", error=str(exc), backoff=backoff)
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 60)


def build_lwt_for_site(site_config: SiteConfig) -> dict[str, object]:
    # Reuse the existing function with a tiny adapter shape.
    class _Config:
        site_slug = site_config.site.slug

    return build_lwt(_Config())
