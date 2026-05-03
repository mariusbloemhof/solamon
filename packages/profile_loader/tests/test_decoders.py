import struct

import pytest

from profile_loader.decoders import decode_format


def test_float32_be_decodes_50hz():
    assert decode_format("float32_be", struct.pack(">f", 50.02), 0) == pytest.approx(50.02, rel=1e-6)


def test_float32_le_decodes_50hz():
    assert decode_format("float32_le", struct.pack("<f", 50.02), 0) == pytest.approx(50.02, rel=1e-6)


def test_float32_mb_decodes_50hz():
    """Middle-endian (BADC): swap each 16-bit word."""
    be = struct.pack(">f", 50.02)
    mb = bytes([be[1], be[0], be[3], be[2]])
    assert decode_format("float32_mb", mb, 0) == pytest.approx(50.02, rel=1e-6)


def test_uint16_decodes_basic():
    assert decode_format("uint16", struct.pack(">H", 12345), 0) == 12345


def test_int16_decodes_negative():
    assert decode_format("int16", struct.pack(">h", -1234), 0) == -1234


def test_uint32_be_decodes_big_value():
    assert decode_format("uint32_be", struct.pack(">I", 4_000_000_000), 0) == 4_000_000_000


def test_int32_be_decodes_negative():
    assert decode_format("int32_be", struct.pack(">i", -100_000), 0) == -100_000


def test_dword_high_first_acuvim_energy():
    """1234567 = 0x0012D687: high=0x0012 at low addr, low=0xD687 at high addr."""
    buf = struct.pack(">HH", 0x0012, 0xD687)
    assert decode_format("dword_high_first", buf, 0) == 1234567


def test_ascii_decodes_with_length():
    payload = b"Accuenergy\x00\x00\x00\x00\x00\x00"
    assert decode_format("ascii", payload, 0, length_bytes=16) == "Accuenergy"


def test_offset_works():
    buf = struct.pack(">ff", 50.02, 49.98)
    assert decode_format("float32_be", buf, 4) == pytest.approx(49.98, rel=1e-6)


def test_unknown_format_raises():
    with pytest.raises(KeyError):
        decode_format("not_a_format", b"\x00\x00\x00\x00", 0)


def test_word_is_alias_for_uint16():
    assert decode_format("word", struct.pack(">H", 42), 0) == 42
