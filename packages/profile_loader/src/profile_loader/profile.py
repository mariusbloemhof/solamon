"""Device profile: maps logical metrics to physical Modbus registers.

Spec: docs/specs/device-library/profile-schema.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal


@dataclass(frozen=True)
class DeviceInfo:
    manufacturer: str
    model: str
    category: Literal["meter", "pv_inverter", "bess_pcs", "bess_hub", "generator", "ppc", "gateway"]


@dataclass(frozen=True)
class ConnectionInfo:
    protocol: Literal["modbus_tcp", "modbus_rtu"]
    default_port: int
    default_unit_id: int


@dataclass(frozen=True)
class MetricMap:
    logical: str
    offset: int
    format: str
    scale: float = 1.0
    sign: Literal["signed", "unsigned"] | None = None
    length: int | None = None
    decoder: str | None = None
    aliased: bool = False


@dataclass(frozen=True)
class ReadBlock:
    name: str
    fc: int
    address: int
    length: int
    cadence_s: float
    metrics: list[MetricMap]


@dataclass(frozen=True)
class FingerprintRead:
    address: int
    length: int
    fc: int = 3
    format: str | None = None
    expected: Any = None
    expected_range: tuple[float, float] | None = None
    expected_contains: str | None = None
    expect_exception: int | None = None


@dataclass(frozen=True)
class FingerprintIdentifier:
    logical: str
    address: int
    length: int
    format: str
    fc: int = 3
    expected_contains: str | None = None


@dataclass(frozen=True)
class Fingerprint:
    reads: list[FingerprintRead]
    identifiers: list[FingerprintIdentifier] = field(default_factory=list)


@dataclass(frozen=True)
class ReadbackRegister:
    address: int
    offset: int
    format: str
    fc: int = 3


@dataclass(frozen=True)
class ControlSpec:
    logical: str
    fc: int
    address: int
    format: str
    allowed_values: list[Any] | None = None
    readback_register: ReadbackRegister | None = None
    readback_delay_ms: int = 500


@dataclass(frozen=True)
class Profile:
    schema_version: str
    device: DeviceInfo
    connection: ConnectionInfo
    fingerprint: Fingerprint
    read_blocks: list[ReadBlock]
    control: dict[str, ControlSpec] = field(default_factory=dict)

    def schedule(self) -> Iterable[tuple[ReadBlock, float]]:
        for block in self.read_blocks:
            yield (block, block.cadence_s)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Profile:
        device = DeviceInfo(**raw["device"])
        connection = ConnectionInfo(**raw["connection"])
        fingerprint = Fingerprint(
            reads=[_parse_fp_read(r) for r in raw["fingerprint"]["reads"]],
            identifiers=[_parse_fp_id(i) for i in raw["fingerprint"].get("identifiers", [])],
        )
        read_blocks = [_parse_block(b) for b in raw["read_blocks"]]
        control = {k: _parse_control(k, v) for k, v in raw.get("control", {}).items()}
        return cls(
            schema_version=raw.get("schema_version", "1.0"),
            device=device, connection=connection,
            fingerprint=fingerprint, read_blocks=read_blocks, control=control,
        )


def _parse_fp_read(r: dict[str, Any]) -> FingerprintRead:
    return FingerprintRead(
        address=r["address"], length=r["length"], fc=r.get("fc", 3),
        format=r.get("format"), expected=r.get("expected"),
        expected_range=tuple(r["expected_range"]) if "expected_range" in r else None,
        expected_contains=r.get("expected_contains"),
        expect_exception=r.get("expect_exception"),
    )


def _parse_fp_id(i: dict[str, Any]) -> FingerprintIdentifier:
    return FingerprintIdentifier(
        logical=i["logical"], address=i["address"], length=i["length"],
        format=i["format"], fc=i.get("fc", 3),
        expected_contains=i.get("expected_contains"),
    )


def _parse_block(b: dict[str, Any]) -> ReadBlock:
    metrics = [
        MetricMap(
            logical=m["logical"], offset=m["offset"], format=m["format"],
            scale=m.get("scale", 1.0), sign=m.get("sign"),
            length=m.get("length"), decoder=m.get("decoder"),
            aliased=m.get("aliased", False),
        )
        for m in b["metrics"]
    ]
    return ReadBlock(name=b["name"], fc=b["fc"], address=b["address"],
                     length=b["length"], cadence_s=b["cadence_s"], metrics=metrics)


def _parse_control(logical: str, spec: dict[str, Any]) -> ControlSpec:
    rb = spec.get("readback_register")
    readback = (
        ReadbackRegister(
            address=rb["address"], offset=rb.get("offset", 0),
            format=rb["format"], fc=rb.get("fc", 3),
        ) if rb else None
    )
    return ControlSpec(
        logical=logical, fc=spec["fc"], address=spec["address"],
        format=spec["format"], allowed_values=spec.get("allowed_values"),
        readback_register=readback, readback_delay_ms=spec.get("readback_delay_ms", 500),
    )
