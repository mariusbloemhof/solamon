"""Fingerprint matching: ModbusClient Protocol + per-read evaluators.

Spec: docs/specs/device-library/profile-schema.md §4
"""
from __future__ import annotations

from typing import Any, Protocol

from .decoders import decode_format
from .profile import FingerprintIdentifier, FingerprintRead


class ModbusClient(Protocol):
    """Minimal contract: matches pymodbus.AsyncModbusTcpClient surface we use.

    SOLID-I (interface segregation): only the methods we actually call.
    """
    async def read_holding_registers(self, address: int, count: int, slave: int = ...) -> Any: ...
    async def read_input_registers(self, address: int, count: int, slave: int = ...) -> Any: ...


async def _do_read(client: ModbusClient, address: int, count: int, fc: int, unit_id: int) -> Any:
    if fc == 3:
        return await client.read_holding_registers(address, count, slave=unit_id)
    if fc == 4:
        return await client.read_input_registers(address, count, slave=unit_id)
    raise ValueError(f"unsupported fingerprint fc: {fc}")


def _registers_to_bytes(registers: list[int]) -> bytes:
    out = bytearray()
    for r in registers:
        # Clamp to uint16 range (0-65535) to handle test values that overflow
        val = int(r) & 0xFFFF
        out.extend(val.to_bytes(2, "big", signed=False))
    return bytes(out)


async def evaluate_read(
    client: ModbusClient, read: FingerprintRead, unit_id: int,
) -> tuple[bool, str | None, Any]:
    """Run one fingerprint read. Returns (matched, failure_or_none, decoded_value)."""
    response = await _do_read(client, read.address, read.length, read.fc, unit_id)
    is_error = bool(getattr(response, "isError", lambda: False)())

    if read.expect_exception is not None:
        if not is_error:
            return False, "expected_exception not raised", None
        actual = getattr(response, "exception_code", None)
        if actual != read.expect_exception:
            return False, f"expected_exception {read.expect_exception:#x} got {actual!r}", None
        return True, None, None

    if is_error:
        return False, f"unexpected modbus exception {getattr(response, 'exception_code', None)!r}", None

    if read.format is None:
        return True, None, None

    buf = _registers_to_bytes(getattr(response, "registers", []))
    length_bytes = read.length * 2 if read.format == "ascii" else None
    value = decode_format(read.format, buf, 0, length_bytes)

    if read.expected is not None and value != read.expected:
        return False, f"expected {read.expected!r}, got {value!r}", value
    if read.expected_range is not None:
        lo, hi = read.expected_range
        if not (lo <= value <= hi):
            return False, f"value {value!r} outside range [{lo}, {hi}]", value
    if read.expected_contains is not None and isinstance(value, str):
        if read.expected_contains not in value:
            return False, f"value {value!r} does not contain {read.expected_contains!r}", value
    return True, None, value


async def evaluate_identifier(
    client: ModbusClient, ident: FingerprintIdentifier, unit_id: int,
) -> tuple[str, Any] | None:
    """Read one identifier. Returns (logical, value) on success, None on warning."""
    try:
        response = await _do_read(client, ident.address, ident.length, ident.fc, unit_id)
        if bool(getattr(response, "isError", lambda: False)()):
            return None
        buf = _registers_to_bytes(getattr(response, "registers", []))
        length_bytes = ident.length * 2 if ident.format == "ascii" else None
        value = decode_format(ident.format, buf, 0, length_bytes)
        if ident.expected_contains and isinstance(value, str) and ident.expected_contains not in value:
            return None
        return (ident.logical, value)
    except Exception:
        return None
