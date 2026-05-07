"""Test ingestion by calling process_telemetry_message directly with a fake
Pydantic-validated payload — no MQTT broker needed for this layer."""
from datetime import datetime, timezone
from uuid import UUID

import pytest

from cloud_app.mqtt.ingestion import process_telemetry_message
from cloud_app.mqtt.payloads import TelemetryPayload


@pytest.fixture
def telemetry_payload(seed_device, seed_site):
    return TelemetryPayload(
        version="1.0",
        site_slug=seed_site.slug,
        device_id=UUID(seed_device.id),
        timestamp=datetime.now(timezone.utc),
        block="realtime",
        source="modbus_poll",
        quality="good",
        readings={"frequency_hz": 50.02, "active_power_total": 12.35},
    )


@pytest.mark.asyncio
async def test_ingestion_inserts_numeric_readings_into_hypertable(
    pg_pool, seed_device, telemetry_payload
):
    # Seed required catalog entries
    async with pg_pool.acquire() as conn:
        for k, dt in [("frequency_hz", "float"), ("active_power_total", "float")]:
            await conn.execute(
                """INSERT INTO app.logical_metric
                     (key, label, unit, data_type, category, is_cumulative,
                      expected_range_min, expected_range_max)
                   VALUES ($1, $1, '', $2, 'power', false, -999999, 999999)
                   ON CONFLICT (key) DO NOTHING""",
                k, dt,
            )
    await process_telemetry_message(pg_pool, telemetry_payload)
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT logical_metric_key, value FROM timeseries.reading "
            "WHERE device_id = $1 ORDER BY logical_metric_key",
            UUID(seed_device.id),
        )
    assert len(rows) == 2
    assert {(r["logical_metric_key"], float(r["value"])) for r in rows} == {
        ("active_power_total", 12.35), ("frequency_hz", 50.02),
    }


@pytest.mark.asyncio
async def test_ingestion_upserts_snapshot(pg_pool, seed_device, telemetry_payload):
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.logical_metric
                 (key, label, unit, data_type, category, is_cumulative, expected_range_min, expected_range_max)
               VALUES ('frequency_hz', 'F', 'Hz', 'float', 'frequency', false, 40, 60)
               ON CONFLICT DO NOTHING"""
        )
    await process_telemetry_message(pg_pool, telemetry_payload)
    async with pg_pool.acquire() as conn:
        snap = await conn.fetchrow(
            "SELECT metrics, snapshot_time FROM app.device_snapshot WHERE device_id = $1",
            UUID(seed_device.id),
        )
    import json as _json
    metrics = _json.loads(snap["metrics"]) if isinstance(snap["metrics"], str) else snap["metrics"]
    assert metrics["frequency_hz"] == 50.02


@pytest.mark.asyncio
async def test_ingestion_dedups_on_unique_key(pg_pool, seed_device, telemetry_payload):
    """Same (time, device, metric, block) must not insert twice."""
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.logical_metric
                 (key, label, unit, data_type, category, is_cumulative, expected_range_min, expected_range_max)
               VALUES ('frequency_hz', 'F', 'Hz', 'float', 'frequency', false, 40, 60)
               ON CONFLICT DO NOTHING"""
        )
    await process_telemetry_message(pg_pool, telemetry_payload)
    await process_telemetry_message(pg_pool, telemetry_payload)
    async with pg_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM timeseries.reading WHERE device_id = $1",
            UUID(seed_device.id),
        )
    assert n == 1
