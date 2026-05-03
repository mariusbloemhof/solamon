"""Format decoders.

Spec: docs/specs/device-library/profile-schema.md §6
"""
from __future__ import annotations

import struct
from typing import Any, Callable, Protocol


class CustomDecoder(Protocol):
    """Vendor-specific decoder; called when format=custom."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any: ...


_BuiltinFn = Callable[[bytes, int, int | None], Any]


def _f32_be(b: bytes, o: int, _: int | None) -> float:
    return struct.unpack_from(">f", b, o)[0]


def _f32_le(b: bytes, o: int, _: int | None) -> float:
    return struct.unpack_from("<f", b, o)[0]


def _f32_mb(buf: bytes, off: int, _: int | None) -> float:
    a, b, c, d = buf[off : off + 4]
    return struct.unpack(">f", bytes([b, a, d, c]))[0]


def _u16(b: bytes, o: int, _: int | None) -> int:
    return struct.unpack_from(">H", b, o)[0]


def _i16(b: bytes, o: int, _: int | None) -> int:
    return struct.unpack_from(">h", b, o)[0]


def _u32_be(b: bytes, o: int, _: int | None) -> int:
    return struct.unpack_from(">I", b, o)[0]


def _i32_be(b: bytes, o: int, _: int | None) -> int:
    return struct.unpack_from(">i", b, o)[0]


def _dword_hf(buf: bytes, off: int, _: int | None) -> int:
    high, low = struct.unpack_from(">HH", buf, off)
    return (high << 16) | low


def _ascii(buf: bytes, off: int, length_bytes: int | None) -> str:
    if length_bytes is None:
        raise ValueError("ascii decode requires length_bytes")
    raw = buf[off : off + length_bytes]
    return raw.rstrip(b"\x00 ").decode("ascii", errors="replace")


_BUILTIN: dict[str, _BuiltinFn] = {
    "float32_be": _f32_be,
    "float32_le": _f32_le,
    "float32_mb": _f32_mb,
    "uint16": _u16,
    "int16": _i16,
    "word": _u16,
    "uint32_be": _u32_be,
    "int32_be": _i32_be,
    "dword_high_first": _dword_hf,
    "ascii": _ascii,
}


def decode_format(
    format: str, buffer: bytes, offset: int, length_bytes: int | None = None
) -> Any:
    """Decode a single value from `buffer` at `offset` using `format`."""
    if format not in _BUILTIN:
        raise KeyError(f"unknown format: {format}")
    return _BUILTIN[format](buffer, offset, length_bytes)


def default_registry() -> dict[str, CustomDecoder]:
    """Return a fresh registry seeded with built-in custom decoders.

    Task 8 replaces _AcuvimClockDecoderStub with the real AcuvimClockDecoder.
    """
    return {
        "acuvim_clock": _AcuvimClockDecoderStub(),
    }


class _AcuvimClockDecoderStub:
    """Transient stub for acuvim_clock; full implementation in Task 8."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any:
        raise NotImplementedError("AcuvimClockDecoder implemented in Task 8")
