"""Per-block Modbus poller."""

from __future__ import annotations

import asyncio
import time

import structlog

from edge_agent.buffer.store import Buffer, ReadingRow
from edge_agent.metrics import EdgeMetrics
from edge_agent.modbus.client import ModbusClient
from edge_agent.modbus.codec import registers_to_bytes
from edge_agent.now import now_utc
from edge_agent.site_config import SiteConfig
from profile_loader.catalog import Catalog
from profile_loader.decoders import CustomDecoder
from profile_loader.profile import Profile, ReadBlock

log = structlog.get_logger()


async def poll_one_cycle(
    *,
    profile: Profile,
    block: ReadBlock,
    client: ModbusClient,
    buffer: Buffer,
    metrics: EdgeMetrics,
    site_config: SiteConfig,
    catalog: Catalog | None = None,
    decoders: dict[str, CustomDecoder] | None = None,
) -> bool:
    started = time.monotonic()
    if block.fc == 3:
        result = await client.read_holding_registers(
            address=block.address,
            count=block.length,
            slave=site_config.device.unit_id,
        )
    elif block.fc == 4:
        result = await client.read_input_registers(
            address=block.address,
            count=block.length,
            slave=site_config.device.unit_id,
        )
    else:
        raise ValueError(f"unsupported read function code: {block.fc}")

    if result.isError():
        metrics.record_modbus_error(block.name)
        log.warning(
            "modbus.exception",
            block=block.name,
            exception_code=getattr(result, "exception_code", None),
        )
        return False

    timestamp = now_utc()
    decoded = profile.decode(
        block.name,
        registers_to_bytes(result.registers),
        catalog=catalog,
        decoders=decoders,
    )
    await buffer.write_batch(
        [
            ReadingRow(
                time=timestamp,
                device_id=site_config.device.id,
                logical_metric_key=key,
                block_name=block.name,
                value=reading.value,
                raw_value=reading.raw_value,
                quality=reading.quality,
            )
            for key, reading in decoded.items()
        ]
    )
    metrics.record_modbus_success(block.name)
    log.debug(
        "modbus.poll_success",
        block=block.name,
        metric_count=len(decoded),
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
    return True


async def poll_block(
    *,
    profile: Profile,
    block: ReadBlock,
    client: ModbusClient,
    buffer: Buffer,
    metrics: EdgeMetrics,
    site_config: SiteConfig,
    stop: asyncio.Event,
    catalog: Catalog | None = None,
    decoders: dict[str, CustomDecoder] | None = None,
) -> None:
    consecutive_failures = 0
    while not stop.is_set():
        started = time.monotonic()
        if block.name in metrics.halted_blocks:
            await asyncio.wait_for(stop.wait(), timeout=block.cadence_s)
            continue
        try:
            ok = await poll_one_cycle(
                profile=profile,
                block=block,
                client=client,
                buffer=buffer,
                metrics=metrics,
                site_config=site_config,
                catalog=catalog,
                decoders=decoders,
            )
            consecutive_failures = 0 if ok else consecutive_failures + 1
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            consecutive_failures += 1
            metrics.record_modbus_error(block.name)
            log.warning("modbus.poll_failed", block=block.name, error=str(exc))
        except Exception as exc:
            consecutive_failures += 1
            metrics.record_modbus_error(block.name)
            log.error("modbus.poll_failed", block=block.name, error=str(exc))
        if consecutive_failures >= 10:
            metrics.halt_block(block.name)
            log.error("modbus.block_halted", block=block.name)
        sleep_for = max(0.0, block.cadence_s - (time.monotonic() - started))
        try:
            await asyncio.wait_for(stop.wait(), timeout=sleep_for)
        except TimeoutError:
            pass
