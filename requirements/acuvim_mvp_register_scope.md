# Acuvim — MVP Register Scope & Dashboard Confirmation

**For Johan to verify and amend.**

Below is every Acuvim Modbus register we believe is relevant for the MVP, plus an explicit recommendation per register on whether it shows up on the dashboard, what we plan to read but not display, and which registers we'll write to for the control demo. Marius's proposal is in the **📊 Dashboard?** column. Use the **✏️ Johan** column (or just mark up the doc) to confirm, override, or call out anything missing.

**Source of register addresses:** [`discovery/specs/acuvim_l_modbus_registers.md`](../discovery/specs/acuvim_l_modbus_registers.md), built from the Acuvim-L Series User Manual V2.0.3 (December 2025).

**Date:** 2026-05-02 · **Owner:** Marius

---

## ⚠️ Open empirical question on the Acuvim L register space

> **Confirmed (Johan, 2026-05-02):** Both the bench unit and the prospect-site unit are **Acuvim L** — not Acuvim II. So MVP ships only `acuvim_l.yaml`; the `acuvim_ii.yaml` profile is deferred until we encounter that hardware.
>
> **Curious (Johan, 2026-05-02):** Johan reports that *"the Modbus map for Acuvim II works on the Acuvim L"* — i.e., the `0x4000` block (which AccuEnergy documents as Acuvim II–specific) reads successfully on his Acuvim L meters. His existing Node-RED flow at home points at `0x4000`.
>
> **Why this is technically suspicious** — three independent sources (AccuEnergy's two product manuals + the Aggsoft data-logger vendor's documentation) describe **different** register blocks for the two product lines: Acuvim L primary Float32 at `0x0600`–`0x064B`; Acuvim II primary Float32 at `0x4000`–`0x4047`. For Johan's claim to be right, AccuEnergy would have unified the firmware silently while keeping separate manuals. Possible but unusual.
>
> **More-likely explanation** — Johan's existing flow has two compensating bugs invisible on single-phase home load:
>
> 1. `scale: 100` on Float32 fields divides by 100 (Float32 is already in engineering units; **no scaling**)
> 2. `accu_S` decoded at offset 88, which is **Sa (Phase A apparent power)**, not **Ssum (system total)**. Ssum is at offset 100.
>
> On 3-phase C&I both bugs would be catastrophic; on single-phase home both happen to fall in plausible ranges.
>
> **Resolution: 5-minute bench test before locking the profile.** Read both `0x0600` and `0x4000` from the bench Acuvim L; compare values; cross-check against a multimeter on at least one phase. Outcome dictates which block we put in `acuvim_l.yaml` and whether Johan's home flow needs correction.
>
> The register tables below stay against the documented Acuvim L block at `0x0600` until the bench test says otherwise. **Worth flagging to Johan** that his current home flow has two bugs his single-phase setup has been hiding — easy fix once we find time.

---

## Legend for the 📊 Dashboard? column

| Symbol | Meaning |
|--------|---------|
| **✅** | **Yes, surface this on the dashboard** — we'll render it (chart / number / gauge / etc.) |
| **○** | **Read but don't display by default** — used in derived calculations (e.g., per-phase used to compute imbalance, but we may not need 3 separate charts). Easy to flip to ✅ if Johan wants. |
| **🔧** | **Read once + on-demand** — configuration; surfaced in a "wiring info" panel, not on live dashboard |
| **✏️** | **Writable / control register** — see §H |
| **⛔** | **Out of MVP scope** — deferred (listed in §I for transparency) |

---

## A. Configuration registers (R/W) — `0x0100` block

**Read pattern:** once at edge-agent startup, then re-read every hour to detect changes. Surfaced on a "Site setup" panel, not the live dashboard.

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x0103` | Voltage wiring type | enum (3LN/3LL/2LL/1LN/1LL) | 🔧 | Site setup panel | |
| `0x0104` | Current wiring type | enum (3CT/2CT/1CT) | 🔧 | Site setup panel | |
| `0x0105`–`0x0106` | PT1 primary | V | 🔧 | Site setup panel | |
| `0x0107` | PT2 secondary | V | 🔧 | Site setup panel | |
| `0x0108` | CT1 primary | A | 🔧 | Site setup panel | |
| `0x0109` | CT2 secondary | mV | 🔧 | Site setup panel | |
| `0x010C` | **Demand sliding window** | **min** | **✅ + ✏️** | **Demand card + Control panel — the control-demo target** | |
| `0x010F` | Clear-energy command | (write `0x0A` to execute) | ⛔ | Out of scope (destructive) | |

---

## B. Real-time measurements — primary Float32 block (R) — `0x0600`–`0x064B`

**Read pattern:** one batched FC03 read of `0x0600`–`0x0649` every **10 s**.
**Format:** IEEE 754 Float32 big-endian, 2 registers per value, no scaling.

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x0600`–`0x0601` | Frequency | Hz | ✅ | Frequency gauge card (50.0 Hz target, ±0.5 Hz band) | |
| `0x0602`–`0x0603` | Voltage L1-N (Va) | V | ✅ | Voltage-per-phase card (3 gauges, 207-253 V band) | |
| `0x0604`–`0x0605` | Voltage L2-N (Vb) | V | ✅ | Voltage-per-phase card | |
| `0x0606`–`0x0607` | Voltage L3-N (Vc) | V | ✅ | Voltage-per-phase card | |
| `0x0608`–`0x0609` | Voltage L1-L2 (Vab) | V | ○ | Available on detail-view; line-to-line | |
| `0x060A`–`0x060B` | Voltage L2-L3 (Vbc) | V | ○ | Detail view | |
| `0x060C`–`0x060D` | Voltage L3-L1 (Vca) | V | ○ | Detail view | |
| `0x060E`–`0x060F` | Current Ia | A | ✅ | Current-per-phase card (3 bars + neutral) | |
| `0x0610`–`0x0611` | Current Ib | A | ✅ | Current-per-phase card | |
| `0x0612`–`0x0613` | Current Ic | A | ✅ | Current-per-phase card | |
| `0x0614`–`0x0615` | Neutral current In | A | ✅ | Current-per-phase card (4th channel) | |
| `0x0616`–`0x0617` | Active power Pa | W | ✅ | Per-phase power card (3 bars showing balance) | |
| `0x0618`–`0x0619` | Active power Pb | W | ✅ | Per-phase power card | |
| `0x061A`–`0x061B` | Active power Pc | W | ✅ | Per-phase power card | |
| **`0x061C`–`0x061D`** | **Total active power Psum** | **W** | **✅** | **Hero KPI tile + main load-profile chart** | |
| `0x061E`–`0x061F` | Reactive power Qa | var | ○ | Detail view | |
| `0x0620`–`0x0621` | Reactive power Qb | var | ○ | Detail view | |
| `0x0622`–`0x0623` | Reactive power Qc | var | ○ | Detail view | |
| `0x0624`–`0x0625` | Total reactive power Qsum | var | ✅ | Q/S/PF tile (3 small numbers) | |
| `0x0626`–`0x0627` | Total apparent power Ssum | VA | ✅ | Q/S/PF tile | |
| `0x0628`–`0x0629` | Power factor PFa | — | ✅ | PF-per-phase card (3 tiles + total, sign-aware) | |
| `0x062A`–`0x062B` | Power factor PFb | — | ✅ | PF-per-phase card | |
| `0x062C`–`0x062D` | Power factor PFc | — | ✅ | PF-per-phase card | |
| `0x062E`–`0x062F` | Total power factor PFsum | — | ✅ | PF-per-phase card | |
| `0x0630`–`0x0631` | **Voltage unbalance** | **%** | ✅ | Imbalance card (numeric + 24h sparkline) | |
| `0x0632`–`0x0633` | **Current unbalance** | **%** | ✅ | Imbalance card (numeric + 24h sparkline) | |
| `0x0636`–`0x0637` | Apparent power Sa | VA | ○ | Detail view | |
| `0x0638`–`0x0639` | Apparent power Sb | VA | ○ | Detail view | |
| `0x063A`–`0x063B` | Apparent power Sc | VA | ○ | Detail view | |

---

## C. Demand registers (R) — `0x063E`–`0x0649` (in same Float32 block)

**Read pattern:** same batched read as §B, but stored at **30 s cadence** (changes slowly because the demand window is integrated over minutes).

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x063E`–`0x063F` | Apparent power demand | VA | ○ | Demand card (small) | |
| **`0x0640`–`0x0641`** | **Active power demand P_Dmd** | **W** | **✅** | **Demand card — KPI for capacity-based billing** | |
| `0x0642`–`0x0643` | Reactive power demand | var | ○ | Demand card (small) | |
| `0x0644`–`0x0645` | Phase A current demand | A | ○ | Detail view | |
| `0x0646`–`0x0647` | Phase B current demand | A | ○ | Detail view | |
| `0x0648`–`0x0649` | Phase C current demand | A | ○ | Detail view | |

---

## D. Energy counters (R/W) — `0x0156`–`0x015F`

**Read pattern:** one FC03 read every **60 s**.
**Format:** Dword (2 registers, high word first). **Scaling: `value / 10` → kWh / kVArh / kVAh.**
*(Theoretically writable to reset, but we don't ever write these in MVP — they're cumulative and we want forever-monotonic energy data for billing.)*

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| **`0x0156`–`0x0157`** | **Import active energy (Ep_imp)** | **kWh** | **✅** | **Energy-totals card (today / week / month / lifetime)** | |
| **`0x0158`–`0x0159`** | **Export active energy (Ep_exp)** | **kWh** | **✅** | **Energy-totals card (only relevant if PV present)** | |
| `0x015A`–`0x015B` | Import reactive energy | kVArh | ○ | Optional detail card | |
| `0x015C`–`0x015D` | Export reactive energy | kVArh | ○ | Optional detail card | |
| `0x015E`–`0x015F` | Apparent energy (Es) | kVAh | ○ | Optional detail card | |

---

## E. Power quality — THD totals (R) — `0x0400`–`0x0405`

**Read pattern:** one FC03 read every **60 s**.
**Format:** Word per channel. **Scaling: `(value / 10000) × 100` → percent.**

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x0400` | THD Va | % | ✅ | Power-quality card (6 bars: 3V + 3I, with healthy thresholds drawn) | |
| `0x0401` | THD Vb | % | ✅ | Power-quality card | |
| `0x0402` | THD Vc | % | ✅ | Power-quality card | |
| `0x0403` | THD Ia | % | ✅ | Power-quality card | |
| `0x0404` | THD Ib | % | ✅ | Power-quality card | |
| `0x0405` | THD Ic | % | ✅ | Power-quality card | |

---

## F. Statistics — peak demand (R) — `0x1024`–`0x103B`

**Read pattern:** one FC03 read every **300 s** (5 min).
**Format:** 4 registers per entry (value HH+LL, then date/time HH+LL).

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x1024`–`0x1027` | **Maximum active power demand + timestamp** | W + ts | ✅ | Demand card — "Peak this billing period: 287 kW @ 2026-05-08 14:23" | |
| `0x1038`–`0x103B` | Maximum apparent demand + timestamp | VA + ts | ○ | Optional sub-line on Demand card | |

---

## G. Clock (R/W) — `0x0184`–`0x018A`

**Read pattern:** one FC03 read every **3600 s** (hourly). Compared against Pi NTP-synced clock for drift detection.

| Address | Metric | Unit | 📊 Dashboard? | 💡 Where it shows | ✏️ Johan |
|---------|--------|------|---------------|-------------------|----------|
| `0x0184`–`0x018A` | Meter clock (Y/M/D/H/M/S/DoW) | datetime | ○ + ✏️ (future) | Site setup panel — shows drift vs. Pi NTP. **Future control:** "sync clock" button (out of MVP scope, listed for transparency) | |

---

## H. CONTROL REGISTERS — what we write to (✏️) {#control}

The MVP edge agent writes to **exactly one register**: `0x010C` (demand sliding window). Everything else listed here is documented for transparency — what's *theoretically* controllable on the Acuvim, what we explicitly are *not* doing in MVP, and what's a candidate for follow-up control demos.

| Address | Function | MVP scope? | Notes |
|---------|----------|-----------|-------|
| **`0x010C`** | **Demand sliding window (1–30 min)** | **✅ in MVP** | The control demo. Operator picks 1/5/10/15/30 min from a dropdown; edge agent does FC06 write + 500 ms wait + read-back verify; cloud confirms. Reversible. Non-destructive. |
| `0x0184`–`0x018A` | Set meter clock | ○ Future | Sync meter clock from cloud NTP. Easy to add as a second control demo if Johan wants. |
| `0x010F` | Clear/reset energy counters | ⛔ NEVER in MVP | Destructive; lose cumulative energy. Don't ever expose this from the cloud. |
| `0x0156`+ | Write energy counters | ⛔ NEVER in MVP | Same risk as above. |
| `0x0103`–`0x0109` | Wiring config (PT/CT ratios) | ⛔ Out of MVP | Changing these mid-life corrupts historical data. Do at commissioning only. |
| `0x0800`–`0x0AEC` | TOU schedule configuration | ⛔ Deferred to billing engine | Multi-register payload (months × seasons × schedules × tariffs). Belongs to the eventual billing module, not MVP. |
| `0x03C0`–`0x03D2` | Digital Output / Input config | ⛔ Out of scope | Assumes no AXM-IO11/IO12 module on the bench. If it's there and Johan wants a relay-click demo, easy to add — but listed as ⛔ for clarity. |

> **Why so much "out of scope" in §H:** the Acuvim L is mostly a measuring device. Most of its writable surface is *configuration* that should be set at commissioning, not flicked from a cloud button. The demand-window register is the rare exception — it's reversible, has a meaningful effect on a visible KPI, and is exactly the kind of thing an operator might tweak remotely.

---

## I. Out of MVP scope — explicit deferrals

Listed for transparency so Johan can see what we're *not* including and call us out if anything is critical:

| Block | Reason |
|-------|--------|
| Per-phase energy counters (`0x0160`–`0x0177`) | System totals are sufficient for load assessment and billing. Per-phase becomes interesting for unbalanced billing — full system. |
| TOU energy registers (`0x0200`–`0x0263`) | Comes online when the billing engine is built. |
| TOU configuration (`0x0800`–`0x0AEC`) | Same — billing engine. |
| Statistics min/max for V&I (`0x1000`–`0x1023`, `0x103C`+) | We cover the demand peaks; V/I peaks are nice-to-have but not load-relevant in MVP. |
| Individual harmonic orders (`0x0406`–`0x04B9`) | Total harmonic distortion percentages are sufficient to flag bad supply or non-linear load issues; per-order analysis is a follow-on. |
| Run time counters (`0x0180`–`0x0183`) | Informational; not load-relevant. |
| TOU error status (`0x080E`) | TOU isn't enabled in MVP. |
| Digital Output / Digital Input registers (`0x03C0`–`0x03D2`) | No DO/DI module assumed on bench. Easy add if present. |

---

## J. Proposed dashboard card layout

This is the **rich, detailed** view — every metric we ingest is reflected somewhere. No abstracted health scores; numbers and charts are visible directly so anomalies are seen, not summarised.

### Page: Load Assessment (the primary view)

**Hero row — instantaneous totals**
- **Active power tile** — large number (Psum kW) + 60-second sparkline + min/avg/max-this-hour underneath
- **Energy today tile** — kWh import / kWh export (delta vs yesterday under each)
- **Demand tile** — current P_Dmd (kW) + peak-this-period with timestamp + small "Configure window" link to control panel (currently set to: e.g. 15 min)

**Per-phase detail row**
- **Voltage card** — three numeric tiles (Va, Vb, Vc) with healthy band 207-253 V drawn as a band on each; numbers turn amber outside band, red >5% out
- **Current card** — three bars (Ia, Ib, Ic) plus a fourth thin bar for In (neutral); bars colored by relative magnitude
- **Per-phase active power card** — three bars (Pa, Pb, Pc) showing balance at a glance
- **Power factor card** — four numeric tiles (PFa, PFb, PFc, PFsum), with sign indicator (e.g., "+0.92" vs "−0.78"). **A different sign on one phase ⇒ CT polarity flipped on that phase** — visible at a glance

**Power quality row**
- **Imbalance card** — V-unbalance % (numeric + 24h sparkline) and I-unbalance % (numeric + 24h sparkline), thresholds drawn at 2 % and 5 %
- **Frequency card** — large gauge centred on 50.0 Hz with healthy band 49.5–50.5 Hz; numeric min/max-last-hour
- **THD card** — six bars (THD Va/b/c, THD Ia/b/c) with "<5 % healthy" line drawn for V and reference line for I
- **Edge health card** — Modbus reads/min, Modbus errors/min, last successful read (relative time), Pi heartbeat (relative time), local buffer depth (rows pending publish)

**Time-series chart (the main canvas)**
- Big chart of Psum over time, with toggleable overlays: Pa/b/c, Q/S, PF; window selector 1h / 6h / 24h / 7d; demand peaks marked with vertical lines

**Side panel: Site setup (collapsible)**
- Voltage wiring type, current wiring type, PT1/PT2 ratio, CT1/CT2 ratio, demand window setting (with "edit" link to control panel), last-config-read time

### Page: Control panel

- **Demand window** — dropdown with allowed values (1, 5, 10, 15, 30 min); current value clearly shown; "Apply" button
- **Live status** of last command — "Issued 14:32:01 → Sent 14:32:02 → Acked by edge 14:32:02 → Confirmed (read-back: 30 min) 14:32:03"
- **Audit list** — last 20 control commands with operator, timestamp, parameters, status, read-back value

---

## K. Questions for Johan

1. ~~Meter model on the bench~~ — **Confirmed Acuvim L** (both bench and prospect site).
2. **Acuvim L model variant on the bench** — `CL` / `DL` / `EL` / `KL`? (`AL` and `BL` have no comms port and are out of scope.) The variants differ only in physical I/O hardware; the Modbus register map is identical across all comms-capable variants. **Why we still ask:** the variant determines what *features* are physically usable (e.g., `EL` adds TOU support). At Modbus level we can't tell them apart, so it goes on the Site setup record at commissioning — usually from the physical label or the AXM-WEB2 web UI.
3. **AXM-WEB2 module fitted?** Confirms native Ethernet path. If not, we need MOXA NPort + RS485.
3. **Voltage wiring** — 3LN (3-phase 4-wire)? Or different?
4. **Modbus TCP IP address** on the LAN — default `192.168.1.254`. Same on the bench unit?
5. **Modbus TCP port** — default `502`. Same?
6. **Acuvim L Modbus slave address** — default `1`. Same?
7. **Fast Read mode** — disabled? (Recommend keeping disabled for MVP — 100 ms updates are overkill and disable other protocols.)
8. **Demand sliding window currently configured to** — what value (1 / 5 / 10 / 15 / 30 min)? This is our "before" reference for the control demo.
9. **PT and CT ratios** Johan has configured — we read these on startup; want him to confirm them so we can flag if they ever change unexpectedly.
10. **Anything missing?** — if there's a register from the spec doc not listed above that he expects to see on the dashboard, call it out.
11. **DO/DI module** — does the bench Acuvim have an AXM-IO11 / AXM-IO12 expansion module? (If yes, a relay-click demo is on the table for control demo #2.)

---

## See also

- [`discovery/specs/acuvim_l_modbus_registers.md`](../discovery/specs/acuvim_l_modbus_registers.md) — full register reference
- [`discovery/specs/acuvim_l_axm_web2_configuration.md`](../discovery/specs/acuvim_l_axm_web2_configuration.md) — AXM-WEB2 communication module setup
- [`GLOSSARY.md`](../GLOSSARY.md) — domain and project terminology
