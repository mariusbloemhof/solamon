# Device library — detail specs

**Spec group owner:** [SOL-20 — MVP — Device library foundation](https://linear.app/solamon/issue/SOL-20)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §6, §7
**Status:** Working spec. Implementation against this spec produces real `architecture/logical_metrics.yaml` and `architecture/profiles/acuvim_l.yaml` files; the JSON Schema at `architecture/profiles/profile.schema.json` constrains every profile.

---

## Why this spec group exists

The eventual full system supports many device variants (multiple Acuvim models, Huawei SmartLogger, Sinexcel PWS1-500K, EPC Power CAB1000, Schneider PM5110, Deep Sea DSE8610, PPC, Sungrow). They all expose the same kinds of measurements (power, voltage, current, energy) but at completely different Modbus addresses. Two ways to handle that:

- **Bake the addresses into application code** — works for one device, becomes a maintenance disaster at three.
- **Separate "what data we want" from "how to get it"** — define logical metrics universally; map them to physical registers per device variant in standalone YAML profiles. Adding a new device variant becomes config (a new YAML), not code.

We're doing the second. This spec group nails the contracts.

## The three layers (concept recap)

```
LOGICAL METRIC CATALOG  ── architecture/logical_metrics.yaml
   "active_power_total" ── kW, instantaneous, sign convention "+ = consumption"
   "neutral_current"    ── A, instantaneous
   "demand_window_minutes" ── int, writable, allowed values [1, 5, 10, 15, 30]
        ▲
   resolved by
        │
DEVICE PROFILE          ── architecture/profiles/<variant>.yaml
   acuvim_l.yaml: active_power_total → 0x061C, Float32 BE, no scaling
   (future) acuvim_ii.yaml: active_power_total → 0x4022, Float32 BE
   (future) smartlogger.yaml: active_power_total → 40525, Int32, scale=0.001
        ▲
   used by
        │
PROFILE LOADER (in edge agent + cloud ingestion + probe CLI)
   Loads the profile for the connected device, schedules batched reads,
   decodes per spec, emits readings keyed by LOGICAL metric name.
   No code knows or cares about register addresses.
```

## Files in this folder

| File | What it specifies |
|------|-------------------|
| [`README.md`](README.md) | This index. |
| [`logical-metric-catalog.md`](logical-metric-catalog.md) | The vendor-agnostic metric catalog: every logical metric the platform recognises, with units, data types, sign conventions, expected ranges. |
| [`profile-schema.md`](profile-schema.md) | The YAML schema every device profile conforms to: device block, connection, fingerprint, read blocks, control registers, supported format types, profile loader semantics. |
| [`acuvim-l-profile.md`](acuvim-l-profile.md) | The concrete Acuvim L profile: every read block defined, every metric mapped, fingerprint strategy, control register, links to the actual YAML. |

## Machine-readable artifacts produced

| Path | What it is | Consumers |
|------|------------|-----------|
| `architecture/logical_metrics.yaml` | The metric catalog as YAML | Edge agent, cloud ingestion, probe CLI, dashboard |
| `architecture/profiles/profile.schema.json` | JSON Schema for profile validation | Profile loader (validates on load), [SOL-14](https://linear.app/solamon/issue/SOL-14) lint tool |
| `architecture/profiles/acuvim_l.yaml` | Concrete profile for Acuvim L | Edge agent (configured per site), probe CLI (cross-checked) |

## How the rest of the system consumes these

- **Edge agent** ([SOL-7](https://linear.app/solamon/issue/SOL-7)) — receives the consolidated config from cloud at startup (which includes the active profile + the logical metric catalog), uses the profile to schedule batched Modbus reads, decodes each metric per profile, publishes telemetry keyed by logical metric name.
- **Cloud ingestion** ([SOL-8](https://linear.app/solamon/issue/SOL-8)) — uses the catalog for type/range validation on incoming readings; stores `Reading` rows keyed by `logical_metric_key`. Serves the consolidated config to the edge.
- **Probe CLI** ([SOL-18](https://linear.app/solamon/issue/SOL-18)) — uses the profile's `fingerprint:` block to identify a device; uses `read_blocks:` to verify the device exposes what we expect; cross-checks against alternative profiles' blocks.
- **Web UI** ([SOL-9](https://linear.app/solamon/issue/SOL-9)) — references logical metric names for chart labels, units, and panel layout. Never knows about registers.

## Acceptance for SOL-20

Spec group is "done" when:

1. All four `.md` specs in this folder are committed and internally consistent.
2. `architecture/logical_metrics.yaml` is committed with the ~40 MVP-relevant metrics.
3. `architecture/profiles/profile.schema.json` is committed and validates `acuvim_l.yaml`.
4. `architecture/profiles/acuvim_l.yaml` is committed and conforms to the schema, covering all read blocks and the control register required by the dashboard.
5. The edge-agent and cloud detail specs (next two spec groups) reference the contracts here without contradiction.

## Out of MVP scope

See SOL-20 for the deferred items. Concretely: profile auto-detection, profile editor UI, per-site overrides, validation/linting tools, schema versioning, hot reload, Acuvim II and other-device profiles. All have Linear issues.
