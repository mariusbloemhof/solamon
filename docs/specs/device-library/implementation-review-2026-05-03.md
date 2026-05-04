# Device-library implementation review — 2026-05-03

**Reviewer:** Claude (spec verification duty)
**Scope reviewed:** the implemented `packages/profile_loader/` package (15 source/test files, 1620 LOC) plus `architecture/logical_metrics.yaml`, `architecture/logical_metrics.schema.json`, `architecture/profiles/profile.schema.json`, `architecture/profiles/acuvim_l.yaml`, and `.github/workflows/device-library.yml`.

Cross-checked against:
- `docs/specs/device-library/` (logical-metric-catalog, profile-schema, acuvim-l-profile, README)
- `docs/specs/device-library/review-2026-05-02.md` (the 17 findings the spec change set addressed)
- `docs/specs/cloud/`, `docs/specs/edge-agent/`, `docs/specs/probe-cli/`, `docs/specs/web-ui/` (consumers)
- `docs/specs/edge-agent/review-2026-05-02.md` (whose findings #5, #6 were contract issues with this package)

**Verification run:**
- `pytest packages/profile_loader/tests` → 53/53 pass.
- `ruff check packages/profile_loader` → clean.
- `python -m profile_loader validate architecture/profiles/acuvim_l.yaml` → exit 0; "AccuEnergy / Acuvim L (meter); 6 read block(s); 54 metric(s) total; 1 control register(s)".

---

## What landed correctly

Worth calling out before the punch list, because most of it is right:

- **Units fix.** `acuvim_l.yaml` applies `scale: 0.001` to all 17 active/reactive/apparent power metrics (lines 78-141) — and to none of the voltages/currents/PF. `test_decode_returns_kw_after_scale_applied` explicitly verifies `12350.0 W` decodes to `12.350 kW`. The single highest-impact finding from the device-library review is in.
- **JSON Schema for the catalog** (`logical_metrics.schema.json`) — closes review #3.
- **`format: custom` + `decoder: <name>` registry** — closes review #2 (vendor-specific leak from FormatType enum). `acuvim_clock` no longer in the global enum.
- **`connection.protocol` narrowed to `modbus_tcp | modbus_rtu`** — closes review #4 (push-protocol leak), with explicit pointer to SOL-22 for the post-MVP discriminator.
- **JSON Schema enforces alignment-related and conditional rules**: `decoder` required when `format=custom` (MetricMapping `if/then`), `format` required when no `expect_exception` (FingerprintRead `if/then`), `monotonic` required when `is_cumulative=true`, `enum_values` required when `data_type=enum`, `allowed_values` OR `expected_range` required when `is_writable=true`. The loader supplements with format-byte alignment.
- **`enum_values` keys quoted as strings** in the catalog YAML (closes review #17 / cloud review #15).
- **`readback_register.fc`** added to the schema (closes edge-agent review #14).
- **`validate_control` raises `ValidationError`** rather than returning `bool` — aligns the loader with edge-agent's expected contract (closes edge-agent review #6).
- **`Profile.fingerprint_match` is async** with a typed `ModbusClient` Protocol — pragmatic (the spec's `def` was sketch-level; the real use case is async).
- **CI workflow** runs lint + pytest + format check + a real `python -m profile_loader validate` against the committed profile on every PR.

The spec→implementation mapping is unusually clean. The findings below are the leftover edges.

---

## Critical — produces wrong data, blocks distribution, or contradicts a published spec

### 1. `Reading` is missing `decoded_at` — the implementation contradicts the spec it's published against

`docs/specs/device-library/profile-schema.md:339`:

> Values are `Reading` objects: `{ value, raw_value, quality, decoded_at }`.

`packages/profile_loader/src/profile_loader/types.py:21-25`:

```python
@dataclass(frozen=True)
class Reading:
    value: Any
    raw_value: int | None
    quality: Literal["good", "uncertain", "bad"]
```

No `decoded_at`. The edge agent's poller (`docs/specs/edge-agent/modbus-poller.md:82`) plans to inject `timestamp = now()` itself, which is fine — but the spec promises the loader produces a self-dated `Reading`, and downstream code (cloud ingestion, probe-cli output, the future profile-editor preview) may rely on that.

Pick one and align:
- **Spec drops `decoded_at`** (the loader is pure; the consumer owns timestamping). Cleaner separation; matches reality.
- **Implementation adds `decoded_at`** (defaults to `datetime.now(timezone.utc)` at decode time). Costs a tiny bit of side-effect impurity but matches the published contract.

Today's state — spec says one thing, code does another — is what bit the web-ui review most: implementations get written against the spec, the spec is wrong, the implementation looks broken at integration time.

### 2. `AcuvimClockDecoder` treats the meter clock as UTC unconditionally — drift detection becomes meaningless if the meter isn't UTC

`packages/profile_loader/src/profile_loader/decoders.py:85-96`:

```python
y, mo, d, h, mi, s, _dow = struct.unpack_from(">7H", buffer, offset)
dt = datetime(y, mo, d, h, mi, s, tzinfo=UTC)
return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
```

`tzinfo=UTC` is hardcoded. The Acuvim's clock registers don't carry timezone info — they return whatever wall-clock time the meter is configured to. Per `acuvim-l-profile.md §5.5`, this metric exists for "drift detection vs Pi NTP". The Pi is set to UTC (per `pi-install.md §1.2`). If the operator left the meter at South Africa Standard Time (UTC+2) — the default for many sites — the comparison shows `meter_clock - pi_clock ≈ -2 hours` and "drift detection" reports a 2-hour offset that is actually a configuration mismatch, not drift.

Fix options:
- **Mandate UTC at the meter** in commissioning. Add a `pi-install.md` check: probe-CLI sanity-warns when meter wall time differs from Pi NTP by more than a small margin AND timezones might explain it. Document explicitly.
- **Accept timezone as a decoder argument** (per-profile or per-site). Adds complexity for a single-decoder use case.

The minimum is a documentation note: "Acuvim L's meter clock is interpreted as UTC; the AXM-WEB2 web UI should be set to UTC at commissioning. Drift detection assumes this." Today's silent assumption is a hidden footgun.

### 3. Hard-coded `REPO_ROOT` in `loader.py:21` blocks pip-install distribution

```python
REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = {
    "catalog": REPO_ROOT / "architecture" / "logical_metrics.schema.json",
    "profile": REPO_ROOT / "architecture" / "profiles" / "profile.schema.json",
}
```

This works only when `loader.py` is at `<repo>/packages/profile_loader/src/profile_loader/loader.py`. The instant someone runs `pip install solamon-profile-loader`, the package lives at `site-packages/profile_loader/` — `parents[4]` points to a directory that has no `architecture/` subtree, and the schema files cannot be opened.

The probe-cli spec (`probe-cli/README.md §5`) names three distribution targets — Pi container, dev-laptop pip-install, CI fixture. Two of those need pip-install to work for a non-checkout install path. As written, only the workspace-checkout path works.

The same problem applies to `__main__.py:18` (`DEFAULT_CATALOG = REPO_ROOT / ...`).

`pyproject.toml` for `solamon-profile-loader` has no `package_data`, no `MANIFEST.in`, and no `[tool.setuptools.package-data]` block — schemas, catalog YAML, profile YAMLs are not bundled.

Fix:
- Ship schemas under `packages/profile_loader/src/profile_loader/_schemas/`, load via `importlib.resources`.
- Accept `schema_dir: Path | None = None` on `ProfileLoader.__init__` so callers can override.
- Document the workspace-checkout assumption explicitly if pip-install is a non-goal for MVP. Currently neither the spec nor the package README acknowledges the constraint.

### 4. `expected_contains` without `format: ascii` silently passes, defeating the fingerprint check

`fingerprint.py:78-80`:

```python
if read.expected_contains is not None and isinstance(value, str):
    if read.expected_contains not in value:
        return False, f"value {value!r} does not contain {read.expected_contains!r}", value
return True, None, value
```

If a profile sets `format: uint16, expected_contains: "x"`, the value decodes to an int, `isinstance(value, str)` is False, the check is skipped, and the function falls through to `return True, None, value`. The fingerprint claims it matched.

The schema's `oneOf` requires exactly one of `expected | expected_range | expected_contains | expect_exception` — but it doesn't constrain `expected_contains` to ASCII formats. `evaluate_read` doesn't either.

Fix:
- Add a schema-level `if/then`: `expected_contains` requires `format: ascii`.
- And/or in `evaluate_read`, raise (or return failure) when type doesn't match the predicate: `expected_contains` on non-string is an authoring error, not a silent pass.

No test exercises this combination, so it currently goes undetected.

---

## Major — gaps and contract drift

### 5. `evaluate_identifier` swallows all exceptions silently — operators have no diagnostic on identifier failures

`fingerprint.py:84-105`:

```python
async def evaluate_identifier(...):
    try:
        ...
        return (ident.logical, value)
    except Exception:
        return None
```

Per `profile-schema.md §4.2`: "Failed identifier reads are warnings, not errors." ✓ silent-OK is the intended behaviour. But:

- A bare `except Exception` masks bugs as well as transient failures. A typo in a profile that produces a `KeyError` here won't surface anywhere.
- `FingerprintResult.identifiers` shows successful reads only; failed identifier reads simply don't appear. An operator looking at `result.identifiers == {}` cannot tell whether the profile defined no identifiers, or defined some that all failed.

Add:
- A `failed_identifiers: list[tuple[str, str]]` (or similar) field on `FingerprintResult` populated with `(logical, reason)`.
- Catch specific exception types (`ConnectionError`, `TimeoutError`, decode errors); let unexpected ones propagate.
- At minimum, `log.warn` the failure with the offending identifier name.

### 6. Loose typing on the public API

- `Profile.decode(self, block_name: str, response: bytes, catalog: Any | None = None, decoders: dict[str, Any] | None = None)` — should be `Catalog | None` and `dict[str, CustomDecoder] | None`.
- `Profile.fingerprint_match(self, client: Any, unit_id: int | None = None)` — should be `ModbusClient` (the protocol exists at `fingerprint.py:14`).

The lazy imports inside the methods (to avoid cycles, see #9) make this awkward but not impossible. Use `TYPE_CHECKING` to import the types for annotations without runtime cost.

The cost today is: IDE auto-complete misses, type checkers can't catch a bad caller, and the published surface is harder to read than it should be. Cheap fix.

### 7. `Catalog.from_dict` accepts a v1.0 (flat-map) shape that the schema no longer permits

`catalog.py:54-81`:

```python
if "schema_version" in raw and "metrics" in raw:
    schema_version = raw["schema_version"]
    metric_map = raw["metrics"]
else:
    metric_map = raw   # legacy v1.0 flat shape
```

`logical_metrics.schema.json` requires `{schema_version, metrics}`. So a flat-shape input would fail schema validation in `ProfileLoader.load_catalog` before reaching `Catalog.from_dict`. Whoever bypasses schema validation (only the catalog tests) gets v1.0 fallback. It's not dead code (`test_catalog.py` uses the flat shape), but it's also not a published contract. Either:

- Update tests to use the wrapper shape and remove the fallback.
- Or formally support both shapes in the schema and document the dual-version policy.

The current state — schema says one thing, loader accepts something else — is a forward-compat mine.

### 8. Cyclic imports forced into runtime via lazy imports inside methods

`profile.py:122` and `profile.py:193-194` do `from .decoders import decode_format` and `from .fingerprint import evaluate_identifier, evaluate_read` inside the methods to break a cycle:

- `profile.py` is imported by `fingerprint.py` (which uses `FingerprintRead`, `FingerprintIdentifier`).
- `profile.py` would import `fingerprint.py` (for `evaluate_*`).
- Cycle.

Functional, but a code smell. Alternatives:
- Move `decode` and `fingerprint_match` out of `Profile` into module-level functions that accept a `Profile`. Pure functions over data; no cycle.
- Keep them on `Profile` but have `fingerprint.py` and `decoders.py` import from `profile.py` only, and `profile.py` resolve the function references via a small registry pattern.

Not urgent; low correctness risk; flag for future tidying.

### 9. Misleading comment on `_registers_to_bytes`

`fingerprint.py:36`:

```python
# Clamp to uint16 range (0-65535) to handle test values that overflow
val = int(r) & 0xFFFF
```

The clamp is correct. The justification is wrong: Modbus 16-bit registers are uint16 by definition; the clamp is defensive against a misbehaving Modbus library returning out-of-range Python ints, not "test values that overflow". Reword to:

```python
# Modbus registers are 16-bit; clamp defensively against malformed responses.
```

Otherwise readers will assume the code accommodates test bugs and is brittle in production.

### 10. `Profile.from_dict` does direct dict access — relies on schema validation upstream

`profile.py:223-240` uses `raw["device"]`, `raw["connection"]`, etc. without `.get` or KeyError handling. If a caller does `Profile.from_dict(broken_dict)`, they get a Python `KeyError` rather than a domain-meaningful `ProfileLoadError`.

The intended contract is "always go through `ProfileLoader.load_profile` which validates first". A few tests construct profiles directly via `Profile.from_dict` — they're well-formed, so no issue. But the public exposure invites callers to do the wrong thing.

Either:
- Document `Profile.from_dict` as internal (rename to `_from_dict`).
- Or wrap key access in a single helper that raises `ProfileLoadError` consistently.

### 11. No package-internal helper for "render hex address as `0x____`"

Per cloud review #14 / web-ui review (admin/profile detail page): YAML hex addresses (`0x0600`) parse to integers (1536) and don't round-trip. The Profile detail page in the web UI promises hex rendering at display time. The probe-cli's JSON output schema (`probe-output.schema.json:138-145`) supports both string-hex and integer for addresses, leaving the choice to the producer.

The package has no helper for this. Every consumer (web-ui, probe-cli, profile editor) will reinvent address-to-hex formatting and have to know which fields are addresses (read_blocks address, fingerprint reads, control address, identifiers, readback_register).

A single-line export `format_address(n: int) -> str` returning `"0x{n:04X}"` plus a class-level list of address fields would prevent inconsistent rendering across consumers.

---

## Minor — polish

### 12. `test_smoke.py` is a one-line import test

Trivial; either delete or expand.

### 13. `AcuvimClockDecoder` discards the day-of-week field

`decoders.py:91`: `_dow` is unpacked then ignored. Could double-check that the reported DoW matches the date computed from Y/M/D — if mismatched, raise `ValueError` (likely a bus-corruption indicator). Out of MVP scope but worth a comment.

### 14. `evaluate_read`'s `if read.format is None: return True, ...` is unreachable

The schema's `if/then` enforces `format` whenever `expect_exception` is absent. Defensive but dead under the published contract. Could `assert` instead, or document as defense-in-depth against bypassed schema validation.

### 15. Test docstring at `test_fingerprint.py:111` says `# "Acuen"` but the bytes encode `"AccuEn"`

Cosmetic. The decoded value (post rstrip nulls) is `"AccuEn"` — matches the assertion. Comment is misleading.

### 16. CI workflow path filter excludes `docs/specs/device-library/**`

`.github/workflows/device-library.yml` triggers on `packages/profile_loader/**`, `architecture/**`, `pyproject.toml`, and the workflow itself. Spec-only changes don't re-run tests. Defensible (specs don't break tests) but worth a noted assumption — the spec docs reference the implementation, and a doc PR could quietly drift from the code.

### 17. Workspace `pyproject.toml` lists src paths for unimplemented packages

`pyproject.toml:7`:

```toml
src = ["packages/profile_loader/src", "packages/edge_agent/src", "packages/cloud_app/src", "packages/probe_cli/src"]
```

Three of those don't exist yet. Lint config preemptively configured. Harmless; will be ready when the packages land.

### 18. `ProfileLoader.__init__` takes no parameters; you can register decoders post-hoc but can't construct empty

`loader.py:59-62` always seeds `default_registry()`. Tests that want to verify "decoder not registered" error path use a synthetic profile that references an unregistered name (✓ works) but can't construct a loader without `acuvim_clock`. Minor; flag for future flexibility.

### 19. `_registers_to_bytes` builds a `bytearray` then converts to `bytes`

`fingerprint.py:32-38` is fine; trivially `b"".join(...)` would work too. Style.

### 20. Catalog `expected_range` is `tuple[float, float] | None`

`catalog.py:35`: tuple typing is correct, but Python's `tuple` annotation without explicit length is the same as `tuple[float, ...]` in some checkers. The `tuple[float, float]` annotation is fine in modern type-checkers; flag for the rare style-strict reader.

---

## Summary

The spec→code mapping is the cleanest of any spec group reviewed: the device-library review's seventeen findings are visible in the artifacts, the units fix is end-to-end-tested, JSON schemas exist and run on every PR. CI is real, tests are real, lint is clean.

Three items deserve attention before consumers (edge agent, cloud, probe-cli) start integrating:

- **#1 (Reading.decoded_at)** — pick a side. The current state has the spec promising one shape and the code shipping another; that's the kind of misalignment that bites every consumer at integration time.
- **#2 (AcuvimClockDecoder UTC assumption)** — at minimum, document the commissioning assumption. Otherwise drift detection silently lies about a 2-hour offset that is actually a meter-config mismatch.
- **#3 (REPO_ROOT hardcoded)** — fine for the workspace-only consumption pattern; a real block for the probe-cli's stated pip-install distribution target. Decide whether pip-install is in scope for MVP or not, and document the answer.

The rest are tractable polish that pose no risk to bench Day 4-5 telemetry.
