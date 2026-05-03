"""Fingerprint matching against a fake Modbus client (Protocol-based)."""

from typing import Any

import pytest


class FakeResponse:
    def __init__(self, registers: list[int] | None = None, exception_code: int | None = None):
        self.registers = registers or []
        self._exc = exception_code

    def isError(self) -> bool:
        return self._exc is not None

    @property
    def exception_code(self) -> int | None:
        return self._exc


class FakeModbusClient:
    """Implements the ModbusClient Protocol for tests — no pymodbus dependency."""

    def __init__(self, responses: dict[tuple[int, int, int], Any]):
        self.responses = responses

    async def read_holding_registers(self, address: int, count: int, slave: int = 1):
        return self.responses[(address, count, 3)]

    async def read_input_registers(self, address: int, count: int, slave: int = 1):
        return self.responses[(address, count, 4)]


def _build_responses_match(profile) -> dict:
    out: dict = {}
    for r in profile.fingerprint.reads:
        if r.expect_exception is not None:
            out[(r.address, r.length, r.fc)] = FakeResponse(exception_code=r.expect_exception)
        elif r.expected_range is not None:
            mid = int((r.expected_range[0] + r.expected_range[1]) / 2)
            out[(r.address, r.length, r.fc)] = FakeResponse(registers=[mid])
        elif r.expected is not None:
            out[(r.address, r.length, r.fc)] = FakeResponse(registers=[r.expected])
    return out


@pytest.mark.asyncio
async def test_fingerprint_match_succeeds(loaded_acuvim_l):
    _, profile, _ = loaded_acuvim_l
    client = FakeModbusClient(_build_responses_match(profile))
    result = await profile.fingerprint_match(client)
    assert result.match is True
    assert result.confidence in ("positive", "negative_fingerprint")
    assert result.failures == []


@pytest.mark.asyncio
async def test_fingerprint_match_fails_when_exception_doesnt_arrive(loaded_acuvim_l):
    """Acuvim L expects exception 0x02 at SunSpec block. If it returns data
    instead (i.e. talking to an Acuvim II), match must fail."""
    _, profile, _ = loaded_acuvim_l
    responses = _build_responses_match(profile)
    for r in profile.fingerprint.reads:
        if r.expect_exception is not None:
            responses[(r.address, r.length, r.fc)] = FakeResponse(registers=[1, 0])
    client = FakeModbusClient(responses)
    result = await profile.fingerprint_match(client)
    assert result.match is False
    assert any("exception" in f.lower() for f in result.failures)


@pytest.mark.asyncio
async def test_fingerprint_match_fails_when_value_outside_range(loaded_acuvim_l):
    _, profile, _ = loaded_acuvim_l
    responses = _build_responses_match(profile)
    for r in profile.fingerprint.reads:
        if r.expected_range is not None:
            responses[(r.address, r.length, r.fc)] = FakeResponse(registers=[99999])
    client = FakeModbusClient(responses)
    result = await profile.fingerprint_match(client)
    assert result.match is False
    assert any("range" in f for f in result.failures)


@pytest.mark.asyncio
async def test_fingerprint_match_collects_identifiers_when_match():
    """Synthetic profile with one identifier — verify it gets captured into
    FingerprintResult.identifiers when the fingerprint matches."""
    from profile_loader.profile import Profile

    profile = Profile.from_dict(
        {
            "schema_version": "1.0",
            "device": {"manufacturer": "Test", "model": "T", "category": "meter"},
            "connection": {"protocol": "modbus_tcp", "default_port": 502, "default_unit_id": 1},
            "fingerprint": {
                "reads": [
                    {"address": 0x100, "length": 1, "format": "uint16", "expected": 42},
                ],
                "identifiers": [
                    {"logical": "manufacturer", "address": 0x200, "length": 4, "format": "ascii"},
                ],
            },
            "read_blocks": [],
        }
    )

    client = FakeModbusClient(
        {
            (0x100, 1, 3): FakeResponse(registers=[42]),
            (0x200, 4, 3): FakeResponse(registers=[0x4163, 0x6375, 0x456E, 0x0000]),  # "Acuen"
        }
    )
    result = await profile.fingerprint_match(client)
    assert result.match is True
    assert result.identifiers.get("manufacturer") == "AccuEn"
