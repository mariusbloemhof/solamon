"""MQTT publisher loop for the bench MVP edge agent."""

from __future__ import annotations

import asyncio
import json
import ssl

import asyncio_mqtt as mqtt
import structlog

from .config import BootstrapConfig
from .now import now_utc
from .payloads import EdgeSample, build_acuvim_native_payload, build_heartbeat, build_lwt

log = structlog.get_logger()


async def publish_forever(config: BootstrapConfig, stop: asyncio.Event) -> None:
    sequence = 0
    while not stop.is_set():
        try:
            will = mqtt.Will(
                topic=config.heartbeat_topic,
                payload=json.dumps(build_lwt(config)),
                qos=1,
                retain=True,
            )
            async with mqtt.Client(
                hostname=config.mqtt_host,
                port=8883,
                username=config.mqtt_username,
                password=config.mqtt_password,
                tls_context=ssl.create_default_context(),
                will=will,
            ) as client:
                log.info("mqtt.connected", host=config.mqtt_host, site_slug=config.site_slug)
                while not stop.is_set():
                    sample = EdgeSample(sequence=sequence, timestamp=now_utc())
                    heartbeat = build_heartbeat(config, sample)
                    telemetry = build_acuvim_native_payload(config, sample)
                    await client.publish(
                        config.heartbeat_topic,
                        json.dumps(heartbeat),
                        qos=1,
                        retain=True,
                    )
                    await client.publish(
                        config.acuvim_topic,
                        json.dumps(telemetry),
                        qos=1,
                        retain=False,
                    )
                    log.info(
                        "publish.ok",
                        site_slug=config.site_slug,
                        heartbeat_topic=config.heartbeat_topic,
                        telemetry_topic=config.acuvim_topic,
                        sequence=sequence,
                    )
                    sequence += 1
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=config.publish_interval_seconds)
                    except TimeoutError:
                        pass
        except mqtt.MqttError as exc:
            log.warning("mqtt.disconnected", error=str(exc), retry_in_seconds=5)
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
