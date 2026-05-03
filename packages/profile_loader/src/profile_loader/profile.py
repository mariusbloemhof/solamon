"""Device profile: maps logical metrics to physical Modbus registers.

Spec: docs/specs/device-library/profile-schema.md
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .decoders import decode_format
from .types import DecodeError, FingerprintResult, Reading, ValidationError

if TYPE_CHECKING:
    from .catalog import Catalog
    from .decoders import CustomDecoder
    from .fingerprint import ModbusClient


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

    def decode(
        self,
        block_name: str,
        response: bytes,
        catalog: Catalog | None = None,
        decoders: dict[str, CustomDecoder] | None = None,
    ) -> dict[str, Reading]:
        """Decode an FC03/FC04 response into a dict keyed by logical metric name.

        Pure function over the inputs; side-effect-free.
        """
        block = next((b for b in self.read_blocks if b.name == block_name), None)
        if block is None:
            raise DecodeError(f"unknown block: {block_name}")
        expected = block.length * 2
        if len(response) != expected:
            raise DecodeError(
                f"block '{block_name}': response length {len(response)} != expected {expected}"
            )
        result: dict[str, Reading] = {}
        for metric in block.metrics:
            if metric.format == "custom":
                if decoders is None or metric.decoder not in decoders:
                    raise DecodeError(
                        f"metric '{metric.logical}': decoder '{metric.decoder}' not provided"
                    )
                length_bytes = (metric.length or 1) * 2
                value = decoders[metric.decoder].decode(response, metric.offset, length_bytes)
                raw = None
            elif metric.format == "ascii":
                length_bytes = (metric.length or 0) * 2
                value = decode_format(metric.format, response, metric.offset, length_bytes)
                raw = None
            else:
                raw_value = decode_format(metric.format, response, metric.offset)
                value = (
                    raw_value * metric.scale if isinstance(raw_value, (int, float)) else raw_value
                )
                raw = raw_value if isinstance(raw_value, int) else None
            quality = "good"
            if catalog is not None:
                cm = catalog.get(metric.logical)
                if (
                    cm is not None
                    and cm.expected_range is not None
                    and isinstance(value, (int, float))
                ):
                    lo, hi = cm.expected_range
                    if value < lo or value > hi:
                        quality = "uncertain"
            result[metric.logical] = Reading(value=value, raw_value=raw, quality=quality)
        return result

    def validate_control(self, logical_metric: str, value: Any, catalog: Catalog) -> None:
        """Validates a control command. Raises ValidationError on bad input.

        Spec: profile-schema.md §7.1
        """
        cm = catalog.get(logical_metric)
        if cm is None:
            raise ValidationError(f"unknown metric: {logical_metric}")
        if not cm.is_writable:
            raise ValidationError(f"metric '{logical_metric}' is not writable in catalog")
        if logical_metric not in self.control:
            raise ValidationError(
                f"metric '{logical_metric}' is not exposed for control by this profile"
            )
        spec = self.control[logical_metric]
        allowed = spec.allowed_values if spec.allowed_values is not None else cm.allowed_values
        if allowed is not None and value not in allowed:
            raise ValidationError(
                f"value {value!r} not in allowed values {allowed} for '{logical_metric}'"
            )

    async def fingerprint_match(
        self,
        client: ModbusClient,
        unit_id: int | None = None,
    ) -> FingerprintResult:
        """Match device fingerprint via ModbusClient Protocol.

        Returns FingerprintResult with match status, confidence, identifiers, and failures.
        """
        # Lazy import: fingerprint.py imports FingerprintRead/FingerprintIdentifier
        # from this module, so a top-level reverse import would create a cycle.
        # decoders.py and types.py have no such cycle; their imports are at module top.
        from .fingerprint import evaluate_identifier, evaluate_read

        slave_id = unit_id if unit_id is not None else self.connection.default_unit_id
        failures: list[str] = []
        used_negative = False

        for read in self.fingerprint.reads:
            if read.expect_exception is not None:
                used_negative = True
            ok, reason, _ = await evaluate_read(client, read, slave_id)
            if not ok:
                failures.append(f"@{read.address:#06x}: {reason}")

        match = len(failures) == 0
        confidence = (
            "none" if not match else ("negative_fingerprint" if used_negative else "positive")
        )

        identifiers: dict[str, Any] = {}
        failed_identifiers: list[tuple[str, str]] = []
        if match:
            for ident in self.fingerprint.identifiers:
                result = await evaluate_identifier(client, ident, slave_id)
                if result[0] is None:
                    failed_identifiers.append((ident.logical, result[1]))
                else:
                    identifiers[result[0]] = result[1]

        return FingerprintResult(
            match=match,
            confidence=confidence,
            identifiers=identifiers,
            failures=failures,
            failed_identifiers=failed_identifiers,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Profile:
        """Parse a profile dict into a Profile dataclass. Always go through
        ProfileLoader.load_profile() for validated loading; this builder is the
        low-level wire used by the loader after schema validation.
        """
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
            device=device,
            connection=connection,
            fingerprint=fingerprint,
            read_blocks=read_blocks,
            control=control,
        )


def _parse_fp_read(r: dict[str, Any]) -> FingerprintRead:
    return FingerprintRead(
        address=r["address"],
        length=r["length"],
        fc=r.get("fc", 3),
        format=r.get("format"),
        expected=r.get("expected"),
        expected_range=tuple(r["expected_range"]) if "expected_range" in r else None,
        expected_contains=r.get("expected_contains"),
        expect_exception=r.get("expect_exception"),
    )


def _parse_fp_id(i: dict[str, Any]) -> FingerprintIdentifier:
    return FingerprintIdentifier(
        logical=i["logical"],
        address=i["address"],
        length=i["length"],
        format=i["format"],
        fc=i.get("fc", 3),
        expected_contains=i.get("expected_contains"),
    )


def _parse_block(b: dict[str, Any]) -> ReadBlock:
    metrics = [
        MetricMap(
            logical=m["logical"],
            offset=m["offset"],
            format=m["format"],
            scale=m.get("scale", 1.0),
            sign=m.get("sign"),
            length=m.get("length"),
            decoder=m.get("decoder"),
            aliased=m.get("aliased", False),
        )
        for m in b["metrics"]
    ]
    return ReadBlock(
        name=b["name"],
        fc=b["fc"],
        address=b["address"],
        length=b["length"],
        cadence_s=b["cadence_s"],
        metrics=metrics,
    )


def _parse_control(logical: str, spec: dict[str, Any]) -> ControlSpec:
    rb = spec.get("readback_register")
    readback = (
        ReadbackRegister(
            address=rb["address"],
            offset=rb.get("offset", 0),
            format=rb["format"],
            fc=rb.get("fc", 3),
        )
        if rb
        else None
    )
    return ControlSpec(
        logical=logical,
        fc=spec["fc"],
        address=spec["address"],
        format=spec["format"],
        allowed_values=spec.get("allowed_values"),
        readback_register=readback,
        readback_delay_ms=spec.get("readback_delay_ms", 500),
    )
