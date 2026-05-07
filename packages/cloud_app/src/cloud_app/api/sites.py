"""/sites + /sites/{slug}."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from ..auth.deps import CurrentUser
from ..models.pydantic import (
    DeviceSummary, SiteDetail, SiteHealth, SiteSummary,
)

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteSummary], operation_id="listSites")
async def list_sites(request: Request, user: CurrentUser) -> list[SiteSummary]:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.slug, s.name, s.timezone, s.last_seen_at, s.is_active
               FROM app.site s
               JOIN app.site_access sa ON sa.site_id = s.id
               WHERE sa.user_id = $1
               ORDER BY s.slug""",
            user.id,
        )
    return [SiteSummary(**dict(r)) for r in rows]


@router.get("/{slug}", response_model=SiteDetail, operation_id="getSite")
async def get_site(slug: str, request: Request, user: CurrentUser) -> SiteDetail:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        site = await conn.fetchrow(
            """SELECT s.id, s.slug, s.name, s.timezone, s.last_seen_at, s.is_active
               FROM app.site s
               JOIN app.site_access sa ON sa.site_id = s.id
               WHERE sa.user_id = $1 AND s.slug = $2""",
            user.id, slug,
        )
        if site is None:
            raise HTTPException(404, "site not found")
        devices = await conn.fetch(
            """SELECT d.id, d.name, dt.manufacturer, dt.model, d.sub_variant,
                      d.host, d.port, d.unit_id, d.status, d.last_seen_at
               FROM app.device d JOIN app.device_type dt ON d.device_type_id = dt.id
               WHERE d.site_id = $1
               ORDER BY d.name""",
            site["id"],
        )
        # SiteHealth derived from heartbeat + reading aggregates — for MVP stub via last_seen_at
        health = SiteHealth(last_heartbeat_at=site["last_seen_at"])
    return SiteDetail(
        slug=site["slug"], name=site["name"], timezone=site["timezone"],
        last_seen_at=site["last_seen_at"], is_active=site["is_active"],
        devices=[DeviceSummary(**dict(d)) for d in devices], health=health,
    )
