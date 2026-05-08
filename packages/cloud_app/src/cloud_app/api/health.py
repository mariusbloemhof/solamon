"""/health — liveness probe used by the cloud-bootstrap acceptance check
and by future load-balancer / CloudWatch monitors.

DB readiness is verified by a `SELECT 1` round-trip on the pool. MQTT
readiness is reported from `app.state.mqtt_connected`, which the
composition root flips on/off as the subscriber loop connects / disconnects.
"""
from __future__ import annotations

from typing import Literal

import asyncpg
from fastapi import APIRouter, Request
from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    mqtt: Literal["ok", "error"]


router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
async def get_health(request: Request) -> Health:
    pool: asyncpg.Pool = request.app.state.pool
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db = "ok"
    except Exception:
        db = "error"

    mqtt = "ok" if getattr(request.app.state, "mqtt_connected", False) else "error"
    status = "ok" if db == "ok" and mqtt == "ok" else "degraded"
    return Health(status=status, db=db, mqtt=mqtt)
