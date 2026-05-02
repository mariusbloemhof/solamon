# Logical metric catalog

**Spec group:** [device-library](README.md)
**Linear:** [SOL-20](https://linear.app/solamon/issue/SOL-20)
**Machine artifact:** `architecture/logical_metrics.yaml`

The vendor-agnostic universe of metrics this platform recognises. Every reading written to the database, rendered on the dashboard, used in alerts, or exposed via the API references one of these names. Device profiles map them to physical registers; nothing else needs to know register addresses exist.

---

## 1. Concept

A logical metric is a (name, unit, data type, semantic-context) tuple defining one observable quantity, independent of how a particular device exposes it. Examples:

- `active_power_total` — the total real power flowing through a meter, in kW, instantaneous (not cumulative), sign-positive when energy is being consumed from the grid.
- `import_active_energy_kwh` — cumulative imported energy in kWh; monotonic (only ever increases barring a meter reset).
- `demand_window_minutes` — the demand integration period currently configured on the meter, in minutes; writable.

Two devices that report `active_power_total` (an Acuvim L and a Huawei SmartLogger, say) may store the underlying value in entirely different formats at entirely different register addresses. The logical metric is the same; the *profile* knows how to retrieve it.

## 2. Catalog structure

The catalog is a YAML map from logical metric key (snake_case identifier) to metadata. Each entry has:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `label` | string | yes | Human-readable name for UI display |
| `unit` | string | yes | SI unit string: `Hz`, `V`, `A`, `kW`, `kvar`, `kVA`, `kWh`, `kvarh`, `kVAh`, `%`, `min`, `°C`. Empty string for unitless ratios (PF). |
| `data_type` | enum | yes | One of: `float`, `int`, `bool`, `enum`, `bitfield`, `datetime`, `string` |
| `category` | enum | yes | One of: `power`, `energy`, `voltage`, `current`, `power_factor`, `frequency`, `demand`, `quality`, `configuration`, `control`, `derived`. Used for grouping in UI and filtering in queries. |
| `is_cumulative` | bool | yes | `true` for monotonically-increasing energy counters; `false` for instantaneous values |
| `monotonic` | bool | conditional | Only when `is_cumulative=true`. If `true`, the value never decreases except on explicit reset. |
| `direction_convention` | string | conditional | Free-text describing sign convention. Required for any metric where direction matters (active power, reactive power). Example: `"positive = consumption from grid; negative = export to grid"`. |
| `expected_range` | `[min, max]` | yes | Sanity range used by the probe CLI ([SOL-18](https://linear.app/solamon/issue/SOL-18)) and ingestion validation. Values outside the range raise quality flags or alarms. |
| `is_writable` | bool | no | Default `false`. `true` for metrics the operator can change via control commands. |
| `allowed_values` | list | conditional | Only when `is_writable=true` and the value is constrained. e.g., `[1, 5, 10, 15, 30]` for demand window. |
| `enum_values` | map | conditional | Only when `data_type=enum`. Maps integer codes to symbolic strings. |

## 3. The catalog (MVP)

Grouped by category. The actual machine-readable form is in `architecture/logical_metrics.yaml`; this section is the human-readable rationale.

### 3.1 Power (instantaneous, kW / kvar / kVA)

Conventions for AC active and reactive power:
- **Active power** sign: positive = energy flowing in the import direction (grid → load); negative = export. The Acuvim and most meters follow this convention by default.
- **Reactive power** sign: positive = inductive (lagging); negative = capacitive (leading). Acuvim default.
- **Apparent power** is always non-negative.

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `active_power_total` | Total active power | kW | float | Hero KPI for load assessment. Sign per above. |
| `active_power_l1` / `_l2` / `_l3` | Phase {A/B/C} active power | kW | float | Per-phase. Mixed signs across phases on a balanced load = CT polarity flipped on one phase (installation-health flag). |
| `reactive_power_total` | Total reactive power | kvar | float | |
| `reactive_power_l1` / `_l2` / `_l3` | Phase {A/B/C} reactive power | kvar | float | |
| `apparent_power_total` | Total apparent power | kVA | float | Always ≥ 0. |
| `apparent_power_l1` / `_l2` / `_l3` | Phase {A/B/C} apparent power | kVA | float | |

### 3.2 Energy (cumulative, monotonic)

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `import_active_energy_kwh` | Imported active energy | kWh | float | Monotonic. Resets only on explicit meter reset (which should never happen post-commissioning). |
| `export_active_energy_kwh` | Exported active energy | kWh | float | Monotonic. Only relevant if site has PV. |
| `import_reactive_energy_kvarh` | Imported reactive energy | kvarh | float | Monotonic. |
| `export_reactive_energy_kvarh` | Exported reactive energy | kvarh | float | Monotonic. |
| `apparent_energy_kvah` | Apparent energy | kVAh | float | Monotonic. |

### 3.3 Voltage

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `voltage_l1_n` / `_l2_n` / `_l3_n` | Phase {A/B/C} voltage (L-N) | V | float | Healthy SA range 207–253 V (230 V ±10 %). |
| `voltage_l1_l2` / `_l2_l3` / `_l3_l1` | Line voltage {L1-L2 / L2-L3 / L3-L1} | V | float | Line-to-line. Healthy SA range 360–440 V (400 V ±10 %). |

> **Deferred (post-MVP):** `voltage_avg_phase`, `voltage_avg_line`. Some devices (e.g., Acuvim II) expose averages directly; on Acuvim L they're absent. Will become **derived metrics** computed cloud-side from per-phase readings — see [SOL-23](https://linear.app/solamon/issue/SOL-23) for the derived-metrics design.

### 3.4 Current

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `current_l1` / `_l2` / `_l3` | Phase {A/B/C} current | A | float | |
| `current_neutral` | Neutral current | A | float | Healthy: small (a few A). Large neutral current = imbalance or fault. |

> **Deferred (post-MVP):** `current_avg` — same reasoning as `voltage_avg_*`. Will become a derived metric. [SOL-23](https://linear.app/solamon/issue/SOL-23).

### 3.5 Power factor

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `power_factor_l1` / `_l2` / `_l3` | Phase {A/B/C} power factor | (none) | float | Range -1.0 to +1.0; sign indicates leading/lagging on Acuvim. |
| `power_factor_total` | Total system power factor | (none) | float | Range -1.0 to +1.0. |

### 3.6 Frequency

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `frequency_hz` | Line frequency | Hz | float | SA grid: 50.0 Hz nominal; healthy ±0.5 Hz. |

### 3.7 Demand (time-windowed averages)

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `active_power_demand` | Active power demand | kW | float | Averaged over the configured demand window. The KPI for capacity-billing tariffs. |
| `apparent_power_demand` | Apparent power demand | kVA | float | |
| `reactive_power_demand` | Reactive power demand | kvar | float | |
| `current_demand_l1` / `_l2` / `_l3` | Per-phase current demand | A | float | |
| `active_power_demand_max` | Peak active power demand this period | kW | float | Reset at billing-period boundary. |
| `active_power_demand_max_timestamp` | Time of peak active power demand | (none) | datetime | Companion to the above. |

### 3.8 Power quality

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `voltage_unbalance_pct` | Voltage unbalance | % | float | Healthy: <2 %. >5 % indicates supply or wiring problem. |
| `current_unbalance_pct` | Current unbalance | % | float | Context-dependent; depends on whether load is balanced by design. |
| `thd_voltage_l1` / `_l2` / `_l3` | THD voltage phase {A/B/C} | % | float | Healthy: <5 %. |
| `thd_current_l1` / `_l2` / `_l3` | THD current phase {A/B/C} | % | float | Context-dependent on load type. |

> **Deferred (post-MVP):** `load_type`. Lives in Acuvim L secondary block (`0x014A`) which the MVP profile doesn't poll. Add when we extend the profile to include the secondary block — additive change, no schema bump.

### 3.9 Configuration (read-only at runtime; captured on startup + hourly)

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `voltage_wiring_type` | Voltage wiring type | (none) | enum | `3LN` / `3LL` / `2LL` / `1LN` / `1LL` |
| `current_wiring_type` | Current wiring type | (none) | enum | `3CT` / `2CT` / `1CT` |
| `pt_ratio_primary` | PT primary side voltage | V | float | |
| `pt_ratio_secondary` | PT secondary side voltage | V | float | |
| `ct_ratio_primary` | CT primary side current | A | int | |
| `ct_ratio_secondary` | CT secondary side current | (mV) | int | 1 / 5 / 333 mV |
| `meter_clock` | Meter internal clock | (none) | datetime | Compared to Pi NTP for drift detection. |

### 3.10 Control (writable)

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `demand_window_minutes` | Demand integration window | min | int | `is_writable: true`; `allowed_values: [1, 5, 10, 15, 30]`. The MVP control demo target. |

### 3.11 Edge-derived (not from device; published by the edge agent itself)

| Key | Label | Unit | Type | Notes |
|-----|-------|------|------|-------|
| `edge_modbus_errors_per_minute` | Edge Modbus error rate | (none) | float | Rolling 1-minute window. |
| `edge_buffer_depth_seconds` | Local buffer depth (oldest unpublished reading age) | s | int | Surfaces backlog when LTE drops. |
| `edge_last_successful_read` | Time of last successful Modbus read | (none) | datetime | Stale-detection on the dashboard. |

## 4. Naming conventions

- **Snake_case** keys, lower-case.
- Phase indices are `_l1` / `_l2` / `_l3` (matching IEC 60038 conventions). Some manuals use A/B/C; the catalog standardises on 1/2/3.
- Cumulative quantities end with the unit (`_kwh`, `_kvarh`, `_kvah`) — disambiguates from instantaneous power.
- Boolean / enum / bitfield identifiers don't carry units.
- Timestamps (datetime fields) end in `_timestamp` if they're a companion to another metric (e.g., `active_power_demand_max_timestamp`).

## 5. Versioning

- The catalog gets a top-level `schema_version: "1.0"` field. MVP ships at 1.0. The field name is intentionally identical to the one in device profiles for consistency.
- **Additive changes** (new metrics) → bump minor version (`1.1`). Edge agents on older versions ignore unknown keys.
- **Breaking changes** (renamed key, changed unit, changed sign convention) → bump major version (`2.0`). Migration documented; deployed agents must upgrade together with cloud.
- Catalog version is included in the consolidated config returned by `GET /api/v1/edge/config/{site_slug}` so the agent can refuse incompatible versions.

Schema-version handling for full deployments is the post-MVP [SOL-15](https://linear.app/solamon/issue/SOL-15) work. For MVP we ship 1.0 and forward-compat is moot.

## 6. Acceptance criteria for this catalog

- `architecture/logical_metrics.yaml` exists, parses as YAML, top-level shape matches the schema described above.
- All ~55 metrics above are present with required fields populated.
- Every metric used in the Acuvim L profile is present in the catalog (cross-checked at profile load).
- Every metric used in the dashboard card layout (main spec §9 + register-scope doc §J) is present.
- Loaded by the edge agent at startup; loaded by cloud ingestion at startup; both raise a clear error if the file is missing or invalid.

## 7. Cross-references

- [`profile-schema.md`](profile-schema.md) — how profiles reference these keys
- [`acuvim-l-profile.md`](acuvim-l-profile.md) — the first profile that consumes them
- Main spec [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §6.1, §7
- [`requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md) — drives the dashboard cards and which logical metrics they need
