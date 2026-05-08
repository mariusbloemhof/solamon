"""Telemetry ingestion: validated payload -> DB writes.

SOLID-S: this module ONLY routes validated payloads to DB. Validation lives
in payloads.py; MQTT subscription lives in __main__/composition root.
"""
from __future__ import annotations

import asyncpg
import structlog

from .payloads import TelemetryPayload

log = structlog.get_logger()

NUMERIC_TYPES = {"float", "int"}


async def process_telemetry_message(pool: asyncpg.Pool, payload: TelemetryPayload) -> None:
    """Insert numeric readings into timeseries.reading; merge ALL into snapshot."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Look up data_type per metric key — drop unknown silently with a warning.
            keys = list(payload.readings.keys())
            if not keys:
                return
            type_rows = await conn.fetch(
                "SELECT key, data_type FROM app.logical_metric WHERE key = ANY($1::text[])",
                keys,
            )
            types = {r["key"]: r["data_type"] for r in type_rows}

            # Numeric readings -> hypertable.
            for key, value in payload.readings.items():
                dt = types.get(key)
                if dt is None:
                    log.warning("ingestion.unknown_metric", key=key)
                    continue
                if dt in NUMERIC_TYPES and isinstance(value, (int, float)):
                    await conn.execute(
                        """INSERT INTO timeseries.reading
                             (time, device_id, logical_metric_key, value, quality, block_name, received_at)
                           VALUES ($1, $2, $3, $4, $5, $6, NOW())
                           ON CONFLICT (time, device_id, logical_metric_key, block_name) DO NOTHING""",
                        payload.timestamp, payload.device_id, key, float(value),
                        payload.quality, payload.block,
                    )

            # Snapshot upsert: merge the whole readings dict into JSONB.
            # Pass the dict directly — the asyncpg jsonb codec (registered
            # in db.pool._init_connection) handles JSON serialization. Calling
            # json.dumps here would double-encode the value.
            metrics_dict = {k: v for k, v in payload.readings.items() if k in types}
            await conn.execute(
                """INSERT INTO app.device_snapshot (device_id, snapshot_time, metrics)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (device_id) DO UPDATE
                     SET snapshot_time = EXCLUDED.snapshot_time,
                         metrics = app.device_snapshot.metrics || EXCLUDED.metrics
                   WHERE EXCLUDED.snapshot_time >= app.device_snapshot.snapshot_time""",
                payload.device_id, payload.timestamp, metrics_dict,
            )

            # Touch device.last_seen_at + status.
            await conn.execute(
                """UPDATE app.device
                     SET last_seen_at = $1, status = 'online'
                   WHERE id = $2""",
                payload.timestamp, payload.device_id,
            )
