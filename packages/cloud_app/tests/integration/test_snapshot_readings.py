from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from cloud_app.api import telemetry


@pytest.mark.asyncio
async def test_snapshot_returns_metrics_jsonb(api_client, admin_token, pg_pool,
                                              seed_site, seed_device):
    now = datetime.now(timezone.utc)
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.device_snapshot (device_id, snapshot_time, metrics)
               VALUES ($1, $2, '{"active_power_total": 12.35}'::jsonb)""",
            UUID(seed_device.id), now,
        )
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{seed_device.id}/snapshot",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["metrics"]["active_power_total"] == 12.35


@pytest.mark.asyncio
async def test_readings_range_returns_points_in_window(api_client, admin_token, pg_pool,
                                                        seed_site, seed_device):
    """Insert 5 reading rows; query a window covering 3 of them."""
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    async with pg_pool.acquire() as conn:
        # Need to seed the catalog row too — use raw SQL minimal seed
        await conn.execute(
            """INSERT INTO app.logical_metric
                 (key, label, unit, data_type, category, is_cumulative, expected_range_min, expected_range_max)
               VALUES ('active_power_total','Total active','kW','float','power',false,-1000,1000)
               ON CONFLICT (key) DO NOTHING"""
        )
        for i in range(5):
            await conn.execute(
                """INSERT INTO timeseries.reading
                     (time, device_id, logical_metric_key, value, quality, block_name)
                   VALUES ($1, $2, 'active_power_total', $3, 'good', 'realtime')""",
                base + timedelta(minutes=i * 10), UUID(seed_device.id), 10.0 + i,
            )
    frm = (base + timedelta(minutes=5)).isoformat()
    to = (base + timedelta(minutes=35)).isoformat()
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{seed_device.id}/readings",
        params={"metric": "active_power_total", "from": frm, "to": to},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["metric"] == "active_power_total"
    assert len(body["points"]) == 3      # 10, 20, 30 minutes


@pytest.mark.asyncio
async def test_raw_readings_limit_keeps_latest_points(monkeypatch, api_client, admin_token,
                                                       pg_pool, seed_site, seed_device):
    monkeypatch.setattr(telemetry, "MAX_RAW_POINTS", 3)
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app.logical_metric
                 (key, label, unit, data_type, category, is_cumulative, expected_range_min, expected_range_max)
               VALUES ('active_power_total','Total active','kW','float','power',false,-1000,1000)
               ON CONFLICT (key) DO NOTHING"""
        )
        for i in range(5):
            await conn.execute(
                """INSERT INTO timeseries.reading
                     (time, device_id, logical_metric_key, value, quality, block_name)
                   VALUES ($1, $2, 'active_power_total', $3, 'good', 'realtime')""",
                base + timedelta(minutes=i), UUID(seed_device.id), 10.0 + i,
            )

    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{seed_device.id}/readings",
        params={
            "metric": "active_power_total",
            "from": base.isoformat(),
            "to": (base + timedelta(minutes=10)).isoformat(),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert res.status_code == 200
    assert [p["value"] for p in res.json()["points"]] == [12.0, 13.0, 14.0]


@pytest.mark.asyncio
async def test_readings_rejects_window_over_30_days(api_client, admin_token,
                                                     seed_site, seed_device):
    res = await api_client.get(
        f"/api/v1/sites/{seed_site.slug}/devices/{seed_device.id}/readings",
        params={
            "metric": "active_power_total",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-04-01T00:00:00Z",   # > 30 days
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 422
