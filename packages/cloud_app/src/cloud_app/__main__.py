"""Composition root — wires concrete adapters; called as `python -m cloud_app`.

For the bench MVP this runs two coroutines concurrently:
    1. The FastAPI HTTP server (uvicorn programmatic).
    2. An MQTT subscriber that translates Acuvim AXM-WEB2 native payloads
       into TelemetryPayload and dispatches to the ingestion worker.

Both share a single asyncpg pool. Migrations run once on startup.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import asyncio_mqtt as mqtt
import structlog
import uvicorn

from .app import create_app
from .config import Settings
from .db.migrations import run_migrations
from .db.pool import create_pool
from .mqtt.adapters.acuvim import parse_acuvim_payload
from .mqtt.ingestion import process_telemetry_message


log = structlog.get_logger()


async def _run_http(app, settings: Settings) -> None:
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.http_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    await uvicorn.Server(config).serve()


async def _run_mqtt(app, pool, settings: Settings) -> None:
    if not settings.bench_site_slug or not settings.bench_device_id:
        log.warning(
            "mqtt.disabled",
            reason="BENCH_SITE_SLUG and BENCH_DEVICE_ID not set; skipping subscriber",
        )
        # Block forever so asyncio.gather doesn't return early.
        await asyncio.Event().wait()
        return

    site_slug = settings.bench_site_slug
    device_id = UUID(settings.bench_device_id)

    while True:
        try:
            async with mqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username,
                password=settings.mqtt_password,
            ) as client:
                async with client.messages() as messages:
                    await client.subscribe(settings.acuvim_topic)
                    app.state.mqtt_connected = True
                    log.info(
                        "mqtt.subscribed",
                        host=settings.mqtt_host,
                        port=settings.mqtt_port,
                        topic=settings.acuvim_topic,
                    )
                    async for message in messages:
                        try:
                            raw = json.loads(message.payload)
                        except (ValueError, UnicodeDecodeError) as exc:
                            log.warning("mqtt.payload.parse_fail",
                                        topic=str(message.topic), error=str(exc))
                            continue
                        try:
                            payload = parse_acuvim_payload(
                                raw, site_slug=site_slug, device_id=device_id,
                            )
                        except Exception as exc:
                            log.warning("mqtt.adapter.fail",
                                        topic=str(message.topic), error=str(exc))
                            continue
                        try:
                            await process_telemetry_message(pool, payload)
                            log.debug("mqtt.ingested",
                                      topic=str(message.topic),
                                      n_readings=len(payload.readings))
                        except Exception as exc:
                            log.error("mqtt.ingest.fail",
                                      topic=str(message.topic), error=str(exc))
        except mqtt.MqttError as exc:
            app.state.mqtt_connected = False
            log.warning("mqtt.disconnected", error=str(exc), retry_in_seconds=5)
            await asyncio.sleep(5)


async def _async_main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level)))

    pool = await create_pool(settings.database_url, min_size=2, max_size=10)
    try:
        await run_migrations(pool)
        log.info("startup.migrations.done")
        app = create_app(pool=pool, jwt_secret=settings.jwt_secret)
        await asyncio.gather(
            _run_http(app, settings),
            _run_mqtt(app, pool, settings),
        )
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
