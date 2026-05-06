"""Pydantic v2 request + response models for the REST API.

These are the WIRE shapes; the openapi.yaml is the editorial spec, but FastAPI
generates the runtime spec from these classes. Keep them in lockstep.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ─── Auth ────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    tier: Literal["operations", "client"]
    role: Literal["admin", "operator", "viewer", "billing"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: User


# ─── Sites + devices ─────────────────────────────────────────────────────────


class SiteSummary(BaseModel):
    slug: str
    name: str
    timezone: str | None = None
    last_seen_at: datetime | None = None
    is_active: bool


class DeviceSummary(BaseModel):
    id: UUID
    name: str
    manufacturer: str | None = None
    model: str | None = None
    sub_variant: str | None = None
    host: str
    port: int
    unit_id: int
    status: Literal["online", "offline", "unreachable", "fault", "unknown"]
    last_seen_at: datetime | None = None


class SiteHealth(BaseModel):
    last_heartbeat_at: datetime | None = None
    heartbeat_age_seconds: int | None = None
    last_reading_at: datetime | None = None
    modbus_errors_per_minute: float = 0.0
    edge_buffer_depth_seconds: int = 0


class SiteDetail(SiteSummary):
    organisation: dict[str, Any] | None = None
    devices: list[DeviceSummary] = []
    health: SiteHealth | None = None


class DeviceDetail(DeviceSummary):
    firmware_version: str | None = None
    serial_number: str | None = None
    commissioned_at: datetime | None = None
    profile_slug: str | None = None
    snapshot: DeviceSnapshot | None = None


# ─── Telemetry ───────────────────────────────────────────────────────────────


class DeviceSnapshot(BaseModel):
    snapshot_time: datetime
    metrics: dict[str, Any] = Field(default_factory=dict)
    operating_state: str | None = None
    active_faults: list[str] | None = None


class ReadingPoint(BaseModel):
    time: datetime
    value: float | None
    quality: Literal["good", "uncertain", "bad"]


class ReadingSeries(BaseModel):
    metric: str
    aggregate: Literal["raw", "1min", "15min", "1hour"] = "raw"
    points: list[ReadingPoint] = []
    next_cursor: str | None = None


# ─── Control ─────────────────────────────────────────────────────────────────


class CommandIssue(BaseModel):
    logical_metric: str
    type: Literal["set_value"]
    parameters: dict[str, Any]


class IssuedBy(BaseModel):
    id: UUID
    display_name: str


class ControlCommand(BaseModel):
    id: UUID
    device_id: UUID
    logical_metric: str
    # Optional with default: OpenAPI's ControlCommand.type is in `properties` but
    # not `required`; the DB doesn't store `type` (it's redundant — always
    # 'set_value' in MVP). Keeps the model alignable with future additions.
    type: str = "set_value"
    parameters: dict[str, Any]
    status: Literal["pending", "sent", "confirmed", "failed", "expired"]
    issued_at: datetime
    sent_at: datetime | None = None
    acknowledged_at: datetime | None = None
    confirmed_value: dict[str, Any] | None = None
    error_message: str | None = None
    last_publish_error: str | None = None
    expires_at: datetime
    issued_by: IssuedBy | None = None


# ─── Catalog ─────────────────────────────────────────────────────────────────


class LogicalMetricApi(BaseModel):
    """Mirrors the catalog's LogicalMetric. Distinct from profile_loader's
    internal dataclass to keep the wire/domain boundary clean (SOLID-S)."""
    model_config = ConfigDict(extra="allow")
    key: str
    label: str
    unit: str
    data_type: str
    category: str
    is_cumulative: bool
    monotonic: bool | None = None
    direction_convention: str | None = None
    expected_range: tuple[float, float] | None = None
    is_writable: bool = False
    allowed_values: list[Any] | None = None


class DeviceProfileSummary(BaseModel):
    profile_slug: str
    manufacturer: str
    model: str
    category: str


class DeviceProfile(DeviceProfileSummary):
    profile_yaml: dict[str, Any]


class EdgeConfigMqtt(BaseModel):
    broker_host: str
    broker_port: int
    username: str
    password: str
    client_id: str
    topic_prefix: str


class EdgeConfig(BaseModel):
    site: dict[str, Any]
    device: dict[str, Any]
    profile: dict[str, Any]
    logical_metrics_catalog: dict[str, Any]
    mqtt: EdgeConfigMqtt


class Health(BaseModel):
    status: Literal["ok", "degraded", "fail"]
    db: Literal["ok", "degraded", "fail"]
    mqtt: Literal["ok", "degraded", "fail"]


class Problem(BaseModel):
    """RFC 7807 problem detail."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


# DeviceDetail had a forward-ref to DeviceSnapshot; rebuild now both are defined.
DeviceDetail.model_rebuild()
