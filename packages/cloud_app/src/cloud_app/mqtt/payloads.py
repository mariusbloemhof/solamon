"""Pydantic models for MQTT payloads — validates every message coming in."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    version: Literal["1.0"]
    site_slug: str
    device_id: UUID
    timestamp: datetime
    block: str
    source: Literal["modbus_poll", "replay_buffer"]
    quality: Literal["good", "uncertain", "bad"]
    readings: dict[str, float | int | str | None]


class HeartbeatPayload(BaseModel):
    version: Literal["1.0"]
    site_slug: str
    timestamp: datetime
    status: Literal["online", "offline"]
    edge_version: str | None = None
    buffer_depth_seconds: int = 0
    last_modbus_success: datetime | None = None
    modbus_errors_per_minute: float = 0.0
    halted_blocks: list[str] = Field(default_factory=list)


class CommandAckPayload(BaseModel):
    version: Literal["1.0"]
    id: UUID
    site_slug: str
    device_id: UUID
    status: Literal["confirmed", "failed"]
    received_at: datetime
    modbus_write_at: datetime | None = None
    readback_at: datetime | None = None
    confirmed_value: dict[str, Any] | None = None
    error_message: str | None = None
