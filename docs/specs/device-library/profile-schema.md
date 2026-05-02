# Device profile schema

**Spec group:** [device-library](README.md)
**Linear:** [SOL-20](https://linear.app/solamon/issue/SOL-20)
**Machine artifacts:**
- `architecture/profiles/profile.schema.json` — JSON Schema for validation
- `architecture/profiles/<variant>.yaml` — one file per device variant

The wire-level contract that maps a logical metric to a physical register on a specific device variant. One profile per variant. The edge agent, cloud ingestion, and probe CLI all consume profiles via the same loader contract.

---

## 1. Top-level shape

```yaml
schema_version: "1.0"

device:
  manufacturer: AccuEnergy
  model: Acuvim L
  category: meter            # meter | pv_inverter | bess_pcs | bess_hub | generator | ppc | gateway

connection:
  protocol: modbus_tcp       # modbus_tcp | modbus_rtu  (MVP — see scope note below)
  default_port: 502
  default_unit_id: 1

fingerprint:
  reads: [...]               # see §4
  identifiers: [...]         # see §4

read_blocks: [...]           # see §3 — telemetry

control: {...}               # see §5 — writable registers
```

Every profile MUST have `schema_version`, `device`, `connection`, `fingerprint`, and `read_blocks`. `control` is optional (for read-only devices) but expected on meters and PCSs.

> **MVP scope: Modbus profiles only.** The schema currently constrains `connection.protocol` to `modbus_tcp` or `modbus_rtu`. AXM-WEB2 MQTT-push profiles (the planned billing path for Acuvim) and HTTP-push profiles need a different shape — `read_blocks`/`fingerprint.reads` are FC03-shaped and don't apply. Adding push protocols is tracked in [SOL-22](https://linear.app/solamon/issue/SOL-22) as a discriminated schema extension; until then, this schema is the authoritative contract for what we ship.

## 2. `device` and `connection` blocks

`device.manufacturer` and `device.model` are free-text but conventionally match the vendor's official product label. `device.category` is an enum from the list above; consumers (e.g., the dashboard) use it for icon selection and capability inference (e.g., a `meter` is expected to have `active_power_total`; a `bess_pcs` is expected to have `state_of_charge_pct`).

`connection.default_port` and `default_unit_id` are advisory — the actual values are overridable per-site in the `Device` row, since multiple meters with different IPs and unit IDs may share a profile.

## 3. `read_blocks` — the telemetry pollset

A profile's `read_blocks` is a list of named, batched FC03 reads. Each block represents one Modbus transaction; metrics within the block are decoded by byte offset from the start of the response.

```yaml
read_blocks:
  - name: realtime
    fc: 3                     # function code: 3 (read holding) or 4 (read input)
    address: 0x0600           # starting register address
    length: 74                # number of registers to read in this batch
    cadence_s: 10             # poll interval in seconds; the storage cadence is the same
    metrics:
      - logical: frequency_hz
        offset: 0             # byte offset within the response payload
        format: float32_be    # one of the supported format types (§6)
        scale: 1.0            # optional; default 1.0; final value = raw × scale
        sign: signed          # optional; for integer formats; default depends on format
```

### 3.1 Block sizing rules

- **Maximum block length:** 125 registers (Modbus FC03 protocol limit).
- **Block addresses must be valid on the target device** — the profile loader does not check this; failure is detected at runtime as a Modbus exception 0x02 ("illegal data address"), which surfaces as a probe CLI verification failure ([SOL-18](https://linear.app/solamon/issue/SOL-18)).
- **Metrics with the same block** are read in a single FC03 transaction. Use this to batch related metrics that share a cadence (e.g., V/I/P/Q/S/PF together at 10 s).
- **Metrics in different blocks** become separate FC03 transactions. Use this to decouple cadences (e.g., energy at 60 s vs. realtime at 10 s).

### 3.2 Cadence semantics

- `cadence_s` is the **poll interval** — how often the agent issues the FC03 read.
- Each successful read produces one row per metric in the local SQLite buffer.
- The MQTT publisher emits **one MQTT message per block** (not per metric) — the message payload contains all metrics from that block decoded together. See [`docs/specs/cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md).
- `cadence_s` minimum 1 s. Cadences below 5 s should be reserved for fast-acting devices (PCS, generator state); meters at 5–60 s are typical.

### 3.3 Per-metric `offset` and `format`

`offset` is in **bytes** (not registers). One Modbus register = 2 bytes, big-endian word order in the response. So:

- A `float32_be` value spans 4 bytes (2 registers); offsets must be multiples of 4 for clean alignment.
- A `dword_high_first` value (Acuvim energy convention) spans 4 bytes (2 registers) read as one 32-bit unsigned, with the **high word in the lower address** (i.e., big-endian word order, big-endian byte order within each word).
- A `word` / `uint16` value is 2 bytes (1 register).

The profile loader validates that all metric offsets are within the block (`offset + bytes(format) <= length × 2`).

### 3.4 Aliasing & fallbacks

A profile MAY declare two metrics at the same offset only if exactly one is marked `aliased: true`. This handles the case where a metric has multiple legitimate names (e.g., `current_neutral` and `neutral_current`). The probe CLI emits a warning if it encounters non-aliased overlap.

## 4. `fingerprint` — device identification on connect

```yaml
fingerprint:
  reads:                       # ordered checks; ALL must pass to claim a match
    - address: 0xC350
      length: 2
      expect_exception: 0x02   # OR exact value match — see below

    - address: 0x0130
      length: 1
      format: uint16
      expected_range: [4500, 6500]   # frequency × 100, healthy SA range

  identifiers:                 # optional; when matched, captured as device metadata
    - logical: manufacturer
      address: 0xC354
      length: 16
      format: ascii
      expected_contains: "Accuenergy"
```

### 4.1 Match rule for `reads`

Each read entry must specify exactly one of:

- `expected: <value>` — the read must succeed AND return this exact value.
- `expected_range: [min, max]` — the read must succeed AND return a value in this range (inclusive).
- `expected_contains: "<substring>"` — the read must succeed AND the decoded ASCII contains this substring.
- `expect_exception: <code>` — the read must FAIL with this Modbus exception code. Exception codes per the Modbus spec: `0x01` illegal function, `0x02` illegal data address, `0x03` illegal data value, `0x04` slave device failure.

ALL entries in `reads` must match for the profile to claim the connected device.

### 4.2 `identifiers`

Read on connect AFTER fingerprint match succeeds. Captured into the cloud `Device` record. Useful for:
- Auditing what's actually deployed in the field
- Debugging mid-life firmware swaps
- Driving display fields (e.g., "Firmware 3.21" on the Site setup card)

Each identifier entry has `logical`, `address`, `length`, `format` and optionally `expected_contains` for soft-validation. Failed identifier reads are warnings, not errors — the device is still considered a match.

### 4.3 Negative fingerprints

If a device variant has **no positive identity register** (Acuvim L is the canonical example — see [`acuvim-l-profile.md`](acuvim-l-profile.md)), the fingerprint relies on:

- A **negative read** (`expect_exception`) at an address known to exist on a sibling variant but not this one.
- One or more **positive capability probes** at known-existing addresses with sane expected ranges.

This is brittle compared to a positive ID, but it's what the device provides. The profile loader treats negative-fingerprint matches as lower-confidence than positive matches.

## 5. `control` — writable registers

```yaml
control:
  demand_window_minutes:       # logical metric key (must exist in catalog with is_writable: true)
    fc: 6                      # 6 (write single) or 16 (write multiple)
    address: 0x010C
    format: word               # one of the supported formats; matches the catalog data_type
    allowed_values: [1, 5, 10, 15, 30]   # optional; overrides catalog allowed_values per profile
    readback_register:         # optional; defaults to write address
      address: 0x010C
      offset: 0
      fc: 3                    # optional; default 3 (read holding registers); use 4 for input registers
      format: word
    readback_delay_ms: 500     # optional; default 500
```

Each writable register is keyed by its logical metric name (which MUST exist in the catalog with `is_writable: true`). The agent validates incoming control commands against `allowed_values` (catalog default OR profile override) before issuing the Modbus write.

`readback_register` defaults to the write address with same format. Override when the device exposes the post-write value at a different address (some devices do). The `fc` field defaults to 3 (read holding registers); use 4 for input-register readback.

**Tolerance for read-back comparison is hardcoded in the loader**, not a profile field:
- For float formats: relative tolerance of 1 part in 10⁶ (well within Float32 precision).
- For integer formats: exact equality.
- For ASCII / custom formats: byte equality.

Profiles cannot override this; if a device legitimately needs a wider tolerance (e.g., a meter that rounds setpoints), that's a loader-level enhancement, not per-profile config.

## 6. Supported format types

### 6.1 Generic formats (decoded by the loader directly)

| Format | Bytes | Modbus regs | Description |
|--------|-------|-------------|-------------|
| `float32_be` | 4 | 2 | IEEE 754 single-precision, big-endian (ABCD byte order). Most common for modern AccuEnergy. |
| `float32_le` | 4 | 2 | Same but little-endian (DCBA). Some Schneider devices. |
| `float32_mb` | 4 | 2 | "Middle endian" / "word swap" (BADC). Watch out — Modbus library defaults vary. |
| `uint16` | 2 | 1 | Unsigned 16-bit integer. Big-endian within the register. |
| `int16` | 2 | 1 | Signed 16-bit integer (two's complement). |
| `uint32_be` | 4 | 2 | Unsigned 32-bit integer, big-endian word order. |
| `int32_be` | 4 | 2 | Signed 32-bit integer, big-endian word order. |
| `dword_high_first` | 4 | 2 | AccuEnergy energy convention: 32-bit unsigned with high word at the lower register address. |
| `word` | 2 | 1 | Alias for `uint16`. |
| `ascii` | varies | varies | ASCII string. `length` field on the metric specifies how many **registers** (each 2 bytes). Trailing nulls / spaces stripped. |

`bool` and `bitfield` are deferred — no MVP metric needs them. Adding later requires a minor version bump.

### 6.2 Custom decoders (`format: custom` + `decoder: <name>`)

Vendor-specific decode logic that doesn't generalise (e.g., the Acuvim clock packed as 7 sequential `uint16`s representing Y/M/D/H/M/S/DoW; future Sinexcel power-flag bitmaps; EPC SunSpec model 65534 oddities). Pattern:

```yaml
- { logical: meter_clock, offset: 0, format: custom, decoder: acuvim_clock }
```

The profile loader maintains a registry: `decoders["acuvim_clock"] = AcuvimClockDecoder()`. A profile referencing an unregistered decoder fails at load time with a clear "decoder not found" error.

Adding a new vendor decoder = one Python class implementing `decode(buffer: bytes, offset: int) -> Reading` + one line in the registry. The schema enum doesn't grow; only `decoder` strings do.

### 6.3 Offset alignment

Format-appropriate alignment is **enforced by the loader at profile load time**, not by the JSON Schema (cross-field constraints don't fit JSON Schema's model cleanly):

- `float32_*` / `uint32_be` / `int32_be` / `dword_high_first` — offset multiple of 4
- `uint16` / `int16` / `word` — offset multiple of 2
- `ascii` — any byte-aligned offset; loader checks `length × 2` doesn't exceed the block

Misalignment fails with a clear error naming the offending metric.

## 7. Profile loader (`lib/profile_loader/`)

The loader is a single Python module shared between the edge agent ([SOL-7](https://linear.app/solamon/issue/SOL-7)), the probe CLI ([SOL-18](https://linear.app/solamon/issue/SOL-18)), and cloud ingestion ([SOL-8](https://linear.app/solamon/issue/SOL-8)). It is THE owner of profile parsing, validation, decoding, and fingerprint-matching logic — every consumer goes through this same code path. **There is no second implementation, ever.**

The loader lives at `lib/profile_loader/` in the implementation tree (final path TBD by the writing-plans phase) and is packaged as a vendored Python module included in:
- The edge-agent Docker image
- The probe-cli pip package
- The cloud's FastAPI process

It has its own test suite covering: schema validation, format decoding, edge cases (offset alignment, unknown logical metrics, unsupported formats), and fingerprint matching against fake-Modbus-server fixtures for both Acuvim L (the canonical profile) and one synthetic non-matching profile.

### 7.1 API

```python
# In lib/profile_loader/__init__.py

class ProfileLoader:
    """Loads + validates profile YAMLs and the logical-metric catalog."""

    def load_catalog(self, catalog_path: str) -> Catalog: ...
    def load_profile(self, profile_path: str, catalog: Catalog) -> Profile: ...
    def register_decoder(self, name: str, decoder: CustomDecoder) -> None:
        """Register a custom decoder (e.g. 'acuvim_clock'). Called at module init."""


class Profile:
    schema_version: str
    device: DeviceInfo
    connection: ConnectionInfo
    fingerprint: Fingerprint
    read_blocks: list[ReadBlock]
    control: dict[str, ControlSpec]

    def schedule(self) -> Iterable[tuple[ReadBlock, float]]:
        """Yields (block, cadence_s) tuples for the agent to schedule."""

    def decode(self, block_name: str, response: bytes) -> dict[str, Reading]:
        """Decodes a Modbus FC03/FC04 response into a dict keyed by logical metric name.
        Applies per-metric scale and produces (value, raw_value, quality) for each metric.
        Raises DecodeError if response length doesn't match block length × 2 bytes."""

    async def fingerprint_match(self, modbus_client) -> FingerprintResult:
        """Runs the fingerprint reads against a connected device. Returns:
          - match: bool
          - confidence: "positive" (all reads matched expected) | "negative_fingerprint" (used expect_exception)
          - identifiers: dict[str, Any]  (manufacturer, model, firmware, serial — populated when available)
          - failures: list[str]  (human-readable per-read failure reasons; empty on full match)
        """

    def validate_control(self, logical_metric: str, value: Any) -> None:
        """Validates a control command against allowed_values + catalog data_type.
        Raises ValidationError on bad input (with a clear message). Returns None on success.

        NOTE: this raises rather than returning bool — callers use try/except to handle
        validation failures and surface the exception message to the user. Earlier drafts
        specified bool return; updated 2026-05-02 in response to spec review."""


class Catalog:
    schema_version: str
    metrics: dict[str, LogicalMetric]    # keyed by logical metric name

    def get(self, key: str) -> LogicalMetric | None: ...
    def all(self) -> list[LogicalMetric]: ...


class CustomDecoder(Protocol):
    """Vendor-specific decoder registered by name (e.g. 'acuvim_clock').
    Profile loader calls this when it encounters format: custom + decoder: <name>."""

    def decode(self, buffer: bytes, offset: int, length_bytes: int) -> Any: ...


class ValidationError(Exception):
    """Raised by validate_control on bad input. Message is operator-readable."""


class DecodeError(Exception):
    """Raised by Profile.decode when the response can't be decoded."""


class FingerprintResult:
    match: bool
    confidence: Literal["positive", "negative_fingerprint", "none"]
    identifiers: dict[str, Any]
    failures: list[str]
```

### 7.2 Decoders registered at module init

The standard decoders (float32 variants, integer types, ASCII, dword_high_first) are built in. Custom decoders registered explicitly by callers — e.g., the edge agent's `__init__.py` does:

```python
from lib.profile_loader import ProfileLoader
from lib.profile_loader.decoders import AcuvimClockDecoder

loader = ProfileLoader()
loader.register_decoder("acuvim_clock", AcuvimClockDecoder())
# ... and any others as new device families come online
```

This keeps the schema enum stable while the decoder set evolves.

### 7.1 Validation on load

When `validate()` is called:

1. Profile parses against `architecture/profiles/profile.schema.json`. Schema violations → fail.
2. Every `read_blocks[*].metrics[*].logical` exists in the catalog. Unknown keys → fail.
3. For each metric, the catalog's `data_type` is compatible with the profile's `format`. Mismatch (e.g., `float` data_type but `uint16` format without explicit scale) → warn.
4. All offsets are within their block's bounds. Out-of-bounds → fail.
5. For `control` entries, every key is a logical metric with `is_writable: true` in the catalog. Mismatch → fail.
6. For control entries with `allowed_values`, all values match the catalog `data_type`. Mismatch → fail.

Validation runs on profile load (every time the agent starts, every time the probe CLI is invoked). Hard failures abort startup.

### 7.2 Read scheduling

`Profile.schedule()` yields blocks at their `cadence_s` interval. The edge agent runs one async task per yielded block; tasks are independent. Within a block, the FC03 read is atomic (either it succeeds and all block metrics get a reading, or it fails and the agent records a Modbus error for the whole block).

### 7.3 Decode contract

`Profile.decode(block_name, response)` returns a dict where:

- Keys are logical metric names.
- Values are `Reading` objects: `{ value, raw_value, quality, decoded_at }`.
- `quality` is `"good"` if the decoded value is within the catalog's `expected_range`; `"uncertain"` if outside; `"bad"` only if decode itself failed (which should never happen because format errors are caught at load).

## 8. JSON Schema

The profile schema is formalised in `architecture/profiles/profile.schema.json`. The loader uses it via `jsonschema` (Python). The future linting tool ([SOL-14](https://linear.app/solamon/issue/SOL-14)) uses the same schema. CI gates on PR validation.

## 9. Acceptance criteria

- `architecture/profiles/profile.schema.json` exists and validates `architecture/profiles/acuvim_l.yaml`.
- The profile loader implementation lives in a shared Python module under `lib/profile_loader/` (or similar — final path decided in the edge-agent spec group).
- All semantics in §7 implemented: load + validate + schedule + decode + fingerprint_match + validate_control.
- Failed loads / schema violations / catalog mismatches surface clear error messages naming the offending file and line.

## 10. Out of scope (deferred)

- Sub-block sub-cadences (a metric inside a block sampled less frequently than the block itself). MVP stores at the block cadence (one row per metric per poll). Downsampling — per-metric storage cadence, continuous aggregates, per-metric retention — happens in cloud queries / Timescale features, not the profile.
- Per-site profile overrides → [SOL-13](https://linear.app/solamon/issue/SOL-13).
- Auto-detection (running fingerprint against ALL profiles on connect, picking the match) → [SOL-11](https://linear.app/solamon/issue/SOL-11). For MVP, the active profile is configured per site.
- Hot reload → [SOL-17](https://linear.app/solamon/issue/SOL-17).
- Schema versioning with backward-compat migration → [SOL-15](https://linear.app/solamon/issue/SOL-15).

## 11. Cross-references

- [`logical-metric-catalog.md`](logical-metric-catalog.md) — what the `logical:` references resolve to
- [`acuvim-l-profile.md`](acuvim-l-profile.md) — the first profile that exercises this schema end-to-end
- [`docs/specs/edge-agent/`](../edge-agent/) — the consumer of the loader API
- [`docs/specs/probe-cli/`](../probe-cli/) — the other consumer
