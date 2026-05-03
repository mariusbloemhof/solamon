"""Logical metric catalog.

Spec: docs/specs/device-library/logical-metric-catalog.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DataType = Literal["float", "int", "bool", "enum", "bitfield", "datetime", "string"]
Category = Literal[
    "power", "energy", "voltage", "current", "power_factor",
    "frequency", "demand", "quality", "configuration", "control", "derived",
]


@dataclass(frozen=True)
class LogicalMetric:
    key: str
    label: str
    unit: str
    data_type: DataType
    category: Category
    is_cumulative: bool
    expected_range: tuple[float, float]
    monotonic: bool | None = None
    direction_convention: str | None = None
    is_writable: bool = False
    allowed_values: list[Any] | None = None
    enum_values: dict[int, str] | None = None


@dataclass(frozen=True)
class Catalog:
    schema_version: str
    metrics: dict[str, LogicalMetric] = field(default_factory=dict)

    def get(self, key: str) -> LogicalMetric | None:
        return self.metrics.get(key)

    def all(self) -> list[LogicalMetric]:
        return list(self.metrics.values())

    @classmethod
    def from_dict(cls, raw: dict[str, Any], schema_version: str = "1.0") -> Catalog:
        # v1.1+: { schema_version: "...", metrics: {...} }; v1.0: flat metric map.
        if "schema_version" in raw and "metrics" in raw:
            schema_version = raw["schema_version"]
            metric_map = raw["metrics"]
        else:
            metric_map = raw
        metrics = {
            key: LogicalMetric(
                key=key,
                label=entry["label"],
                unit=entry["unit"],
                data_type=entry["data_type"],
                category=entry["category"],
                is_cumulative=entry["is_cumulative"],
                expected_range=tuple(entry["expected_range"]),
                monotonic=entry.get("monotonic"),
                direction_convention=entry.get("direction_convention"),
                is_writable=entry.get("is_writable", False),
                allowed_values=entry.get("allowed_values"),
                enum_values=entry.get("enum_values"),
            )
            for key, entry in metric_map.items()
        }
        return cls(schema_version=schema_version, metrics=metrics)
