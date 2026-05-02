# Acuvim L profile

**Spec group:** [device-library](README.md)
**Linear:** [SOL-20](https://linear.app/solamon/issue/SOL-20)
**Machine artifact:** `architecture/profiles/acuvim_l.yaml`

The concrete profile mapping the [logical metric catalog](logical-metric-catalog.md) onto the AccuEnergy Acuvim L's Modbus register space, conforming to the [profile schema](profile-schema.md). This is the first profile and the only one shipped in MVP. Both bench unit and prospect-site unit are confirmed Acuvim L by Johan.

---

## 1. Source-of-truth references

- Acuvim L user manual V2.0.3 (December 2025): https://www.accuenergy.com/wp-content/uploads/Acuvim-L-Panel-Submeter-Power-Energy-Meter-User-Manual1030E2202.pdf
- Repo register reference: [`discovery/specs/acuvim_l_modbus_registers.md`](../../../discovery/specs/acuvim_l_modbus_registers.md)
- Register scope confirmation doc (Johan-facing): [`requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md)

## 2. Sub-variants covered

The Acuvim L family has six sub-variants:

| Variant | Comms? | Use in this project |
|---------|--------|----------------------|
| `AL`, `BL` | None | Out of scope (no comms port) |
| `CL`, `DL`, `KL` | RS-485 | Covered by this profile (Modbus map identical) |
| `EL` | RS-485 + TOU support | Covered by this profile + TOU energy registers (deferred until billing engine ships) |

The Modbus register map is identical across `CL` / `DL` / `EL` / `KL`. Sub-variant only affects which physical I/O is wired and (for `EL`) whether TOU energy registers are populated. Capture the sub-variant at commissioning from the device label, not from the wire — there is no register that distinguishes them.

## 3. Connection details

```yaml
connection:
  protocol: modbus_tcp
  default_port: 502
  default_unit_id: 1
```

Modbus TCP via the AXM-WEB2 communication module. If AXM-WEB2 is not fitted, the meter is RS-485 only and we need a MOXA NPort gateway in front — that's a separate site-specific connection adjustment, not a profile change.

## 4. Fingerprint strategy

The Acuvim L manual V2.0.3 documents **no identity registers** on the wire — no manufacturer code, model code, firmware version, or serial number is exposed via Modbus. So we cannot positively identify an Acuvim L by reading an ID register. Instead we use a **negative fingerprint** (the SunSpec common-model block at `0xC350` exists on Acuvim II but NOT on Acuvim L) combined with **positive capability probes** (registers known to exist on Acuvim L with sane expected values).

```yaml
fingerprint:
  reads:
    # Negative: SunSpec common-model block must NOT exist on Acuvim L
    - address: 0xC350
      length: 2
      expect_exception: 0x02       # illegal data address

    # Positive: secondary frequency register exists, returns 50.00 Hz × 100 = 5000
    - address: 0x0130
      length: 1
      format: uint16
      expected_range: [4500, 6500] # 45.00–65.00 Hz raw

    # Positive: comms address echoes (sanity)
    - address: 0x0101
      length: 1
      format: uint16
      expected_range: [1, 247]     # Modbus slave address range

  identifiers: []                  # No identifier registers on Acuvim L; capture serial / firmware / sub-variant from the device label or AXM-WEB2 web UI at commissioning
```

The probe CLI ([SOL-18](https://linear.app/solamon/issue/SOL-18)) cross-checks against the Acuvim II `0x4000`+ block to definitively answer Johan's "the II map works on the L" question on bench Day 3.

## 5. Read blocks

Five blocks at distinct cadences to balance freshness vs. Modbus traffic.

### 5.1 `realtime` — every 10 s — `0x0600`–`0x0649` (74 registers, Float32)

The primary Float32 measurement block. Single FC03 batched read; 30+ metrics decoded by offset. **No scaling required** — Acuvim returns Float32 in engineering units.

| Offset | Register | Logical metric | Format | Notes |
|--------|----------|----------------|--------|-------|
| 0  | `0x0600`-`0x0601` | `frequency_hz`         | float32_be | |
| 4  | `0x0602`-`0x0603` | `voltage_l1_n`         | float32_be | |
| 8  | `0x0604`-`0x0605` | `voltage_l2_n`         | float32_be | |
| 12 | `0x0606`-`0x0607` | `voltage_l3_n`         | float32_be | |
| 16 | `0x0608`-`0x0609` | `voltage_l1_l2`        | float32_be | |
| 20 | `0x060A`-`0x060B` | `voltage_l2_l3`        | float32_be | |
| 24 | `0x060C`-`0x060D` | `voltage_l3_l1`        | float32_be | |
| 28 | `0x060E`-`0x060F` | `current_l1`           | float32_be | |
| 32 | `0x0610`-`0x0611` | `current_l2`           | float32_be | |
| 36 | `0x0612`-`0x0613` | `current_l3`           | float32_be | |
| 40 | `0x0614`-`0x0615` | `current_neutral`      | float32_be | |
| 44 | `0x0616`-`0x0617` | `active_power_l1`      | float32_be | Sign per catalog convention |
| 48 | `0x0618`-`0x0619` | `active_power_l2`      | float32_be | |
| 52 | `0x061A`-`0x061B` | `active_power_l3`      | float32_be | |
| 56 | `0x061C`-`0x061D` | `active_power_total`   | float32_be | **Hero KPI** |
| 60 | `0x061E`-`0x061F` | `reactive_power_l1`    | float32_be | |
| 64 | `0x0620`-`0x0621` | `reactive_power_l2`    | float32_be | |
| 68 | `0x0622`-`0x0623` | `reactive_power_l3`    | float32_be | |
| 72 | `0x0624`-`0x0625` | `reactive_power_total` | float32_be | |
| 76 | `0x0626`-`0x0627` | `apparent_power_total` | float32_be | |
| 80 | `0x0628`-`0x0629` | `power_factor_l1`      | float32_be | Sign-aware |
| 84 | `0x062A`-`0x062B` | `power_factor_l2`      | float32_be | |
| 88 | `0x062C`-`0x062D` | `power_factor_l3`      | float32_be | |
| 92 | `0x062E`-`0x062F` | `power_factor_total`   | float32_be | |
| 96 | `0x0630`-`0x0631` | `voltage_unbalance_pct`| float32_be | |
| 100| `0x0632`-`0x0633` | `current_unbalance_pct`| float32_be | |
| 108| `0x0636`-`0x0637` | `apparent_power_l1`    | float32_be | |
| 112| `0x0638`-`0x0639` | `apparent_power_l2`    | float32_be | |
| 116| `0x063A`-`0x063B` | `apparent_power_l3`    | float32_be | |
| 124| `0x063E`-`0x063F` | `apparent_power_demand`| float32_be | Demand metrics share the realtime read but storage cadence is 30 s (downsampled) |
| 128| `0x0640`-`0x0641` | `active_power_demand`  | float32_be | |
| 132| `0x0642`-`0x0643` | `reactive_power_demand`| float32_be | |
| 136| `0x0644`-`0x0645` | `current_demand_l1`    | float32_be | |
| 140| `0x0646`-`0x0647` | `current_demand_l2`    | float32_be | |
| 144| `0x0648`-`0x0649` | `current_demand_l3`    | float32_be | |

**Skipped offsets** at 104 (`0x0634`-`0x0635`) and 120 (`0x063C`-`0x063D`) are reserved/unused per the manual; we read but don't decode them.

### 5.2 `energy` — every 60 s — `0x0156`–`0x015F` (10 registers, Dword)

Cumulative energy counters. Read with `dword_high_first` format (AccuEnergy convention). **Scaling: × 0.1** to get kWh / kvarh / kVAh.

| Offset | Register | Logical metric | Format | Scale |
|--------|----------|----------------|--------|-------|
| 0 | `0x0156`-`0x0157` | `import_active_energy_kwh`     | dword_high_first | 0.1 |
| 4 | `0x0158`-`0x0159` | `export_active_energy_kwh`     | dword_high_first | 0.1 |
| 8 | `0x015A`-`0x015B` | `import_reactive_energy_kvarh` | dword_high_first | 0.1 |
| 12| `0x015C`-`0x015D` | `export_reactive_energy_kvarh` | dword_high_first | 0.1 |
| 16| `0x015E`-`0x015F` | `apparent_energy_kvah`         | dword_high_first | 0.1 |

### 5.3 `power_quality` — every 60 s — `0x0400`–`0x0405` (6 registers, Word)

THD totals. **Scaling: × 0.01** to get percent (raw is `(value / 10000) × 100`, equivalent to `value × 0.01`).

| Offset | Register | Logical metric | Format | Scale |
|--------|----------|----------------|--------|-------|
| 0  | `0x0400` | `thd_voltage_l1` | uint16 | 0.01 |
| 2  | `0x0401` | `thd_voltage_l2` | uint16 | 0.01 |
| 4  | `0x0402` | `thd_voltage_l3` | uint16 | 0.01 |
| 6  | `0x0403` | `thd_current_l1` | uint16 | 0.01 |
| 8  | `0x0404` | `thd_current_l2` | uint16 | 0.01 |
| 10 | `0x0405` | `thd_current_l3` | uint16 | 0.01 |

### 5.4 `peak_demand` — every 300 s — `0x1024`–`0x1027` (4 registers)

Per the spec doc, the peak active power demand entry is 4 registers: 2 for the Dword value, 2 for the timestamp (date HH+LL packed). For MVP, we read only the value (offset 0) and let the cloud add a `received_at` timestamp; decoding the meter's internal timestamp is post-MVP.

| Offset | Register | Logical metric | Format | Scale |
|--------|----------|----------------|--------|-------|
| 0 | `0x1024`-`0x1025` | `active_power_demand_max` | dword_high_first | 1.0 |

### 5.5 `clock` — every 3600 s — `0x0184`–`0x018A` (7 registers)

The meter's internal RTC. Compared against Pi NTP for drift detection.

| Offset | Register | Logical metric | Format | Notes |
|--------|----------|----------------|--------|-------|
| 0 | `0x0184`-`0x018A` | `meter_clock` | acuvim_clock | Custom decoder: 7 words → datetime (YYYY-MM-DD HH:MM:SS, day-of-week ignored) |

`acuvim_clock` is a one-off custom format defined for this profile. It packs Year / Month / Day / Hour / Minute / Second / DoW each as a uint16. The profile loader recognises `acuvim_clock` as a profile-local format extension; future devices needing date decoding should reuse this format type or the loader gets a registry of named decoders.

### 5.6 `config` — startup + every 3600 s — `0x0103`–`0x0109` (mixed)

Read-once at startup, re-read hourly to detect mid-life config changes.

| Offset | Register | Logical metric | Format | Notes |
|--------|----------|----------------|--------|-------|
| 0  | `0x0103` | `voltage_wiring_type` | uint16 | enum: 0=3LN, 1=3LL, 2=2LL, 3=1LN, 4=1LL |
| 2  | `0x0104` | `current_wiring_type` | uint16 | enum: 0=3CT, 1=2CT, 2=1CT |
| 4  | `0x0105`-`0x0106` | `pt_ratio_primary` | dword_high_first | scale 0.1 (manual quotes 50.0–1,000,000.0 V × 10 raw) |
| 8  | `0x0107` | `pt_ratio_secondary` | uint16 | scale 0.1 |
| 10 | `0x0108` | `ct_ratio_primary` | uint16 | scale 1.0 (1–50,000 A) |
| 12 | `0x0109` | `ct_ratio_secondary` | uint16 | scale 1.0 (1, 5, or 333 mV) |

Note the config block runs `0x0103`-`0x0109` which is 7 consecutive registers — but `pt_ratio_primary` is a Dword spanning `0x0105`-`0x0106` so length = 7 covers it.

## 6. Control register — demand window

```yaml
control:
  demand_window_minutes:
    fc: 6                              # write single register
    address: 0x010C
    format: word
    allowed_values: [1, 5, 10, 15, 30]
    readback_register:
      address: 0x010C
      offset: 0
      format: word
    readback_delay_ms: 500
```

The MVP control demo target. Operator picks 1/5/10/15/30 from the dashboard control panel; agent issues FC06 write to `0x010C`; sleeps 500 ms; reads back; confirms or fails. State machine in main spec §10.

## 7. Open empirical question — `0x0600` vs `0x4000`

Johan reports that the Acuvim II Modbus map (which uses `0x4000`+ for real-time measurements) "works on the Acuvim L". AccuEnergy's official docs disagree — Acuvim L uses `0x0600`+, Acuvim II uses `0x4000`+. The profile above commits to the documented `0x0600` block.

**To be resolved on bench Day 3** via `solamon-probe`, which reads BOTH `0x0600` and `0x4000` from the same Acuvim L, sanity-checks values against a multimeter, and reports findings. Three possible outcomes:

1. Both blocks return identical, sensible Float32 → firmware aliases the blocks; pick `0x0600` (better-documented); note the alternative as fallback.
2. `0x0600` returns sensible, `0x4000` returns garbage / exception → the profile above is correct; Johan's home flow has been reading nonsense; recommend he correct it.
3. `0x0600` errors and `0x4000` works → atypical L variant; rebase the profile to `0x4000`.

The probe CLI captures this in its report; whoever runs Day 3 commits the empirical answer to this doc as a footnote.

## 8. Acceptance criteria

- `architecture/profiles/acuvim_l.yaml` exists, parses against `profile.schema.json`, all metrics referenced exist in `architecture/logical_metrics.yaml`.
- All five read blocks above are populated with the offsets / formats / scales documented here.
- The control register entry validates a `set_demand_window` command with parameter 30 (and rejects parameter 25).
- The fingerprint matches against a real Acuvim L (verified on bench Day 3).
- The fingerprint does NOT match against an Acuvim II (verified by running the same fingerprint against an Acuvim II — even one in a virtual / simulated form).

## 9. Cross-references

- [`logical-metric-catalog.md`](logical-metric-catalog.md) — defines every `logical:` key referenced above
- [`profile-schema.md`](profile-schema.md) — the schema this profile conforms to
- [`discovery/specs/acuvim_l_modbus_registers.md`](../../../discovery/specs/acuvim_l_modbus_registers.md) — the underlying register reference
- [`discovery/specs/acuvim_ii_modbus_registers.md`](../../../discovery/specs/acuvim_ii_modbus_registers.md) — the SunSpec block at `0xC350` that drives our negative fingerprint
- [`requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md) — the Johan-facing checklist that drives dashboard cards and confirms the register selection
