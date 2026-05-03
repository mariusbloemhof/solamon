import struct

import pytest

from profile_loader import DecodeError


def test_decode_returns_kw_after_scale_applied(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")
    payload = bytearray(realtime.length * 2)
    p = next(m for m in realtime.metrics if m.logical == "active_power_total")
    struct.pack_into(">f", payload, p.offset, 12350.0)  # 12350 W → expect 12.35 kW
    readings = profile.decode("realtime", bytes(payload), catalog=catalog, decoders=decoders)
    assert readings["active_power_total"].value == pytest.approx(12.350, rel=1e-6)


def test_decode_quality_good_inside_range(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")
    payload = bytearray(realtime.length * 2)
    f = next(m for m in realtime.metrics if m.logical == "frequency_hz")
    struct.pack_into(">f", payload, f.offset, 50.02)
    readings = profile.decode("realtime", bytes(payload), catalog=catalog, decoders=decoders)
    assert readings["frequency_hz"].quality == "good"


def test_decode_quality_uncertain_outside_range(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")
    payload = bytearray(realtime.length * 2)
    f = next(m for m in realtime.metrics if m.logical == "frequency_hz")
    struct.pack_into(">f", payload, f.offset, 100.0)
    readings = profile.decode("realtime", bytes(payload), catalog=catalog, decoders=decoders)
    assert readings["frequency_hz"].quality == "uncertain"


def test_decode_unknown_block_raises(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    with pytest.raises(DecodeError, match="not_a_block"):
        profile.decode("not_a_block", b"\x00" * 10, catalog=catalog, decoders=decoders)


def test_decode_response_too_short_raises(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")
    short = b"\x00" * (realtime.length * 2 - 1)
    with pytest.raises(DecodeError, match="length"):
        profile.decode("realtime", short, catalog=catalog, decoders=decoders)


def test_decode_clock_block_with_real_decoder():
    """Regression test for the bug where meter_clock missing 'length' field
    caused AcuvimClockDecoder to receive 2 bytes (length_bytes from `length or 1`)
    instead of 14, raising ValueError at decode time. Uses the REAL decoder, not
    the stub fixture, to exercise the full path."""
    from pathlib import Path

    from profile_loader import ProfileLoader

    REPO_ROOT = Path(__file__).resolve().parents[3]
    loader = ProfileLoader()  # Uses default_registry → real AcuvimClockDecoder
    catalog = loader.load_catalog(REPO_ROOT / "architecture" / "logical_metrics.yaml")
    profile = loader.load_profile(
        REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml", catalog
    )

    # 14 bytes = 7 sequential uint16s for Y/M/D/H/M/S/DoW
    payload = struct.pack(">7H", 2026, 5, 3, 14, 23, 45, 6)
    readings = profile.decode("clock", payload, catalog=catalog, decoders=loader.decoders)
    assert readings["meter_clock"].value == "2026-05-03T14:23:45Z"
