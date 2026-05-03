# Device Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Python `profile_loader` package that turns committed YAML catalog + profile files into typed, validated, decode-capable objects consumed by the edge agent, cloud ingestion, and probe CLI.

**Architecture:** Pure-Python package at `packages/profile_loader/src/profile_loader/`. Three immutable dataclass layers (`Catalog`, `Profile`, `Reading`) loaded from YAML and validated against committed JSON Schemas. A registry pattern for vendor-specific format decoders keeps the schema enum stable as new device families come online. Fingerprint matching is async and depends on a `ModbusClient` Protocol — never on `pymodbus` directly.

**Tech Stack:** Python 3.12, PyYAML, jsonschema, pytest, pytest-asyncio.

**Linear:** SOL-20.

**Conventions:** [`2026-05-03-conventions.md`](2026-05-03-conventions.md) — TDD strict, SOLID, monorepo structure, CI per spec group. Read it first.

**Spec source of truth:**
- [`docs/specs/device-library/README.md`](../../specs/device-library/README.md)
- [`docs/specs/device-library/profile-schema.md`](../../specs/device-library/profile-schema.md)
- [`docs/specs/device-library/logical-metric-catalog.md`](../../specs/device-library/logical-metric-catalog.md)
- [`docs/specs/device-library/acuvim-l-profile.md`](../../specs/device-library/acuvim-l-profile.md)

**What already exists (do NOT recreate):**
- `architecture/logical_metrics.yaml` (~60 metrics)
- `architecture/logical_metrics.schema.json`
- `architecture/profiles/profile.schema.json`
- `architecture/profiles/acuvim_l.yaml`

The plan validates these conform to their schemas, then builds the loader.

---

## File structure

```
solamon/
├── pyproject.toml                                # workspace dev-tool config (created Task 1)
├── packages/
│   └── profile_loader/
│       ├── pyproject.toml                        # package metadata + deps
│       ├── src/profile_loader/
│       │   ├── __init__.py                       # re-exports public API
│       │   ├── types.py                          # Reading, FingerprintResult, errors
│       │   ├── catalog.py                        # LogicalMetric, Catalog
│       │   ├── profile.py                        # Profile + nested dataclasses + decode + validate_control + fingerprint_match
│       │   ├── decoders.py                       # built-in decoders + CustomDecoder Protocol + AcuvimClockDecoder
│       │   ├── loader.py                         # ProfileLoader: load_catalog, load_profile, register_decoder
│       │   ├── fingerprint.py                    # ModbusClient Protocol + evaluate_read / evaluate_identifier
│       │   └── __main__.py                       # `python -m profile_loader validate <profile>`
│       └── tests/
│           ├── conftest.py
│           ├── test_committed_schemas.py         # validates the existing architecture/*.yaml files
│           ├── test_catalog.py
│           ├── test_profile_load.py
│           ├── test_loader.py
│           ├── test_decoders.py
│           ├── test_profile_decode.py
│           ├── test_custom_decoders.py
│           ├── test_validate_control.py
│           ├── test_fingerprint.py
│           └── test_cli.py
└── .github/workflows/device-library.yml
```

One file per responsibility (S in SOLID): `types.py` value objects, `catalog.py` / `profile.py` pure data + parse-from-yaml, `decoders.py` pure functions, `loader.py` orchestration, `fingerprint.py` the Modbus boundary Protocol, `__main__.py` CLI wrapper.

---

## Task 1: Workspace + package skeleton

**Files:**
- Create: `pyproject.toml` (workspace root — dev tool config only)
- Create: `packages/profile_loader/pyproject.toml`
- Create: `packages/profile_loader/src/profile_loader/__init__.py`
- Create: `packages/profile_loader/tests/__init__.py`
- Create: `packages/profile_loader/tests/test_smoke.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing import test**

```python
# packages/profile_loader/tests/test_smoke.py
def test_can_import_profile_loader():
    import profile_loader
    assert profile_loader.__name__ == "profile_loader"
```

- [ ] **Step 2: Run the test**

```bash
python -m pytest packages/profile_loader/tests/test_smoke.py -v
```
Expected: `ModuleNotFoundError: No module named 'profile_loader'`.

- [ ] **Step 3: Create workspace-root `pyproject.toml`**

```toml
# pyproject.toml (repo root)
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["packages/profile_loader/src", "packages/edge_agent/src", "packages/cloud_app/src", "packages/probe_cli/src"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "RUF"]
ignore = ["E501"]                 # line-length governed by ruff format

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]             # allow `assert False` in tests

[tool.pytest.ini_options]
testpaths = ["packages"]
asyncio_mode = "auto"
```

- [ ] **Step 4: Create the profile_loader package `pyproject.toml`**

```toml
# packages/profile_loader/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "solamon-profile-loader"
version = "0.0.0"
description = "Solamon profile loader — shared Python lib for catalog + profile parsing/decoding"
requires-python = ">=3.12"
dependencies = [
    "pyyaml>=6.0",
    "jsonschema>=4.21",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[project.scripts]
solamon-profile-validate = "profile_loader.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 5: Create the empty package + test init files**

```bash
mkdir -p packages/profile_loader/src/profile_loader
mkdir -p packages/profile_loader/tests
```

```python
# packages/profile_loader/src/profile_loader/__init__.py
"""Solamon profile loader: parses logical-metric catalogs and device profiles
shared between the edge agent, cloud ingestion, and probe CLI.

See docs/specs/device-library/ for the contracts.
"""
```

```python
# packages/profile_loader/tests/__init__.py
```
(empty file — just exists so pytest collects the directory)

- [ ] **Step 6: Add Python build artifacts to `.gitignore`**

Append to existing `.gitignore`:
```
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
*.egg-info/
.venv/
```

- [ ] **Step 7: Install + run the smoke test**

```bash
python -m pip install -e "packages/profile_loader[dev]"
python -m pytest packages/profile_loader/tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml packages/profile_loader/ .gitignore
git commit -m "feat(device-library): scaffold profile_loader package + workspace pyproject"
```

---

## Task 2: Validate committed YAML against committed JSON Schemas

The cheapest possible check that protects every downstream consumer from schema drift.

**Files:**
- Create: `packages/profile_loader/tests/test_committed_schemas.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_committed_schemas.py
"""Validate the committed architecture/*.yaml files against their JSON Schemas.

If these tests fail, the YAML and schema have drifted and NO downstream code
(edge agent, cloud, probe) will work correctly.
"""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _validate(raw: dict, schema_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema)
    return [
        f"{list(e.absolute_path)}: {e.message}"
        for e in sorted(validator.iter_errors(raw), key=lambda e: list(e.absolute_path))
    ]


def test_logical_metrics_yaml_conforms_to_schema():
    errors = _validate(_load_yaml(ARCH / "logical_metrics.yaml"), ARCH / "logical_metrics.schema.json")
    assert errors == [], "\n".join(errors)


def test_acuvim_l_profile_conforms_to_schema():
    errors = _validate(_load_yaml(ARCH / "profiles" / "acuvim_l.yaml"), ARCH / "profiles" / "profile.schema.json")
    assert errors == [], "\n".join(errors)


def test_logical_metrics_yaml_loads_as_dict():
    catalog = _load_yaml(ARCH / "logical_metrics.yaml")
    assert isinstance(catalog, dict)
    # v1.1+ shape: top-level wrapper with `metrics` key.
    assert "active_power_total" in catalog["metrics"]
```

- [ ] **Step 2: Run the tests**

```bash
python -m pytest packages/profile_loader/tests/test_committed_schemas.py -v
```
Expected: 3 passed. If any fail, **STOP** — do not "fix" the test. The committed YAML or schema has drifted; raise it on the spec side first.

- [ ] **Step 3: Commit**

```bash
git add packages/profile_loader/tests/test_committed_schemas.py
git commit -m "test(device-library): validate committed YAML against committed JSON Schemas"
```

---

## Task 3: `LogicalMetric` + `Catalog` dataclasses

**Files:**
- Create: `packages/profile_loader/src/profile_loader/types.py`
- Create: `packages/profile_loader/src/profile_loader/catalog.py`
- Create: `packages/profile_loader/tests/test_catalog.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_catalog.py
import yaml

from profile_loader.catalog import Catalog, LogicalMetric


SAMPLE = """
active_power_total:
  label: "Total active power"
  unit: kW
  data_type: float
  category: power
  is_cumulative: false
  direction_convention: "positive = consumption"
  expected_range: [-2000, 2000]

demand_window_minutes:
  label: "Demand integration window"
  unit: min
  data_type: int
  category: configuration
  is_cumulative: false
  expected_range: [1, 60]
  is_writable: true
  allowed_values: [1, 5, 10, 15, 30]
"""


def test_catalog_from_dict_parses_metrics():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    apt = catalog.get("active_power_total")
    assert isinstance(apt, LogicalMetric)
    assert apt.unit == "kW"
    assert apt.data_type == "float"
    assert apt.is_writable is False
    dwm = catalog.get("demand_window_minutes")
    assert dwm.is_writable is True
    assert dwm.allowed_values == [1, 5, 10, 15, 30]


def test_catalog_get_returns_none_for_unknown_metric():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    assert catalog.get("not_a_metric") is None


def test_catalog_all_returns_every_metric():
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    assert {m.key for m in catalog.all()} == {"active_power_total", "demand_window_minutes"}


def test_logical_metric_is_frozen():
    """SOLID: value objects are immutable."""
    import pytest
    catalog = Catalog.from_dict(yaml.safe_load(SAMPLE))
    apt = catalog.get("active_power_total")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        apt.unit = "MW"
```

- [ ] **Step 2: Run the tests** — fails with ModuleNotFoundError.

```bash
python -m pytest packages/profile_loader/tests/test_catalog.py -v
```

- [ ] **Step 3: Implement `types.py` (errors + Reading + FingerprintResult)**

```python
# packages/profile_loader/src/profile_loader/types.py
"""Shared value-object and exception types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class ValidationError(Exception):
    """Raised when input fails validation. Message is operator-readable."""


class DecodeError(Exception):
    """Raised when a Modbus response can't be decoded according to the profile."""


class ProfileLoadError(Exception):
    """Raised when a profile YAML can't be parsed or fails cross-validation against the catalog."""


@dataclass(frozen=True)
class Reading:
    value: Any
    raw_value: int | None
    quality: Literal["good", "uncertain", "bad"]


@dataclass(frozen=True)
class FingerprintResult:
    match: bool
    confidence: Literal["positive", "negative_fingerprint", "none"]
    identifiers: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Implement `catalog.py`**

```python
# packages/profile_loader/src/profile_loader/catalog.py
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
    expected_range: tuple[float, float] | None = None     # absent for datetime/enum metrics
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
                expected_range=tuple(entry["expected_range"]) if "expected_range" in entry else None,
                monotonic=entry.get("monotonic"),
                direction_convention=entry.get("direction_convention"),
                is_writable=entry.get("is_writable", False),
                allowed_values=entry.get("allowed_values"),
                enum_values=entry.get("enum_values"),
            )
            for key, entry in metric_map.items()
        }
        return cls(schema_version=schema_version, metrics=metrics)
```

- [ ] **Step 5: Run the catalog test**

```bash
python -m pytest packages/profile_loader/tests/test_catalog.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/profile_loader/src/profile_loader/types.py packages/profile_loader/src/profile_loader/catalog.py packages/profile_loader/tests/test_catalog.py
git commit -m "feat(device-library): LogicalMetric + Catalog dataclasses"
```

---

## Task 4: `Profile` + nested dataclasses

**Files:**
- Create: `packages/profile_loader/src/profile_loader/profile.py`
- Create: `packages/profile_loader/tests/test_profile_load.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_profile_load.py
from pathlib import Path

import yaml

from profile_loader.profile import (
    ConnectionInfo, DeviceInfo, MetricMap, Profile, ReadBlock,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ACUVIM_L_PATH = REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml"


def _acuvim_l_dict() -> dict:
    with ACUVIM_L_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_profile_from_dict_parses_device_info():
    profile = Profile.from_dict(_acuvim_l_dict())
    assert isinstance(profile.device, DeviceInfo)
    assert profile.device.manufacturer == "AccuEnergy"
    assert profile.device.model == "Acuvim L"
    assert profile.device.category == "meter"


def test_profile_from_dict_parses_connection():
    profile = Profile.from_dict(_acuvim_l_dict())
    assert isinstance(profile.connection, ConnectionInfo)
    assert profile.connection.protocol == "modbus_tcp"
    assert profile.connection.default_port == 502


def test_profile_from_dict_parses_read_blocks():
    profile = Profile.from_dict(_acuvim_l_dict())
    realtime = next((b for b in profile.read_blocks if b.name == "realtime"), None)
    assert realtime is not None
    assert isinstance(realtime, ReadBlock)
    assert realtime.fc == 3
    assert realtime.cadence_s > 0
    assert realtime.length > 0
    assert all(isinstance(m, MetricMap) for m in realtime.metrics)


def test_profile_schedule_yields_blocks():
    profile = Profile.from_dict(_acuvim_l_dict())
    scheduled = list(profile.schedule())
    assert len(scheduled) == len(profile.read_blocks)
    for block, cadence in scheduled:
        assert isinstance(block, ReadBlock)
        assert cadence == block.cadence_s
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Implement `profile.py`** (without `decode` / `validate_control` / `fingerprint_match` — those land in later tasks)

```python
# packages/profile_loader/src/profile_loader/profile.py
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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest packages/profile_loader/tests/test_profile_load.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/profile_loader/src/profile_loader/profile.py packages/profile_loader/tests/test_profile_load.py
git commit -m "feat(device-library): Profile dataclasses + from_dict + schedule"
```

---

## Task 5: `ProfileLoader` orchestration + cross-validation

**Files:**
- Create: `packages/profile_loader/src/profile_loader/loader.py`
- Create: `packages/profile_loader/src/profile_loader/decoders.py` (skeleton — built-in decoders land in Task 6)
- Modify: `packages/profile_loader/src/profile_loader/__init__.py`
- Create: `packages/profile_loader/tests/test_loader.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_loader.py
from pathlib import Path

import pytest

from profile_loader import ProfileLoader, ProfileLoadError

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"
CATALOG_PATH = ARCH / "logical_metrics.yaml"
ACUVIM_L_PATH = ARCH / "profiles" / "acuvim_l.yaml"


def test_load_catalog_returns_catalog_with_metrics():
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    assert catalog.get("active_power_total") is not None
    assert len(catalog.all()) > 30


def test_load_profile_returns_validated_profile():
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    profile = loader.load_profile(ACUVIM_L_PATH, catalog)
    assert profile.device.manufacturer == "AccuEnergy"
    assert len(profile.read_blocks) > 0


def test_load_profile_rejects_unknown_logical_metric(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint: { reads: [] }
read_blocks:
  - name: badblock
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: this_metric_does_not_exist, offset: 0, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="this_metric_does_not_exist"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_offset_outside_block(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint: { reads: [] }
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: frequency_hz, offset: 12, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="exceeds block length"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_misaligned_offset(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint: { reads: [] }
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 4
    cadence_s: 10
    metrics:
      - { logical: frequency_hz, offset: 1, format: float32_be }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="alignment"):
        loader.load_profile(bad, catalog)


def test_load_profile_rejects_custom_format_without_registered_decoder(tmp_path: Path):
    loader = ProfileLoader()
    catalog = loader.load_catalog(CATALOG_PATH)
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
device: { manufacturer: Test, model: TestUnit, category: meter }
connection: { protocol: modbus_tcp, default_port: 502, default_unit_id: 1 }
fingerprint: { reads: [] }
read_blocks:
  - name: realtime
    fc: 3
    address: 0
    length: 8
    cadence_s: 10
    metrics:
      - { logical: meter_clock, offset: 0, format: custom, decoder: not_registered, length: 7 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="not_registered"):
        loader.load_profile(bad, catalog)
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Implement `decoders.py` skeleton**

```python
# packages/profile_loader/src/profile_loader/decoders.py
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
    return {}
```

- [ ] **Step 4: Implement `loader.py`**

```python
# packages/profile_loader/src/profile_loader/loader.py
"""Top-level loader: parse + validate catalog and profiles.

Spec: docs/specs/device-library/profile-schema.md §7-8
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .catalog import Catalog
from .profile import Profile
from .types import ProfileLoadError

# Locate the architecture/ tree relative to this file.
# packages/profile_loader/src/profile_loader/loader.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = {
    "catalog": REPO_ROOT / "architecture" / "logical_metrics.schema.json",
    "profile": REPO_ROOT / "architecture" / "profiles" / "profile.schema.json",
}

FORMAT_BYTES: dict[str, int] = {
    "float32_be": 4, "float32_le": 4, "float32_mb": 4,
    "uint16": 2, "int16": 2, "word": 2,
    "uint32_be": 4, "int32_be": 4, "dword_high_first": 4,
    "ascii": 0, "custom": 0,
}

FORMAT_ALIGN: dict[str, int] = {
    "float32_be": 4, "float32_le": 4, "float32_mb": 4,
    "uint32_be": 4, "int32_be": 4, "dword_high_first": 4,
    "uint16": 2, "int16": 2, "word": 2,
    "ascii": 1, "custom": 1,
}


class ProfileLoader:
    """Loads + validates profile YAMLs and the logical-metric catalog."""

    def __init__(self) -> None:
        from .decoders import default_registry
        self._decoders = default_registry()

    def register_decoder(self, name: str, decoder: Any) -> None:
        self._decoders[name] = decoder

    @property
    def decoders(self) -> dict[str, Any]:
        return self._decoders

    def load_catalog(self, path: str | Path) -> Catalog:
        path = Path(path)
        raw = _load_yaml(path)
        _validate_jsonschema(raw, SCHEMAS["catalog"], path)
        return Catalog.from_dict(raw)

    def load_profile(self, path: str | Path, catalog: Catalog) -> Profile:
        path = Path(path)
        raw = _load_yaml(path)
        _validate_jsonschema(raw, SCHEMAS["profile"], path)
        profile = Profile.from_dict(raw)
        self._cross_validate(profile, catalog, path)
        return profile

    def _cross_validate(self, profile: Profile, catalog: Catalog, path: Path) -> None:
        for block in profile.read_blocks:
            block_byte_length = block.length * 2
            for metric in block.metrics:
                if catalog.get(metric.logical) is None:
                    raise ProfileLoadError(
                        f"{path}: read_block '{block.name}': metric '{metric.logical}' not in catalog"
                    )
                if metric.format not in FORMAT_BYTES:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': unknown format '{metric.format}'"
                    )
                align = FORMAT_ALIGN[metric.format]
                if metric.offset % align != 0:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': offset {metric.offset} "
                        f"violates {align}-byte alignment for format '{metric.format}'"
                    )
                if metric.format == "ascii":
                    if metric.length is None:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': format 'ascii' requires 'length'"
                        )
                    end = metric.offset + (metric.length * 2)
                elif metric.format == "custom":
                    end = metric.offset + ((metric.length or 1) * 2)
                else:
                    end = metric.offset + FORMAT_BYTES[metric.format]
                if end > block_byte_length:
                    raise ProfileLoadError(
                        f"{path}: metric '{metric.logical}': bytes {metric.offset}-{end} "
                        f"exceeds block length {block_byte_length} bytes"
                    )
                if metric.format == "custom":
                    if metric.decoder is None:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': format 'custom' requires 'decoder'"
                        )
                    if metric.decoder not in self._decoders:
                        raise ProfileLoadError(
                            f"{path}: metric '{metric.logical}': decoder '{metric.decoder}' not registered"
                        )

        for control_key in profile.control:
            cm = catalog.get(control_key)
            if cm is None:
                raise ProfileLoadError(f"{path}: control '{control_key}' not in catalog")
            if not cm.is_writable:
                raise ProfileLoadError(f"{path}: control '{control_key}' not marked is_writable")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ProfileLoadError(f"file not found: {path}")
    with path.open(encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ProfileLoadError(f"{path}: YAML parse error: {e}") from e


def _validate_jsonschema(raw: dict, schema_path: Path, source_path: Path) -> None:
    with schema_path.open(encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise ProfileLoadError(f"{source_path}: schema violations: {msgs}")
```

- [ ] **Step 5: Update `__init__.py` to export the public API**

```python
# packages/profile_loader/src/profile_loader/__init__.py
"""Solamon profile loader."""
from .catalog import Catalog, LogicalMetric
from .loader import ProfileLoader
from .profile import (
    ConnectionInfo, ControlSpec, DeviceInfo, Fingerprint, FingerprintIdentifier,
    FingerprintRead, MetricMap, Profile, ReadbackRegister, ReadBlock,
)
from .types import (
    DecodeError, FingerprintResult, ProfileLoadError, Reading, ValidationError,
)

__all__ = [
    "Catalog", "ConnectionInfo", "ControlSpec", "DecodeError", "DeviceInfo",
    "Fingerprint", "FingerprintIdentifier", "FingerprintRead", "FingerprintResult",
    "LogicalMetric", "MetricMap", "Profile", "ProfileLoadError", "ProfileLoader",
    "ReadBlock", "ReadbackRegister", "Reading", "ValidationError",
]
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest packages/profile_loader/tests/test_loader.py -v
```
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add packages/profile_loader/src/profile_loader/ packages/profile_loader/tests/test_loader.py
git commit -m "feat(device-library): ProfileLoader with schema + cross-validation"
```

---

## Task 6: Built-in format decoders

**Files:**
- Modify: `packages/profile_loader/src/profile_loader/decoders.py`
- Create: `packages/profile_loader/tests/test_decoders.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_decoders.py
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
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Replace `decoders.py` with full built-in set**

```python
# packages/profile_loader/src/profile_loader/decoders.py
"""Format decoders.

Spec: docs/specs/device-library/profile-schema.md §6
"""
from __future__ import annotations

import struct
from typing import Any, Callable, Protocol


class CustomDecoder(Protocol):
    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any: ...


_BuiltinFn = Callable[[bytes, int, int | None], Any]


def _f32_be(b: bytes, o: int, _: int | None) -> float: return struct.unpack_from(">f", b, o)[0]
def _f32_le(b: bytes, o: int, _: int | None) -> float: return struct.unpack_from("<f", b, o)[0]


def _f32_mb(buf: bytes, off: int, _: int | None) -> float:
    a, b, c, d = buf[off:off + 4]
    return struct.unpack(">f", bytes([b, a, d, c]))[0]


def _u16(b: bytes, o: int, _: int | None) -> int: return struct.unpack_from(">H", b, o)[0]
def _i16(b: bytes, o: int, _: int | None) -> int: return struct.unpack_from(">h", b, o)[0]
def _u32_be(b: bytes, o: int, _: int | None) -> int: return struct.unpack_from(">I", b, o)[0]
def _i32_be(b: bytes, o: int, _: int | None) -> int: return struct.unpack_from(">i", b, o)[0]


def _dword_hf(buf: bytes, off: int, _: int | None) -> int:
    high, low = struct.unpack_from(">HH", buf, off)
    return (high << 16) | low


def _ascii(buf: bytes, off: int, length_bytes: int | None) -> str:
    if length_bytes is None:
        raise ValueError("ascii decode requires length_bytes")
    raw = buf[off:off + length_bytes]
    return raw.rstrip(b"\x00 ").decode("ascii", errors="replace")


_BUILTIN: dict[str, _BuiltinFn] = {
    "float32_be":       _f32_be,
    "float32_le":       _f32_le,
    "float32_mb":       _f32_mb,
    "uint16":           _u16,
    "int16":            _i16,
    "word":             _u16,
    "uint32_be":        _u32_be,
    "int32_be":         _i32_be,
    "dword_high_first": _dword_hf,
    "ascii":            _ascii,
}


def decode_format(format: str, buffer: bytes, offset: int, length_bytes: int | None = None) -> Any:
    """Decode a single value from `buffer` at `offset` using `format`."""
    if format not in _BUILTIN:
        raise KeyError(f"unknown format: {format}")
    return _BUILTIN[format](buffer, offset, length_bytes)


def default_registry() -> dict[str, CustomDecoder]:
    """Return a fresh registry seeded with built-in custom decoders.

    Task 8 adds AcuvimClockDecoder.
    """
    return {}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest packages/profile_loader/tests/test_decoders.py packages/profile_loader/tests/test_loader.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add packages/profile_loader/src/profile_loader/decoders.py packages/profile_loader/tests/test_decoders.py
git commit -m "feat(device-library): built-in format decoders (float32/uint/int/dword/ascii)"
```

---

## Task 7: `Profile.decode(block_name, response, catalog, decoders)`

**Files:**
- Modify: `packages/profile_loader/src/profile_loader/profile.py` (add `decode` method)
- Create: `packages/profile_loader/tests/conftest.py` (shared fixtures)
- Create: `packages/profile_loader/tests/test_profile_decode.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/conftest.py
"""Shared fixtures."""
from pathlib import Path

import pytest

from profile_loader import ProfileLoader

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCH = REPO_ROOT / "architecture"


class _StubClockDecoder:
    """Stub for tests that don't exercise the real clock decoder."""
    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> str:
        return "1970-01-01T00:00:00Z"


@pytest.fixture
def loader_with_stub_clock():
    loader = ProfileLoader()
    loader.register_decoder("acuvim_clock", _StubClockDecoder())
    return loader


@pytest.fixture
def loaded_acuvim_l(loader_with_stub_clock):
    catalog = loader_with_stub_clock.load_catalog(ARCH / "logical_metrics.yaml")
    profile = loader_with_stub_clock.load_profile(ARCH / "profiles" / "acuvim_l.yaml", catalog)
    return catalog, profile, loader_with_stub_clock.decoders
```

```python
# packages/profile_loader/tests/test_profile_decode.py
import struct

import pytest

from profile_loader import DecodeError


def test_decode_returns_kw_after_scale_applied(loaded_acuvim_l):
    catalog, profile, decoders = loaded_acuvim_l
    realtime = next(b for b in profile.read_blocks if b.name == "realtime")
    payload = bytearray(realtime.length * 2)
    p = next(m for m in realtime.metrics if m.logical == "active_power_total")
    struct.pack_into(">f", payload, p.offset, 12350.0)   # 12350 W → expect 12.35 kW
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
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Add `decode` method to `Profile`** in `profile.py`

Add these imports near the top:
```python
from .types import DecodeError, Reading, ValidationError
```

Inside the `Profile` dataclass, after `schedule()`, add:

```python
    def decode(
        self,
        block_name: str,
        response: bytes,
        catalog: Any | None = None,         # Catalog; avoid circular import here
        decoders: dict[str, Any] | None = None,
    ) -> dict[str, Reading]:
        """Decode an FC03/FC04 response into a dict keyed by logical metric name.

        Pure function over the inputs; side-effect-free.
        """
        from .decoders import decode_format

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
                value = raw_value * metric.scale if isinstance(raw_value, (int, float)) else raw_value
                raw = raw_value if isinstance(raw_value, int) else None
            quality = "good"
            if catalog is not None:
                cm = catalog.get(metric.logical)
                if cm is not None and isinstance(value, (int, float)):
                    lo, hi = cm.expected_range
                    if value < lo or value > hi:
                        quality = "uncertain"
            result[metric.logical] = Reading(value=value, raw_value=raw, quality=quality)
        return result
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest packages/profile_loader/tests/test_profile_decode.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/profile_loader/src/profile_loader/profile.py packages/profile_loader/tests/conftest.py packages/profile_loader/tests/test_profile_decode.py
git commit -m "feat(device-library): Profile.decode with scale + quality + custom decoder dispatch"
```

---

## Task 8: `AcuvimClockDecoder`

**Files:**
- Modify: `packages/profile_loader/src/profile_loader/decoders.py`
- Create: `packages/profile_loader/tests/test_custom_decoders.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_custom_decoders.py
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
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Append to `decoders.py`**

```python
# Append at the bottom of decoders.py:

from datetime import datetime, timezone


class AcuvimClockDecoder:
    """Decode Acuvim's 7-register clock block (Y/M/D/H/M/S/DoW) → ISO 8601."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> str:
        if length_bytes < 14:
            raise ValueError(f"acuvim_clock requires 14 bytes, got {length_bytes}")
        y, mo, d, h, mi, s, _dow = struct.unpack_from(">7H", buffer, offset)
        try:
            dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
        except ValueError as e:
            raise ValueError(f"acuvim_clock decode: {e}") from e
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
```

Update `default_registry()`:
```python
def default_registry() -> dict[str, CustomDecoder]:
    return {"acuvim_clock": AcuvimClockDecoder()}
```

- [ ] **Step 4: Run tests + full suite**

```bash
python -m pytest packages/profile_loader/tests -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add packages/profile_loader/src/profile_loader/decoders.py packages/profile_loader/tests/test_custom_decoders.py
git commit -m "feat(device-library): AcuvimClockDecoder for meter_clock metric"
```

---

## Task 9: `Profile.validate_control`

**Files:**
- Modify: `packages/profile_loader/src/profile_loader/profile.py`
- Create: `packages/profile_loader/tests/test_validate_control.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_validate_control.py
import pytest

from profile_loader import ValidationError


def test_validate_control_passes_for_allowed_value(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    profile.validate_control("demand_window_minutes", 30, catalog=catalog)
    profile.validate_control("demand_window_minutes", 1, catalog=catalog)


def test_validate_control_rejects_disallowed_value(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="not in allowed"):
        profile.validate_control("demand_window_minutes", 99, catalog=catalog)


def test_validate_control_rejects_unknown_metric(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="unknown"):
        profile.validate_control("not_a_metric", 1, catalog=catalog)


def test_validate_control_rejects_non_writable_metric(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    with pytest.raises(ValidationError, match="not writable"):
        profile.validate_control("active_power_total", 12.5, catalog=catalog)


def test_validate_control_rejects_metric_not_in_profile_control_block(loaded_acuvim_l):
    catalog, profile, _ = loaded_acuvim_l
    writable = [m.key for m in catalog.all() if m.is_writable]
    not_in_profile = [w for w in writable if w not in profile.control]
    if not_in_profile:
        with pytest.raises(ValidationError, match="not exposed"):
            profile.validate_control(not_in_profile[0], 1, catalog=catalog)
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Add `validate_control` to `Profile`** (in `profile.py`, after `decode`)

```python
    def validate_control(self, logical_metric: str, value: Any, catalog: Any) -> None:
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
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest packages/profile_loader/tests/test_validate_control.py -v
git add packages/profile_loader/src/profile_loader/profile.py packages/profile_loader/tests/test_validate_control.py
git commit -m "feat(device-library): Profile.validate_control with catalog cross-check"
```

---

## Task 10: `Profile.fingerprint_match` (async + Protocol-driven)

**Files:**
- Create: `packages/profile_loader/src/profile_loader/fingerprint.py`
- Modify: `packages/profile_loader/src/profile_loader/profile.py`
- Create: `packages/profile_loader/tests/test_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/profile_loader/tests/test_fingerprint.py
"""Fingerprint matching against a fake Modbus client (Protocol-based)."""
from typing import Any

import pytest


class FakeResponse:
    def __init__(self, registers: list[int] | None = None, exception_code: int | None = None):
        self.registers = registers or []
        self._exc = exception_code

    def isError(self) -> bool: return self._exc is not None

    @property
    def exception_code(self) -> int | None: return self._exc


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
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Create `fingerprint.py`**

```python
# packages/profile_loader/src/profile_loader/fingerprint.py
"""Fingerprint matching: ModbusClient Protocol + per-read evaluators.

Spec: docs/specs/device-library/profile-schema.md §4
"""
from __future__ import annotations

from typing import Any, Protocol

from .decoders import decode_format
from .profile import FingerprintIdentifier, FingerprintRead


class ModbusClient(Protocol):
    """Minimal contract: matches pymodbus.AsyncModbusTcpClient surface we use.

    SOLID-I (interface segregation): only the methods we actually call.
    """
    async def read_holding_registers(self, address: int, count: int, slave: int = ...) -> Any: ...
    async def read_input_registers(self, address: int, count: int, slave: int = ...) -> Any: ...


async def _do_read(client: ModbusClient, address: int, count: int, fc: int, unit_id: int) -> Any:
    if fc == 3:
        return await client.read_holding_registers(address, count, slave=unit_id)
    if fc == 4:
        return await client.read_input_registers(address, count, slave=unit_id)
    raise ValueError(f"unsupported fingerprint fc: {fc}")


def _registers_to_bytes(registers: list[int]) -> bytes:
    out = bytearray()
    for r in registers:
        out.extend(int(r).to_bytes(2, "big", signed=False))
    return bytes(out)


async def evaluate_read(
    client: ModbusClient, read: FingerprintRead, unit_id: int,
) -> tuple[bool, str | None, Any]:
    """Run one fingerprint read. Returns (matched, failure_or_none, decoded_value)."""
    response = await _do_read(client, read.address, read.length, read.fc, unit_id)
    is_error = bool(getattr(response, "isError", lambda: False)())

    if read.expect_exception is not None:
        if not is_error:
            return False, "expected_exception not raised", None
        actual = getattr(response, "exception_code", None)
        if actual != read.expect_exception:
            return False, f"expected_exception {read.expect_exception:#x} got {actual!r}", None
        return True, None, None

    if is_error:
        return False, f"unexpected modbus exception {getattr(response, 'exception_code', None)!r}", None

    if read.format is None:
        return True, None, None

    buf = _registers_to_bytes(getattr(response, "registers", []))
    length_bytes = read.length * 2 if read.format == "ascii" else None
    value = decode_format(read.format, buf, 0, length_bytes)

    if read.expected is not None and value != read.expected:
        return False, f"expected {read.expected!r}, got {value!r}", value
    if read.expected_range is not None:
        lo, hi = read.expected_range
        if not (lo <= value <= hi):
            return False, f"value {value!r} outside range [{lo}, {hi}]", value
    if read.expected_contains is not None and isinstance(value, str):
        if read.expected_contains not in value:
            return False, f"value {value!r} does not contain {read.expected_contains!r}", value
    return True, None, value


async def evaluate_identifier(
    client: ModbusClient, ident: FingerprintIdentifier, unit_id: int,
) -> tuple[str, Any] | None:
    """Read one identifier. Returns (logical, value) on success, None on warning."""
    try:
        response = await _do_read(client, ident.address, ident.length, ident.fc, unit_id)
        if bool(getattr(response, "isError", lambda: False)()):
            return None
        buf = _registers_to_bytes(getattr(response, "registers", []))
        length_bytes = ident.length * 2 if ident.format == "ascii" else None
        value = decode_format(ident.format, buf, 0, length_bytes)
        if ident.expected_contains and isinstance(value, str) and ident.expected_contains not in value:
            return None
        return (ident.logical, value)
    except Exception:
        return None
```

- [ ] **Step 4: Add `fingerprint_match` to `Profile`** (in `profile.py`)

```python
    async def fingerprint_match(self, client: Any, unit_id: int | None = None):
        from .fingerprint import evaluate_identifier, evaluate_read
        from .types import FingerprintResult

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
            "none" if not match
            else ("negative_fingerprint" if used_negative else "positive")
        )

        identifiers: dict[str, Any] = {}
        if match:
            for ident in self.fingerprint.identifiers:
                result = await evaluate_identifier(client, ident, slave_id)
                if result is not None:
                    identifiers[result[0]] = result[1]

        return FingerprintResult(match=match, confidence=confidence,
                                 identifiers=identifiers, failures=failures)
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest packages/profile_loader/tests/test_fingerprint.py -v
git add packages/profile_loader/src/profile_loader/fingerprint.py packages/profile_loader/src/profile_loader/profile.py packages/profile_loader/tests/test_fingerprint.py
git commit -m "feat(device-library): async fingerprint_match via ModbusClient Protocol"
```

---

## Task 11: CLI `solamon-profile-validate`

**Files:**
- Create: `packages/profile_loader/src/profile_loader/__main__.py`
- Create: `packages/profile_loader/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/profile_loader/tests/test_cli.py
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ACUVIM_L_PATH = REPO_ROOT / "architecture" / "profiles" / "acuvim_l.yaml"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "profile_loader", *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_validate_succeeds_on_committed_profile():
    result = _run("validate", str(ACUVIM_L_PATH))
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout
    assert "Acuvim L" in result.stdout


def test_validate_fails_on_broken_profile(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not a profile", encoding="utf-8")
    result = _run("validate", str(bad))
    assert result.returncode != 0
    assert result.stderr


def test_help_lists_validate_subcommand():
    result = _run("--help")
    assert result.returncode == 0
    assert "validate" in result.stdout
```

- [ ] **Step 2: Run** — fails.

- [ ] **Step 3: Implement `__main__.py`**

```python
# packages/profile_loader/src/profile_loader/__main__.py
"""CLI entry point: `python -m profile_loader validate <profile-path>`.

Exits:
  0 — profile loaded + validated
  1 — invalid arguments
  2 — schema or cross-validation failure
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import ProfileLoader
from .types import ProfileLoadError

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = REPO_ROOT / "architecture" / "logical_metrics.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solamon-profile-validate",
        description="Validate a Solamon device profile against the catalog + JSON Schema.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="Validate a single profile.")
    v.add_argument("profile", type=Path)
    v.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        loader = ProfileLoader()
        try:
            catalog = loader.load_catalog(args.catalog)
            profile = loader.load_profile(args.profile, catalog)
        except ProfileLoadError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        n_metrics = sum(len(b.metrics) for b in profile.read_blocks)
        print(f"OK: {profile.device.manufacturer} / {profile.device.model} ({profile.device.category})")
        print(f"   {len(profile.read_blocks)} read block(s); {n_metrics} metric(s) total")
        print(f"   {len(profile.control)} control register(s)")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests + manual sanity check**

```bash
python -m pytest packages/profile_loader/tests/test_cli.py -v
python -m profile_loader validate architecture/profiles/acuvim_l.yaml
solamon-profile-validate validate architecture/profiles/acuvim_l.yaml
```

- [ ] **Step 5: Commit**

```bash
git add packages/profile_loader/src/profile_loader/__main__.py packages/profile_loader/tests/test_cli.py
git commit -m "feat(device-library): solamon-profile-validate CLI"
```

---

## Task 12: GitHub Actions CI

**Files:**
- Create: `.github/workflows/device-library.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/device-library.yml
name: Device library

on:
  push:
    branches: [master]
    paths:
      - "packages/profile_loader/**"
      - "architecture/**"
      - "pyproject.toml"
      - ".github/workflows/device-library.yml"
  pull_request:
    paths:
      - "packages/profile_loader/**"
      - "architecture/**"
      - "pyproject.toml"

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - name: Install
        run: python -m pip install -e "packages/profile_loader[dev]"
      - name: Lint
        run: python -m ruff check packages/profile_loader
      - name: Tests
        run: python -m pytest packages/profile_loader/tests -v
      - name: Validate committed profile
        run: python -m profile_loader validate architecture/profiles/acuvim_l.yaml
```

- [ ] **Step 2: Sanity-check + lint locally + commit**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/device-library.yml'))"
python -m ruff check packages/profile_loader
git add .github/workflows/device-library.yml
git commit -m "ci(device-library): pytest + ruff + validate-CLI on PRs"
```

---

## Self-review

**Spec coverage** — every device-library acceptance line maps to a task:

| Spec line | Task |
|-----------|------|
| `architecture/logical_metrics.yaml` exists | Already exists; Task 2 verifies |
| `architecture/profiles/profile.schema.json` validates `acuvim_l.yaml` | Task 2 |
| Profile loader at shared module path | Task 5 |
| `ProfileLoader.load_catalog` / `load_profile` / `register_decoder` | Task 5 |
| `Profile.schedule` | Task 4 |
| `Profile.decode` with quality + scale | Task 7 |
| `Profile.fingerprint_match` (positive + negative + identifiers) | Task 10 |
| `Profile.validate_control` | Task 9 |
| 10 built-in format decoders | Task 6 |
| Custom decoder registry + AcuvimClockDecoder | Task 5 (skeleton) + Task 8 |
| `format: custom + decoder: <name>` registry pattern | Task 5 + Task 7 + Task 8 |
| Clear error messages naming offending file | Task 5 (cross-validation tests assert message content) |

**Placeholder scan** — none of "TBD", "implement later", "similar to Task N" appear.

**Type consistency** — `Catalog`, `Profile`, `Reading`, `FingerprintResult`, `ValidationError`, `DecodeError`, `ProfileLoadError` defined in Task 3, used consistently. `decode_format(format, buffer, offset, length_bytes=None)` signature stable across Tasks 6, 7, 8, 10.

---

## Acceptance verification

```bash
python -m ruff check packages/profile_loader
python -m pytest packages/profile_loader/tests -v
python -m profile_loader validate architecture/profiles/acuvim_l.yaml
solamon-profile-validate validate architecture/profiles/acuvim_l.yaml
```

All four must succeed.

---

## Out of scope (tracked separately)

Per [`2026-05-03-conventions.md` §7](2026-05-03-conventions.md): profile linting (SOL-14), auto-detection (SOL-11), per-site overrides (SOL-13), hot reload (SOL-17), schema versioning (SOL-15), Acuvim II profile, push-protocol profiles (SOL-22).
