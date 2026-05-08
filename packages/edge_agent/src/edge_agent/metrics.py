"""In-process health counters for heartbeat payloads."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta


class EdgeMetrics:
    def __init__(self) -> None:
        self._modbus_errors: deque[datetime] = deque()
        self._modbus_errors_by_block: dict[str, deque[datetime]] = defaultdict(deque)
        self._last_modbus_success: datetime | None = None
        self.halted_blocks: set[str] = set()
        self.device_fault: str | None = None

    def record_modbus_error(self, block_name: str | None = None) -> None:
        now = datetime.now(UTC)
        self._modbus_errors.append(now)
        if block_name:
            self._modbus_errors_by_block[block_name].append(now)
        self._evict_old_errors()

    def record_modbus_success(self, block_name: str | None = None) -> None:
        self._last_modbus_success = datetime.now(UTC)
        if block_name:
            self.halted_blocks.discard(block_name)

    def halt_block(self, block_name: str) -> None:
        self.halted_blocks.add(block_name)

    def mark_device_fault(self, reason: str) -> None:
        self.device_fault = reason

    def modbus_errors_per_minute_total(self) -> float:
        self._evict_old_errors()
        return float(len(self._modbus_errors))

    def modbus_errors_per_minute_by_block(self) -> dict[str, float]:
        self._evict_old_errors()
        return {
            block_name: float(len(errors))
            for block_name, errors in self._modbus_errors_by_block.items()
            if errors
        }

    def last_modbus_success_iso(self) -> str | None:
        if self._last_modbus_success is None:
            return None
        return self._last_modbus_success.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _evict_old_errors(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=1)
        while self._modbus_errors and self._modbus_errors[0] < cutoff:
            self._modbus_errors.popleft()
        for block_name in list(self._modbus_errors_by_block):
            errors = self._modbus_errors_by_block[block_name]
            while errors and errors[0] < cutoff:
                errors.popleft()
            if not errors:
                del self._modbus_errors_by_block[block_name]
