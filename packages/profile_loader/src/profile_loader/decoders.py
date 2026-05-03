"""Format decoders.

Spec: docs/specs/device-library/profile-schema.md §6
"""
from __future__ import annotations

from typing import Any, Protocol


class CustomDecoder(Protocol):
    """Vendor-specific decoder; called when format=custom."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any: ...


def default_registry() -> dict[str, CustomDecoder]:
    """Return a fresh registry seeded with built-in custom decoders.

    Currently empty; Task 8 adds AcuvimClockDecoder. Edge agents and probe-CLI
    register additional vendor decoders at module init.
    """
    return {
        "acuvim_clock": _AcuvimClockDecoderStub(),
    }


class _AcuvimClockDecoderStub:
    """Stub for acuvim_clock decoder; full implementation in Task 8."""
    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any:
        raise NotImplementedError("AcuvimClockDecoder implemented in Task 8")
