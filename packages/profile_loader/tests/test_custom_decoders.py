import struct

import pytest

from profile_loader.decoders import AcuvimClockDecoder, default_registry


def test_default_registry_includes_acuvim_clock():
    registry = default_registry()
    assert "acuvim_clock" in registry
    assert isinstance(registry["acuvim_clock"], AcuvimClockDecoder)


def test_decodes_iso_format():
    """7 sequential uint16s: Y, M, D, H, M, S, DoW (DoW discarded)."""
    buf = struct.pack(">7H", 2026, 5, 3, 14, 23, 45, 6)
    assert AcuvimClockDecoder().decode(buf, 0, 14) == "2026-05-03T14:23:45Z"


def test_decodes_with_offset():
    buf = b"\x00" * 4 + struct.pack(">7H", 2026, 12, 31, 23, 59, 59, 7)
    assert AcuvimClockDecoder().decode(buf, 4, 14) == "2026-12-31T23:59:59Z"


def test_invalid_month_raises():
    buf = struct.pack(">7H", 2026, 13, 1, 0, 0, 0, 1)
    with pytest.raises(ValueError, match="month"):
        AcuvimClockDecoder().decode(buf, 0, 14)


def test_too_few_bytes_raises():
    with pytest.raises(ValueError, match="14 bytes"):
        AcuvimClockDecoder().decode(b"\x00" * 13, 0, 13)
