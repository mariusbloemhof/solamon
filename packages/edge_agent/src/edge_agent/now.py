"""UTC timestamp helper for MQTT payloads."""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
