"""/sites/{slug}/devices/* — device list + detail."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from ..auth.deps import CurrentUser
from ..models.pydantic import DeviceDetail, DeviceSnapshot, DeviceSummary

router = APIRouter(prefix="/sites/{slug}/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary], operation_id="listDevices")
async def list_devices(slug: str, request: Request, user: CurrentUser) -> list[DeviceSummary]:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT d.id, d.name, dt.manufacturer, dt.model, d.sub_variant,
                      d.host, d.port, d.unit_id, d.status, d.last_seen_at
               FROM app.device d
               JOIN app.device_type dt ON d.device_type_id = dt.id
               JOIN app.site s ON d.site_id = s.id
               JOIN app.site_access sa ON sa.site_id = s.id
               WHERE sa.user_id = $1 AND s.slug = $2
               ORDER BY d.name""",
            user.id, slug,
        )
    return [DeviceSummary(**dict(r)) for r in rows]


@router.get("/{device_id}", response_model=DeviceDetail, operation_id="getDevice")
async def get_device(slug: str, device_id: UUID, request: Request,
                     user: CurrentUser) -> DeviceDetail:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT d.id, d.name, dt.manufacturer, dt.model, d.sub_variant,
                      d.host, d.port, d.unit_id, d.status, d.last_seen_at,
                      d.firmware_version, d.serial_number, d.commissioned_at,
                      dt.profile_slug
               FROM app.device d
               JOIN app.device_type dt ON d.device_type_id = dt.id
               JOIN app.site s ON d.site_id = s.id
               JOIN app.site_access sa ON sa.site_id = s.id
               WHERE sa.user_id = $1 AND s.slug = $2 AND d.id = $3""",
            user.id, slug, device_id,
        )
        if row is None:
            raise HTTPException(404, "device not found")
        snap = await conn.fetchrow(
            "SELECT snapshot_time, metrics, operating_state, active_faults "
            "FROM app.device_snapshot WHERE device_id = $1",
            device_id,
        )
    snapshot = DeviceSnapshot(**dict(snap)) if snap else None
    return DeviceDetail(snapshot=snapshot, **dict(row))
