# Device-library spec review — response

**Reviewed:** [`review-2026-05-02.md`](review-2026-05-02.md) — 17 findings (1 critical, 7 major, 9 minor)
**Author:** Marius (with Claude)
**Date:** 2026-05-02
**Status:** All findings addressed in this commit. Two new Linear issues filed for items deferred to post-MVP follow-on work.

Each finding was validated independently before applying a fix — no blind acceptance. Findings I judged needed pushback or alternative resolution are explicitly flagged.

---

## Critical

### #1 — Power units off by 1000× (no `scale: 0.001`)

**Validity check:** Acuvim L manual V2.0.3 (`discovery/specs/acuvim_l_modbus_registers.md` §4) declares the primary Float32 power fields in **W / var / VA**. Catalog uses **kW / kvar / kVA**. Profile had no scale. Confirmed real bug.

**Note for the bench:** the Acuvim II manual for the same fields says **kW / kvar / kVA** — vendor inconsistency between sister products is plausible but worth verifying. Could also be a manual mislabel.

**Resolution:**
- Added `scale: 0.001` to all 17 power metrics in [`architecture/profiles/acuvim_l.yaml`](../../../architecture/profiles/acuvim_l.yaml) (active, reactive, apparent — total + per-phase + demand variants + peak demand).
- Added §7.2 to [`acuvim-l-profile.md`](acuvim-l-profile.md) — bench Day 3 includes a multimeter cross-check; if values agree at our scale the manual was right; if off by 1000× we remove the scale.
- Added the §7.2 note to the §5.1 realtime-block scaling notes inline so an implementer reading the profile doc sees the unit-uncertainty flag immediately.

---

## Major

### #2 — Vendor-specific format leaked into global enum

**Validity check:** `acuvim_clock` was sitting in `FormatType` alongside generic types. Adding a Sinexcel power-flag bitmap or EPC SunSpec model 65534 decoder would grow the enum the same way. Real architectural concern.

**Resolution:** Refactored to **`format: custom` + `decoder: <name>`**.
- [`architecture/profiles/profile.schema.json`](../../../architecture/profiles/profile.schema.json) — removed `acuvim_clock` from `FormatType`; added `custom` to the enum; added `decoder` field on `MetricMapping` and `Identifier`; added conditional `if/then` requiring `decoder` when `format: custom`.
- [`architecture/profiles/acuvim_l.yaml`](../../../architecture/profiles/acuvim_l.yaml) — `meter_clock` now uses `format: custom, decoder: acuvim_clock`.
- [`profile-schema.md`](profile-schema.md) §6 — split into "Generic formats" (table) and "Custom decoders" (registry pattern explained).

Loader implementation: a `decoders` registry where adding a new vendor decoder = one Python class + one line in the registry. Schema enum doesn't grow.

### #3 — No JSON Schema for the catalog

**Validity check:** `profile.schema.json` existed; no equivalent for `logical_metrics.yaml`. SOL-14 lint tool can't validate without one.

**Resolution:** Created [`architecture/logical_metrics.schema.json`](../../../architecture/logical_metrics.schema.json) with conditional rules: `monotonic` required when `is_cumulative: true`; `enum_values` required when `data_type: enum`; `allowed_values` or `expected_range` required when `is_writable: true`. Catches structural errors at PR time.

### #4 — Schema can't express push profiles

**Validity check:** Confirmed. Original schema allowed `connection.protocol: mqtt | http_push` but `read_blocks: minItems: 1` was unconditionally required, so a push profile would always fail validation. Conflict between declared protocol enum and required fields.

**Resolution chosen — narrow + defer:**
- Narrowed `connection.protocol` enum to `modbus_tcp | modbus_rtu` only.
- Added explicit MVP-scope note in [`profile-schema.md`](profile-schema.md) §1 referencing **[SOL-22](https://linear.app/solamon/issue/SOL-22)** for the future discriminated extension.
- Created **[SOL-22](https://linear.app/solamon/issue/SOL-22) — Device profile schema — push protocol support (MQTT, HTTP)**, post-MVP, low priority. Triggered by the billing engine work coming online.

**Alternative considered:** add the discriminator now (`anyOf` based on protocol). Rejected: significant complexity for a path we don't ship in MVP. Narrow + defer is honest.

### #5 — Fingerprint can mis-identify a non-WEB Acuvim II as Acuvim L

**Validity check:** Confirmed. Per [`acuvim_ii_modbus_registers.md`](../../../discovery/specs/acuvim_ii_modbus_registers.md), the SunSpec `0xC350` block requires AXM-WEB / WEB2 firmware. An Acuvim II without WEB also returns exception `0x02` at `0xC350`. The frequency probe at `0x0130` and slave-address echo at `0x0101` are unverified on Acuvim II — they likely pass.

**Resolution:**
- Added "Known false-positive class" callout to [`acuvim-l-profile.md`](acuvim-l-profile.md) §4.
- Documented mitigation: the probe-CLI's `--cross-check` flag reads the Acuvim II `0x4000` block; if it returns sensible Float32 values, the device is an Acuvim II without WEB.
- Added a caveat about reporting fingerprint result as "negative match" so the lower confidence is visible.
- Added a comment in the profile YAML pointing at the same explanation.

**Note:** in MVP practice this is unlikely (Johan's two units have AXM-WEB2; Acuvim II is uncommon in SA market). The mitigation surfaces the case rather than silently mis-routing.

### #6 — Sub-variant has no home in the data model

**Validity check:** The cloud `data-model.md` and `0001_initial.sql` already have `sub_variant`, `firmware_version`, `serial_number` columns on `app.device`. The issue is the **summary table** in main spec §6.2 which abbreviated to just `host, port, unit_id, device_type_id`. Doc-consistency issue, not a real schema gap.

**Resolution:** Updated [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §6.2 to include the missing columns in the Device-row description.

### #7 — Orphaned catalog metrics

**Validity check:** `voltage_avg_phase`, `voltage_avg_line`, `current_avg`, `load_type` defined in catalog with no read-block reference. Real orphans.

**Resolution chosen — drop with deferral notes:**
- Removed all four entries from [`architecture/logical_metrics.yaml`](../../../architecture/logical_metrics.yaml).
- Replaced with deferral notes pointing at **[SOL-23](https://linear.app/solamon/issue/SOL-23) — Derived metrics**.
- Updated [`logical-metric-catalog.md`](logical-metric-catalog.md) tables to flag them as deferred with the same reference.
- `load_type` lives in Acuvim L's secondary block (`0x014A`) which we don't poll in MVP; deferral is honest.

**Alternative considered:** keep them with `is_derived: true` placeholder. Rejected: cleaner to drop and re-add when SOL-23 ships derivation logic. Re-adding is trivial.

**Created [SOL-23](https://linear.app/solamon/issue/SOL-23) — Derived metrics** describing the derivation framework (`category: derived` + `derived_from` formula).

### #8 — Demand-window storage cadence inconsistent

**Validity check:** Confirmed.
- Main spec §4.3 said "stored at 30 s (read at 10 s, downsampled)"
- `profile-schema.md` §10 said "MVP stores at the block cadence; downsampling happens in cloud queries"
- The actual YAML stores demand metrics at the realtime cadence (10 s)

Three inconsistent stories.

**Resolution:** Aligned on **storage at block cadence (10 s)**.
- Updated main spec §4.3 — removed the "Demand sub-block, stored at 30 s" row; merged into the realtime block row with a note that demand metrics share the block cadence; per-metric storage cadences are post-MVP.
- Profile-schema.md §10 was already correct; minor wording tweak for clarity.
- YAML was already correct; no change.

### #15 — Fast Read mode not flagged

**Validity check:** Confirmed. Acuvim manual states Fast Read at `0x3000`+ suspends all other Modbus protocols. If toggled in the AXM-WEB2 web UI, our `0x0600` reads silently fail.

**Resolution:**
- Added §7.3 to [`acuvim-l-profile.md`](acuvim-l-profile.md) describing the interference and the probe-CLI sanity check.
- Confirmed [`requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md) §K already has Q7 ("Fast Read disabled?") — no change needed there.
- Probe-CLI spec already includes the cross-check (probes `0x3000` block); no change needed there either.

---

## Minor

### #9 — `version` vs `schema_version` rename

Updated [`logical-metric-catalog.md`](logical-metric-catalog.md) §5 to say `schema_version: "1.0"` — matches both the YAML and the convention used in profile YAMLs.

### #10 — `acuvim_clock` missing from format-types table

Resolved by #2 refactor. The new §6.2 explains custom decoders generally; `acuvim_clock` is a registry entry, not a schema enum value.

### #11 — Schema doesn't conditionally require `format` on fingerprint reads

Added `if/then` to [`profile.schema.json`](../../../architecture/profiles/profile.schema.json) `FingerprintRead` — `format` required unless `expect_exception` is set.

### #12 — Schema doesn't enforce metric-offset alignment

**Validity check + judgment call:** the reviewer prefers schema-level enforcement; I went with **loader-enforced + documented**. JSON Schema 2020-12 *can* express it via `if/then` matching format → `offset.multipleOf`, but verbose for the 10 format types.

**Reasoning for the judgment call:**
- The lint tool ([SOL-14](https://linear.app/solamon/issue/SOL-14)) catches alignment errors pre-PR-merge.
- The loader catches them at startup with a clear error.
- Same effective outcome with simpler schema.

If SOL-14 wants schema-level pre-load checks for editor support, easy to add then. Documented as loader-enforced in [`profile-schema.md`](profile-schema.md) §6.3.

### #13 — `MetricMapping.length` unit was undefined

Updated all `length` field descriptions in the schema to "Length in 16-bit registers (each 2 bytes)" — consistent across `ReadBlock`, `FingerprintRead`, `Identifier`, `MetricMapping`, and `readback_register`.

### #14 — Catalog metric count off

Was "~40", actual was 60+. After the #7 drops, it's ~55. Updated [`logical-metric-catalog.md`](logical-metric-catalog.md) §6 acceptance criterion.

### #16 — Peak demand is unsigned

Added a comment block in [`acuvim_l.yaml`](../../../architecture/profiles/acuvim_l.yaml) `peak_demand` block and an explanatory paragraph in [`acuvim-l-profile.md`](acuvim-l-profile.md) §5.4. Acuvim normally reports `|max|` so it's a non-issue in practice; flagged for awareness.

### #17 — `load_type` enum keys are integers

Resolved by #7 (load_type dropped). The new [`logical_metrics.schema.json`](../../../architecture/logical_metrics.schema.json) requires string keys for `enum_values` (regex `^[0-9]+$`), so any future enum metric will fail validation if it tries integer keys.

---

## Summary

- **17 findings, 17 addressed.** No blind acceptance — each was validated against the source.
- **One judgment call** (#12 — loader-enforced over schema-enforced alignment) explained.
- **Two new Linear issues** ([SOL-22](https://linear.app/solamon/issue/SOL-22), [SOL-23](https://linear.app/solamon/issue/SOL-23)) filed for the architectural deferrals (push profiles, derived metrics).
- **Core artifact changes:** `acuvim_l.yaml` got 17 scale fixes + custom-decoder swap; `profile.schema.json` got the format-type refactor + conditional fingerprint rule + length-unit alignment; `logical_metrics.yaml` lost 4 orphans; new `logical_metrics.schema.json` created.
- **Core doc changes:** all four device-library specs updated; main spec §4.3 + §6.2 corrected.

The biggest single risk identified — **#1 (units)** — now has its own bench Day 3 verification step and a clear remediation if the manual is wrong about the unit. The implementer (or whoever runs the bench) commits the empirical answer back into [`acuvim-l-profile.md`](acuvim-l-profile.md) §7.4.
