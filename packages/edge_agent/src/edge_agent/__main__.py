"""Composition root for the Pi edge agent."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import structlog

from profile_loader.catalog import Catalog
from profile_loader.decoders import default_registry
from profile_loader.loader import ProfileLoader
from profile_loader.profile import Profile

from .buffer.store import Buffer, rotate_once
from .config import load_bootstrap
from .metrics import EdgeMetrics
from .modbus.client import create_modbus_client
from .modbus.poller import poll_block
from .mqtt_runtime import mqtt_loop
from .site_config import (
    SiteConfig,
    atomic_write_cache,
    fetch_site_config_with_cached_token,
    load_or_fetch_site_config,
)


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


async def _async_main() -> None:
    config_path = Path(os.environ.get("SOLAMON_CONFIG", "/etc/solamon/bootstrap.yaml"))
    bootstrap = load_bootstrap(config_path)
    _configure_logging(bootstrap.log_level)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    cache_path = Path(os.environ.get("SOLAMON_SITE_CONFIG", "/var/lib/solamon/site_config.yaml"))
    buffer_path = Path(os.environ.get("SOLAMON_BUFFER", "/var/lib/solamon/readings.sqlite3"))
    allow_fallback = os.environ.get("SOLAMON_ALLOW_BOOTSTRAP_FALLBACK") == "1"
    site_config = await load_or_fetch_site_config(
        bootstrap,
        cache_path=cache_path,
        allow_fallback=allow_fallback,
    )
    profile, catalog, decoders = _load_profile_and_catalog(site_config)

    buffer = Buffer(buffer_path)
    await buffer.init()
    metrics = EdgeMetrics()
    modbus = create_modbus_client(site_config.device.host, site_config.device.port)
    connected = await modbus.connect()
    if connected:
        fp = await profile.fingerprint_match(modbus, unit_id=site_config.device.unit_id)
        if not fp.match:
            for block in profile.read_blocks:
                metrics.halt_block(block.name)
            metrics.mark_device_fault("fingerprint_mismatch")
            structlog.get_logger().error("modbus.fingerprint_mismatch", failures=fp.failures)

    tasks = [
        asyncio.create_task(
            poll_block(
                profile=profile,
                block=block,
                client=modbus,
                buffer=buffer,
                metrics=metrics,
                site_config=site_config,
                stop=stop,
                catalog=catalog,
                decoders=decoders,
            ),
            name=f"poll:{block.name}",
        )
        for block in profile.read_blocks
    ]
    tasks.append(
        asyncio.create_task(
            mqtt_loop(
                site_config=site_config,
                profile=profile,
                catalog=catalog,
                buffer=buffer,
                metrics=metrics,
                modbus=modbus,
                stop=stop,
            ),
            name="mqtt",
        )
    )
    tasks.append(asyncio.create_task(_rotation_loop(buffer, stop), name="buffer-rotation"))
    tasks.append(
        asyncio.create_task(
            _config_refresh_loop(bootstrap, cache_path, stop),
            name="config-refresh",
        )
    )

    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _load_profile_and_catalog(site_config: SiteConfig) -> tuple[Profile, Catalog, dict]:
    if site_config.profile and site_config.logical_metrics_catalog:
        return (
            Profile.from_dict(site_config.profile),
            Catalog.from_dict(site_config.logical_metrics_catalog),
            default_registry(),
        )
    root = Path(__file__).resolve()
    candidates = [
        Path("/app/architecture"),
        root.parents[4] / "architecture",
        Path.cwd() / "architecture",
    ]
    architecture = next((path for path in candidates if path.exists()), candidates[-1])
    loader = ProfileLoader(schema_dir=architecture)
    catalog = loader.load_catalog(architecture / "logical_metrics.yaml")
    profile = loader.load_profile(architecture / "profiles" / "acuvim_l.yaml", catalog)
    return profile, catalog, loader.decoders


async def _rotation_loop(buffer: Buffer, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await rotate_once(buffer)
        try:
            await asyncio.wait_for(stop.wait(), timeout=600)
        except TimeoutError:
            pass


async def _config_refresh_loop(
    bootstrap,
    cache_path: Path,
    stop: asyncio.Event,
) -> None:
    log = structlog.get_logger()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=300)
        except TimeoutError:
            pass
        if stop.is_set():
            break
        try:
            config = await fetch_site_config_with_cached_token(bootstrap, cache_path)
            atomic_write_cache(cache_path, config.raw)
            log.info("config.refresh_ok", site_slug=config.site.slug)
        except Exception as exc:
            log.warning("config.refresh_failed", error=str(exc))


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
