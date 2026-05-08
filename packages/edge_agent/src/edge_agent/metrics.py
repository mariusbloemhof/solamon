"""In-process health counters for heartbeat payloads."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta


class EdgeMetrics:
    def __init__(self) -> None:
        self._modbus_errors: deque[datetime] = deque()
        self._last_modbus_success: datetime | None = None
        self.halted_blocks: set[str] = set()

    def record_modbus_error(self, block_name: str | None = None) -> None:
        self._modbus_errors.append(datetime.now(UTC))
        self._evict_old_errors()

    def record_modbus_success(self, block_name: str | None = None) -> None:
        self._last_modbus_success = datetime.now(UTC)
        if block_name:
            self.halted_blocks.discard(block_name)

    def halt_block(self, block_name: str) -> None:
        self.halted_blocks.add(block_name)

    def modbus_errors_per_minute_total(self) -> float:
        self._evict_old_errors()
        return float(len(self._modbus_errors))

    def last_modbus_success_iso(self) -> str | None:
        if self._last_modbus_success is None:
            return None
        return self._last_modbus_success.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _evict_old_errors(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=1)
        while self._modbus_errors and self._modbus_errors[0] < cutoff:
            self._modbus_errors.popleft()
