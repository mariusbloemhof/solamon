# CLAUDE.md — Solar Monitor Project Context

This file is auto-loaded by Claude Code. It gives any Claude instance full working context for this project without re-reading every document.

---

## Project Identity

**Client:** Johan Wolmarans — solar energy business, South Africa  
**Consultant:** Marius Bloemhof — software architect, technical lead  
**Repo:** github.com/mariusbloemhof/solamon  
**Phase:** Discovery complete → Architecture drafted → Awaiting Johan Q&A → PRD next

Johan's business model: owns and installs solar PV + BESS systems at commercial/industrial client sites; clients pay for energy and services delivered. He needs software to scale the business.

**Three objectives — everything traces back to these:**
1. **Remote Monitoring** — live + historical telemetry from all devices at all sites
2. **Billing / Metering** — automated invoice generation from revenue-grade Acuvim L data
3. **Remote Control** — mode switching, setpoints, start/stop with full audit trail

---

## Workspace Layout

```
discovery/          Device research — specs, SLD diagrams, source PDFs
  specs/            Per-device Modbus/protocol specifications
  documents/        Original source PDFs and SLD images from Johan
architecture/       System architecture and data model (drafts v0.1)
  data-model/
requirements/       Questions for Johan (PRD not yet started)
OVERVIEW.md         Project purpose, scope, architecture summary — human entry point
README.md           Repo front door with navigation links
CLAUDE.md           This file
```

---

## Architecture Decisions — Already Made, Do Not Relitigate

### System layers
Three-layer model: **Edge → Cloud → App**. Edge agent per site polls Modbus TCP devices on site LAN, buffers locally, forwards to cloud via MQTT. Acuvim L pushes directly to cloud via MQTT (no edge agent involvement for billing data).

### Aggregation hub principle
**Do not integrate sub-devices directly when a hub exists.** This collapses the integration surface from 14 devices to 7 endpoints:

| Endpoint | What it covers | Protocol |
|----------|---------------|---------|
| Huawei SmartLogger `:502` | ALL Huawei: SUN2000 PV inverters, Luna PCS, LUNA2000B batteries, connected BMS | Modbus TCP |
| AccuEnergy Acuvim L / AXM-WEB2 | Revenue-grade billing meter | MQTT push (primary), Modbus TCP (fallback) |
| Sinexcel PWS1-500K `:502` | 500kW BESS PCS + connected BMS (Poweroad/CATL via CAN pass-through) | Modbus TCP (or via MOXA if RS485) |
| EPC Power CAB1000 `:502` | BESS PCS + battery cabinets | Modbus TCP via Lantronix gateway |
| Schneider PM5110 `:502` | Secondary energy meter | Modbus TCP via MOXA NPort (RS485 bridge) |
| Deep Sea DSE8610 MK2 `:502` | Generator controller | Modbus TCP (native, no add-on) |
| PPC | Grid compliance controller | **TBD — pending Johan** |

**Not directly integrated:** Individual Huawei inverters/batteries (→SmartLogger), Poweroad/CATL BMS (→Sinexcel CAN pass-through), EPC battery cabinets (→CAB1000 internal), MOXA NPort (transparent gateway, not a data source).

### Billing data
**Acuvim L is the only billing source — never derive billing from polling other devices.** If Acuvim L is unavailable, the AXM-WEB2 stores 3 GB locally and replays on reconnection. EnergyInterval records are immutable once written; corrections go through EnergyAdjustment, never overwrites.

### User tiers
Two tiers, different API surfaces:
- **Operations** (Johan's team): full access — raw telemetry, control, billing admin, device management
- **Client** (Johan's customers): aggregated read-only — usage summary + invoice history only. Never exposes raw `Reading` records or device-level data to clients.

### Other confirmed decisions
- **Multi-site from day 1** — 1 to N sites, no single-site special casing
- **Dashboard refresh:** 5 min default, configurable, minimum floor ~30 s — not a real-time SCADA system
- **Edge poll rate** is decoupled from dashboard refresh: power/alarms at 10 s, SOC/temp at 30 s, energy counters at 60 s
- **Storage:** TimescaleDB (PostgreSQL + time-series extension) — single DB, two schemas (`timeseries` hypertables + `app` relational)
- **Control commands** are verified by read-back (write → wait 500 ms → read back → confirm or alert). Every command logged in immutable audit trail.
- **Store-and-forward:** 72-hour local buffer at edge; site offline does not lose billing data (AXM-WEB2 cache)

---

## Key Device Technical Facts (Implementation-Ready)

### Huawei SmartLogger V300R024C00SPC200
- Modbus TCP port 502, Unit ID 0
- 166 RO/RW registers documented in `discovery/specs/` (via SmartLogger PDF)
- Key registers: SOC=40515, SOH=40516, Active power=40525, Working mode=42256 (RW)
- Working mode values: 0=no ctrl, 2=max self-consumption, 4=full grid feed, 5=TOU, 6=grid dispatch
- Control: Active power adjust=40420/40428/40430; Grid connection=44376 (0=on-grid, 1=off-grid)

### AccuEnergy Acuvim L + AXM-WEB2
- Full spec: `discovery/specs/acuvim_l_modbus_registers.md` + `acuvim_l_axm_web2_configuration.md`
- Modbus TCP port 502, Float32 measurements at 0x0600+, energy at 0x0156+, TOU at 0x0200+
- MQTT: JSON push, topic configurable, QoS 1, TLS on port 8883, LWT supported
- MQTT payload: `{gateway: {id, name}, device: {id, name}, readings: [{name, value, unit}]}`
- Revenue-grade: Class 0.2/0.5, TOU 4 tariffs × 12 seasons × 14 schedules, 3 GB offline cache

### Sinexcel PWS1-500K
- Full spec: `discovery/specs/sinexcel_pws1_500k_protocol.md`
- Modbus TCP port 502 (or RS485 via MOXA; baud 9600/19200)
- **SunSpec Model 103** at register 500 (SunSpec ID at 500, measurements 572–622)
- **Proprietary measurements** at 101–148: AC voltage/current/power/PF/energy, DC power/voltage/current
  - Register 122 = Total 3-phase active power (signed, 0.01 kW, negative = charging)
  - Registers 126–129 = AC charge/discharge energy (uint32, resettable)
- **Power setpoints:** Register 135 = active power setpoint (0.01 kW), 136 = reactive
- **Command registers 650–658:** 650=Start, 651=Stop, 652=ClearFault, 653=OnGrid, 654=OffGrid, 655=Standby, 656=Restart, 657=GridStop
- **Module-based control (PWS1-500K specific):** 53900=Start all, 53901=Stop all, 53903=ClearFault all
- **53622 = AC active power setpoint — units: 10W per count** (write 50000 = 500 kW discharge, −50000 = 500 kW charge)
- **Network config registers 300–333:** IP/mask/gateway (300–311), Modbus addr (316), baud (320), interface (325), EMS timeout watchdog (327), BMS timeout (329), grid mode (331)
- **OpenEMS cross-validates** FC3 read blocks: 1–31, 32–47, 101–148, 224–333, 650–658, 748–894, 934–967
- **DEIF v1517 note:** firmware v1517 changed voltage/frequency offset register addresses — confirm firmware version on Johan's units before production

### EPC Power CAB1000
- Full spec: `discovery/specs/epc_power_cab1000_status.md`
- Modbus TCP via **Lantronix serial-to-Ethernet gateway**, DHCP, port 502
- **Static +20,000 register address offset** — all registers start at ~20001 (confirmed via `epcpower/pm` on GitHub)
- **SunSpec model 65534** (vendor-specific extension) — `smdx_65534.xml` contains register definitions
- GitHub org: `github.com/epcpower` (12 repos: `sunspec-demo`, `pm`, `st`/EPyQ)
- Known control point names (from `smdx_65534.xml`): `CmdRealPwr`, `CmdReactivePwr`, `CmdV`, `CmdHz`, `CtlSrc`, `St`, `StVnd`, `FltClr`
- CAN J1939 internal: CommandPower `0x0CFFAC41` ±90,000 W
- **Actual register addresses still unknown** — need Eaton xStorage I/O manual P-164001236 OR run `get-models.py` from `epcpower/sunspec-demo` against a live device

### Schneider PM5110
- Full spec: `discovery/specs/schneider_pm5110_modbus_register_map.md`
- RS485 only (no native Ethernet) — must use MOXA NPort gateway
- Default: 8E1, 19200 baud, Modbus address 1
- Current at 3000–3018, Voltage at 3020–3052, Power at 3054–3076, Energy FLOAT32 at 2700–2722
- Demand at 3764–3882, THD at 21300+, Alarms at 2421/2423/2441

### Deep Sea DSE8610 MK2
- Full spec: `discovery/specs/dse8610_gencomm_register_map.md`
- Native Modbus TCP (no add-on module needed), default unit ID 10
- **GenComm address formula:** `(Page × 256) + Offset`
- Engine state: reg 772, AC output: 1031–1057, Alarms: 39425–39445
- Alarm decode: each register holds 4 two-bit alarm states (0=none, 1=warning, 2=shutdown, 3=electrical trip)

---

## Data Model Key Points

Full spec: `architecture/data-model/DATA_MODEL.md`

- **Reading** (TimescaleDB hypertable): all telemetry, partition key = `time`, index on `(device_id, metric_key, time DESC)`
- **EnergyInterval** (TimescaleDB hypertable): 15-min billing buckets from Acuvim L, store Wh as `bigint` (tenths of Wh) — no float rounding
- **EnergyAdjustment**: immutable correction records — never overwrite EnergyInterval
- **ClientUsageSummary**: materialised view — pre-aggregated, what client portal API serves. Clients never touch `Reading` table directly.
- **ControlCommand**: every device command — status tracks `pending → sent → acknowledged → confirmed/failed`
- Retention: raw readings 90 days → compress; 15-min aggregates 7 years; audit log = never delete

---

## Outstanding Gaps

### Device specs (technical research)
| Gap | Action |
|-----|--------|
| EPC CAB1000 actual register addresses | Download Eaton xStorage I/O manual P-164001236 in browser; or run `get-models.py` against live unit |
| Sinexcel PWS1 500K vs 30K register confirmation | Request module protocol spreadsheet: sinexcel.us/wiki or +86 0755-8651-1588 |
| Sungrow MBB register map | Research once model confirmed by Johan |
| MOXA NPort model numbers | Ask Johan (see QUESTIONS_FOR_JOHAN.md) |

### Business requirements (pending Johan Q&A)
See `requirements/QUESTIONS_FOR_JOHAN.md` for full structured list. Critical blockers:

| Question | Why critical |
|----------|-------------|
| **PPC make/model** | Could collapse control architecture to 1 endpoint — or add significant complexity |
| What energy flows are billed | Determines which Acuvim L registers feed billing engine |
| Tariff structure (flat/TOU/demand) | Determines billing engine complexity |
| MOXA NPort model numbers | RS485 gateway configuration |
| Sungrow MBB model | Determines if Sungrow is in v1 scope |
| Regulatory/retention requirements | Determines data retention policy |

---

## Conventions

- All documentation in Markdown
- Device spec files: `discovery/specs/<device>_<detail>.md`
- Architecture docs: `architecture/`
- Requirements: `requirements/`
- No implementation code yet — this repo is currently design/documentation only
- Branch: `master`, remote: `github.com/mariusbloemhof/solamon`
- Commit messages: descriptive, include co-author line for Claude
