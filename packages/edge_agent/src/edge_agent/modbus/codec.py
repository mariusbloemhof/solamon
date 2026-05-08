"""Small Modbus codec helpers."""

from __future__ import annotations

import struct
from typing import Any

from profile_loader.decoders import decode_format


def registers_to_bytes(registers: list[int]) -> bytes:
    return b"".join(int(reg).to_bytes(2, "big", signed=False) for reg in registers)


def register_count(format_name: str) -> int:
    if format_name in {"float32_be", "float32_le", "float32_mb", "uint32_be", "int32_be", "dword_high_first"}:
        return 2
    return 1


def encode_register_value(value: Any, format_name: str) -> int | list[int]:
    if format_name in {"word", "uint16"}:
        return int(value)
    if format_name == "int16":
        return int(value) & 0xFFFF
    if format_name in {"uint32_be", "dword_high_first"}:
        raw = int(value)
        return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]
    if format_name == "int32_be":
        raw = int(value) & 0xFFFFFFFF
        return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]
    if format_name == "float32_be":
        b = struct.pack(">f", float(value))
        return [int.from_bytes(b[:2], "big"), int.from_bytes(b[2:], "big")]
    raise ValueError(f"unsupported write format: {format_name}")


def decode_register_value(registers: list[int], format_name: str) -> Any:
    return decode_format(format_name, registers_to_bytes(registers), 0)


def values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, float) or isinstance(expected, float):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected
