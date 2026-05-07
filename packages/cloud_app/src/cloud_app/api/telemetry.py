"""Snapshot + readings range queries."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from ..auth.deps import CurrentUser
from ..models.pydantic import DeviceSnapshot, ReadingPoint, ReadingSeries

router = APIRouter(prefix="/sites/{slug}/devices/{device_id}", tags=["telemetry"])

MAX_RAW_WINDOW = timedelta(days=30)


async def _check_access(pool: asyncpg.Pool, user_id: UUID, slug: str, device_id: UUID) -> None:
    async with pool.acquire() as conn:
        ok = await conn.fetchval(
            """SELECT 1 FROM app.device d
               JOIN app.site s ON d.site_id = s.id
               JOIN app.site_access sa ON sa.site_id = s.id
               WHERE sa.user_id = $1 AND s.slug = $2 AND d.id = $3""",
            user_id, slug, device_id,
        )
    if ok is None:
        raise HTTPException(404, "device not found or no access")


@router.get("/snapshot", response_model=DeviceSnapshot, operation_id="getDeviceSnapshot")
async def get_snapshot(slug: str, device_id: UUID, request: Request,
                       user: CurrentUser) -> DeviceSnapshot:
    pool: asyncpg.Pool = request.app.state.pool
    await _check_access(pool, user.id, slug, device_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT snapshot_time, metrics, operating_state, active_faults "
            "FROM app.device_snapshot WHERE device_id = $1",
            device_id,
        )
    if row is None:
        # Return an empty snapshot rather than 404 — fresh device pre-first-telemetry.
        return DeviceSnapshot(snapshot_time=datetime.fromtimestamp(0), metrics={})
    data = dict(row)
    if isinstance(data.get("metrics"), str):
        data["metrics"] = json.loads(data["metrics"])
    if isinstance(data.get("active_faults"), str):
        data["active_faults"] = json.loads(data["active_faults"])
    return DeviceSnapshot(**data)


@router.get("/readings", response_model=ReadingSeries, operation_id="getDeviceReadings")
async def get_readings(
    slug: str, device_id: UUID, request: Request, user: CurrentUser,
    metric: str = Query(...),
    frm: str = Query(..., alias="from"),
    to: str = Query(...),
    aggregate: Literal["raw", "1min", "15min", "1hour"] = Query("raw"),
    cursor: str | None = Query(None),
) -> ReadingSeries:
    pool: asyncpg.Pool = request.app.state.pool
    await _check_access(pool, user.id, slug, device_id)
    # Handle URL encoding where + becomes space
    frm_str = frm.replace(" ", "+") if " " in frm else frm
    to_str = to.replace(" ", "+") if " " in to else to
    frm_dt = datetime.fromisoformat(frm_str)
    to_dt = datetime.fromisoformat(to_str)
    if aggregate == "raw" and (to_dt - frm_dt) > MAX_RAW_WINDOW:
        raise HTTPException(422, "raw window must be ≤ 30 days; use aggregate=1hour for longer ranges")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT time, value, quality FROM timeseries.reading
               WHERE device_id = $1 AND logical_metric_key = $2
                 AND time >= $3 AND time <= $4
               ORDER BY time ASC LIMIT 5000""",
            device_id, metric, frm_dt, to_dt,
        )
    points = [ReadingPoint(time=r["time"], value=r["value"], quality=r["quality"]) for r in rows]
    return ReadingSeries(metric=metric, aggregate=aggregate, points=points)
