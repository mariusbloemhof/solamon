# AccuEnergy Acuvim II — Modbus TCP Register Map

**Device:** Acuvim II Series Power Meter (Acuvim II / IIR / IIE / IIW)
**Manufacturer:** AccuEnergy
**Status:** Stub — captures the `0x4000` "Basic Real-time Parameters" block from AccuEnergy's official Acuvim II documentation. **Project decision (2026-05-02):** the MVP ships against the Acuvim L profile only; this stub is preserved as future-ready reference for when an actual Acuvim II device enters the fleet.

> **Open empirical question** — Johan (Acuvim L user, two units in scope) reports the `0x4000` block reads successfully on his Acuvim L meters, contradicting AccuEnergy's product-line separation in the official manuals. To be resolved on the bench: read both `0x0600` (Acuvim L documented) and `0x4000` (Acuvim II documented) from the same meter, compare values, decide. See [`requirements/acuvim_mvp_register_scope.md`](../../requirements/acuvim_mvp_register_scope.md) "Open empirical question" section for the test plan.

**Source documents:**
- [AccuEnergy Acuvim II Power Meter User Manual (1040E1303)](https://www.accuenergy.com/wp-content/uploads/Acuvim-II-Power-Meter-User-Manual-1040E1303.pdf) — official, full reference
- [Acuvim II Modbus map — Hoyt Meter mirror](https://hoytmeter.com/content/manual/Acuvim-II-modbus.pdf) — full register reference, register table on pp. 5-6
- [AccuEnergy data scaling guide](https://www.accuenergy.com/support/acuvim-ii-user-guide/acuvim-ii-modbus-registers-data-scaling/) — official scaling formulas

**Modbus TCP port:** 502 (default)
**Function codes:** FC03 (read holding registers), FC16 (write multiple registers)
**Byte order:** Big-endian (ABCD)

---

## How this product relates to the Acuvim L

Acuvim II and Acuvim L are **different product lines** from the same vendor (AccuEnergy):

| | Acuvim L (Basic / 2x2 / V / EL / CL / AL / BL) | Acuvim II (Acuvim II / IIR / IIE / IIW) |
|---|------------------------------------------------|------------------------------------------|
| Real-time block | `0x0600`–`0x064B` (Float32) and `0x0130`–`0x0155` (scaled int) | **`0x4000`–`0x4047`** (Float32) |
| Fast Read block | `0x3000`–`0x301D` (100 ms), `0x3400`–`0x341D` (50 ms) | similar in `0x4000` range; details in manual |
| Energy registers | `0x0156`–`0x017D` (Dword × 0.1 = kWh) | **different** — see manual |
| Statistics | `0x1000`–`0x105F` | different — see manual |
| Harmonics | `0x0400`–`0x04B9` (THD + 2nd-31st orders) | different — see manual |
| AXM-WEB2 module | Yes | Yes — same module, same MQTT push behaviour |
| Accuracy class | Class 0.2 / 0.5 (revenue-grade) | Class 0.5S (revenue-grade) |

**Architectural implication:** the edge agent must be **variant-aware**. The MQTT, billing, control, and AXM-WEB2 push flows are identical — only the register addresses on the device change.

---

## Device identity — SunSpec common-model block (R) — `0xC350`–`0xC395`

**Read pattern:** one FC03 read at `0xC350` length 2 to detect the SunSpec sentinel; on success, follow up reading the rest of the block.

**Format:** Mixed — uint16 / uint32 sentinel + ASCII strings.

**Caveat:** This block depends on the AXM-WEB / AXM-WEB2 module being present. Without WEB-family firmware, the block may not be exposed.

| Address | Decimal | Field | Format | Length (regs) | Sample value |
|---------|---------|-------|--------|---------------|--------------|
| `0xC350`–`0xC351` | 50000-50001 | SunSpec sentinel | uint32 BE | 2 | `0x53756E53` (`"SunS"`) |
| `0xC352` | 50002 | SunSpec model ID | uint16 | 1 | `1` (common model) |
| `0xC353` | 50003 | Block length | uint16 | 1 | `65` |
| `0xC354`–`0xC363` | 50004-50019 | **Manufacturer** | ASCII | 16 | `"Accuenergy"` |
| `0xC364`–`0xC373` | 50020-50035 | **Model** | ASCII | 16 | `"Acuvim II"` |
| `0xC374`–`0xC37B` | 50036-50043 | **Options** (sub-variant) | ASCII | 8 | `"IIR"` / `"IIE"` / `"IIW"` |
| `0xC37C`–`0xC383` | 50044-50051 | **Version** (HW + SW) | ASCII | 8 | `"H: 2.31\nS: 3.60"` |
| `0xC384`–`0xC393` | 50052-50067 | **Serial Number** | ASCII | 16 | factory-set string |
| `0xC394` | 50068 | Device address (echo) | uint16 | 1 | Modbus slave addr |
| `0xC395` | 50069 | Wiring ID | uint16 | 1 | 201 / 202 / 203 / 204 |

**This is the canonical fingerprint block for Acuvim II identity.** Read `0xC350` first; if `"SunS"` is returned, this is Acuvim II (and AXM-WEB-family firmware is present). If a Modbus exception 0x02 (illegal data address) is returned, this is NOT Acuvim II — most likely an Acuvim L (which has no SunSpec block).

---

## Basic Real-time Parameters (R) — `0x4000`–`0x4047`

**Read pattern:** one batched FC03 read of `0x4000`–`0x4047` (72 registers = 144 bytes) to get the full block. Johan's flow reads only 51 registers (`0x4000`–`0x4032`, 102 bytes), which covers Frequency through Total Apparent Power — sufficient for MVP load assessment.

**Format:** IEEE 754 Float32 big-endian, 2 registers per value, **no scaling required** (values in engineering units when meter is in Primary Mode).

> **In Secondary Mode**, voltage and current require PT/CT ratio multiplication; power values are still kW directly. **Never** divide by 100 — see "Common pitfalls" below.

| Hex | Decimal | Symbol | Parameter | Unit | Byte offset (from base) |
|-----|---------|--------|-----------|------|-------------------------|
| `0x4000`–`0x4001` | 16384 | F | Frequency | Hz | 0 |
| `0x4002`–`0x4003` | 16386 | U1 | Phase 1 voltage (L1-N) | V | 4 |
| `0x4004`–`0x4005` | 16388 | U2 | Phase 2 voltage (L2-N) | V | 8 |
| `0x4006`–`0x4007` | 16390 | U3 | Phase 3 voltage (L3-N) | V | 12 |
| `0x4008`–`0x4009` | 16392 | Uavg | Average phase voltage | V | 16 |
| `0x400A`–`0x400B` | 16394 | U12 | Line voltage L1-L2 | V | 20 |
| `0x400C`–`0x400D` | 16396 | U23 | Line voltage L2-L3 | V | 24 |
| `0x400E`–`0x400F` | 16398 | U31 | Line voltage L3-L1 | V | 28 |
| `0x4010`–`0x4011` | 16400 | Ulavg | Average line voltage | V | 32 |
| `0x4012`–`0x4013` | 16402 | IL1 | Total Phase A current | A | 36 |
| `0x4014`–`0x4015` | 16404 | IL2 | Total Phase B current | A | 40 |
| `0x4016`–`0x4017` | 16406 | IL3 | Total Phase C current | A | 44 |
| `0x4018`–`0x4019` | 16408 | Iavg | Average phase current | A | 48 |
| `0x401A`–`0x401B` | 16410 | In | Neutral current | A | 52 |
| `0x401C`–`0x401D` | 16412 | Pa | Phase A active power | kW | 56 |
| `0x401E`–`0x401F` | 16414 | Pb | Phase B active power | kW | 60 |
| `0x4020`–`0x4021` | 16416 | Pc | Phase C active power | kW | 64 |
| **`0x4022`–`0x4023`** | **16418** | **Psum** | **Total system active power** | **kW** | **68** |
| `0x4024`–`0x4025` | 16420 | Qa | Phase A reactive power | kvar | 72 |
| `0x4026`–`0x4027` | 16422 | Qb | Phase B reactive power | kvar | 76 |
| `0x4028`–`0x4029` | 16424 | Qc | Phase C reactive power | kvar | 80 |
| **`0x402A`–`0x402B`** | **16426** | **Qsum** | **Total reactive power** | **kvar** | **84** |
| `0x402C`–`0x402D` | 16428 | Sa | Phase A apparent power | kVA | 88 |
| `0x402E`–`0x402F` | 16430 | Sb | Phase B apparent power | kVA | 92 |
| `0x4030`–`0x4031` | 16432 | Sc | Phase C apparent power | kVA | 96 |
| **`0x4032`–`0x4033`** | **16434** | **Ssum** | **Total apparent power** | **kVA** | **100** |
| `0x4034`–`0x4047` | 16436+ | (PF, PFavg, demand, etc.) | (continues — full block is 72 registers) | — | 104+ |

> **Full block extends to `0x4047`** — power factor per phase, system PF, current/voltage unbalance, and demand follow Ssum. Refer to the manual or pull on demand if/when needed.

---

## Common pitfalls (and bugs in Johan's flow we caught)

### 1. The `scale: 100` mistake

Several Node-RED flows online (including Johan's) apply `scale: 100` to the Float32 power and current values in the `0x4000` block. **This is wrong.** Acuvim II Float32 values are already in engineering units. Applying a divide-by-100 makes the values appear in the right magnitude only on **single-phase 230 V residential** loads where actual currents are ~10 A and powers ~2 kW. On any 3-phase C&I load, this fudge **under-reports by 100×.**

**Fix:** remove the `scale: 100` from voltage, current, and power in the buffer-parser. Float32 needs no scaling.

### 2. Reading "Ssum" at offset 88

Offset 88 in this block is `Sa` (Phase A apparent power), **not** `Ssum`. The system total is at offset **100** (register `0x4032`-`0x4033`). On a single-phase install where only Phase A carries load, Sa ≈ Ssum, so the bug is invisible. On 3-phase, "Ssum" read this way is **~1/3 of the real total.**

**Fix:** read 51+ registers and use offset 100 for `Ssum`.

### 3. Primary Mode vs. Secondary Mode

Acuvim II has two reporting modes set on the device:
- **Primary Mode (`U=Rx, I=Rx`)** — values returned in primary-side engineering units (the actual V on the line, the actual A through the CT primary). No PT/CT math needed.
- **Secondary Mode** — values returned in secondary-side units (the V/A actually appearing at the meter terminals, before PT/CT step-up). Multiplication by PT1/PT2 and CT1/CT2 ratios needed in software.

Always check the meter's configured mode at commissioning and document it on the site record. Mode change after commissioning will silently shift all values.

---

## What's NOT in this stub

This file documents only the **`0x4000` Basic Real-time Parameters block** — sufficient for MVP load assessment. The full Acuvim II Modbus map (config registers, energy counters, statistics, harmonics, TOU, clock, control writes) is in the [official manual](https://www.accuenergy.com/wp-content/uploads/Acuvim-II-Power-Meter-User-Manual-1040E1303.pdf). When we need any of those for a specific feature (full billing engine, control demo target on Acuvim II, etc.), pull the relevant section into this doc.

**Specifically deferred until the meter variant on the bench is confirmed:**

- Energy counter registers (Acuvim II equivalent of Acuvim L's `0x0156`)
- Demand-window control register (Acuvim II equivalent of Acuvim L's `0x010C`)
- Configuration registers (PT/CT ratios, wiring type) — equivalent of Acuvim L's `0x0103`-`0x0109`
- Statistics, harmonics, TOU, clock

If the bench unit turns out to be Acuvim II rather than Acuvim L, we extract these blocks before writing the edge agent. Otherwise our existing `acuvim_l_modbus_registers.md` stays canonical.
