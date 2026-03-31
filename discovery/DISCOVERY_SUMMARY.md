# Solar Monitor — Discovery Summary

**Date:** 2026-03-31  
**Author:** Marius Bloemhof (technical consultant)  
**Client:** Johan Wolmarans (solar energy business)

---

## 1. Business Objectives

Three-pillar value proposition for the cloud platform:

| Pillar | Description | Who Benefits |
|--------|-------------|-------------|
| **Remote Monitoring** | Live and historical visibility into all site equipment | Johan's team, clients |
| **Billing / Metering** | Revenue-grade energy data to bill clients under rental model | Johan's team, finance |
| **Remote Control** | Working mode, power setpoints, start/stop for maintenance and optimisation | Johan's team (operators) |

Johan sees the cloud integration layer as the primary value-add for software. Edge hardware will largely be purchased off-shelf.

---

## 2. Device Ecosystem

### 2.1 Devices Present on Sites

| Device | Role | Protocol | Connectivity | Coverage Status |
|--------|------|----------|-------------|----------------|
| **Huawei SmartLogger V300R024C00SPC200** | Aggregation hub for Huawei sub-system | Modbus TCP port 502 | Native Ethernet | Full — 166 RO/RW registers documented |
| **Huawei SUN2000 inverters** | PV inverters | Internal (via SmartLogger) | Via SmartLogger | Accessible via SmartLogger pass-through |
| **Huawei Luna PCS** | BESS power conversion | Internal (via SmartLogger) | Via SmartLogger | Accessible via SmartLogger |
| **Huawei LUNA2000B batteries** | Battery storage | Internal (via SmartLogger) | Via SmartLogger | SOC/SOH/SOE via SmartLogger |
| **AccuEnergy Acuvim L + AXM-WEB2** | Revenue-grade energy metering | Modbus TCP, MQTT, HTTP Push, FTP, BACnet-IP, IEC 61850 | Native dual Ethernet | Full — datasheet ingested; billing-capable |
| **Schneider PM5110** | Energy metering (secondary) | Modbus RTU/ASCII RS485 only | Via MOXA gateway | Partial — datasheet only, no register map |
| **Schneider PM3255 / PM5000** | Energy metering (secondary) | Modbus RTU RS485 | Via MOXA gateway | Not yet researched |
| **EPC Power CAB1000** | BESS inverter / PCS | Modbus TCP | Native Ethernet | Gap — no document in discovery folder |
| **Sinexcel PWS1-500K** | BESS inverter / PCS (500kW bidirectional) | Modbus RTU RS485 (default) or Modbus TCP Ethernet | RS485 or Ethernet | Partial — operating manual ingested; register map is a separate document |
| **Poweroad batteries** | Battery storage | BMS over RS485 (likely) | Via MOXA or BESS inverter | Gap — no register map |
| **CATL batteries** | Battery storage | BMS over CAN/RS485 | Via BESS inverter | Gap — no register map |
| **Deep Sea DSE8610 mk2** | Generator controller | Modbus TCP/RTU, proprietary | Ethernet capable | Gap — no register map ingested |
| **MOXA I/O devices** | RS485-to-Ethernet bridge | Transparent gateway | Native Ethernet | Configuration-only; model unknown |
| **PPC (Power Plant Controller)** | Grid compliance controller | Modbus/IEC (vendor unknown) | Ethernet | Gap — make/model unknown |
| **Sungrow (MBB units, SLD2)** | BESS (some sites) | Modbus TCP | Ethernet | Gap — not researched |

### 2.2 Protocol Summary

| Protocol | Devices | Cloud Integration Path |
|----------|---------|----------------------|
| **Modbus TCP** | SmartLogger, Acuvim L, EPC CAB1000, (Sinexcel/PM5110 via MOXA) | Edge agent polls on-site LAN |
| **Modbus RTU RS485** | Sinexcel, PM5110, PM3255, Poweroad BMS | Bridge via MOXA to Ethernet, then Modbus TCP |
| **MQTT push** | Acuvim L + AXM-WEB2 | Direct cloud push — no edge agent needed for data |
| **HTTP/HTTPS push** | Acuvim L + AXM-WEB2 | Direct cloud push webhook |
| **FTP push** | Acuvim L + AXM-WEB2 | Direct to cloud FTP receiver |
| **IEC 61850** | Acuvim L + AXM-WEB2-FOLC | Optional; relevant if integrating with utilities |
| **BACnet-IP** | Acuvim L + AXM-WEB2 | BAS integration (likely not needed) |

---

### 2.2 Sinexcel PWS1-500K — Key Technical Details (from operating manual)

**Manufacturer:** Shenzhen Sinexcel Electric Co., Ltd. (sinexcel.com)  
**Models covered:** PWS1-500K (with transformer), PWS1-500KTL / PWS1-500KTL-NA / PWS1-500KTL-EX (without transformer)  
**Rating:** 500 kW nominal, 550 kW max bidirectional  
**DC side:** 600–900 V, up to 8 battery string inputs  
**AC side:** 380/400V 3-phase, 720–760A  
**Peak efficiency:** 98.2% (TL) / 97.3% (with transformer)

**Communication interfaces:**
- **RS485** (default for EMS) — Modbus RTU, baud 9600/19200, address 1–247, terminals 9 & 10
- **Ethernet** (RJ45 on touch screen) — Modbus TCP/IP; fixed IP configured via HMI
- **CAN** (default for BMS) — terminals 7 & 8; supported brands: JUNWEI, NANDU, XIEXIN, XINWANGDA, PAINENG, GAOTE, and others
- Protocol compatibility: **SunSpec / MESA** (both RS485 and Ethernet)

**Control modes:**
- Manual Operate (local HMI control)
- Automatic Operate (autonomous start/stop on schedule/conditions)
- Remote Control (full Modbus/EMS control — settings and operation invisible on HMI in this mode)

**EMS-controllable parameters** (what the register map must expose):
- Active power setpoint: −770 to +770 kW
- Reactive power setpoint: −770 to +770 kVAr
- Power factor setpoint: −1.00 to +1.00
- Reactive power control mode: Fixed PF / Fixed Q / Volt-Var
- Active power control mode: Specified P / Volt-Watt / Freq-Watt
- Start/stop command (remote startup/shutdown)
- On-grid / Off-grid mode switch (when STS fitted)
- Clear fault command

**Monitored parameters** (HMI Info screens indicate register availability):
- DC: Voltage, Current, Power, Bus Voltage, Status, Warning, Switch state
- AC: V/I/P/Q/S/PF per phase (L1, L2, L3), Total P/Q/S, Frequency
- Charged Energy (kWh), Discharged Energy (kWh) — cumulative
- BMS: SOC, SOH, cell-level data (brand-dependent)
- Grid Info: V/I/P/Q/S/PF (only when STS module present)
- Load Info: V/I/P/Q/S/PF (only when STS module present)

**Fault/alarm categories:**
- AC bus over/under voltage, over/under frequency
- DC input over/under voltage, DC bus over/under voltage
- Battery under energy (BMS-reported)
- Parameter mismatch
- Fan/relay failure, OTP, OLP, GFDI, anti-islanding

**Note:** The operating manual does **not** include Modbus register addresses. A separate "Communication Protocol" or "Modbus Interface Definition" document must be obtained from Sinexcel.

---

## 3. Site Topology

### Network Architecture (both SLD images)

```
Internet
    │
    ▼
Internet Router (LAN + 3G/4G/GSM cellular failover)
    │
    ▼
Network Switch
    ├── SmartLogger (port 502)
    ├── PPC (Power Plant Controller)
    ├── Acuvim L meters (fixed IPs, e.g. 192.168.x.x)
    ├── MOXA RS485→Ethernet converters
    │       ├── Sinexcel
    │       ├── PM5110
    │       └── other RS485 devices
    └── Second Switch (larger sites)
            ├── Additional MOXA devices
            └── DSE8610
```

Key points:
- All devices share a 192.168.x.x LAN
- Cellular backup SIM provides connectivity resilience
- Complex sites (SLD2) have a dedicated engineering VLAN separate from operations
- Acuvim meters are assigned fixed/static IPs

---

## 4. Data Availability by Objective

### 4.1 Remote Monitoring

**Available now (SmartLogger registers):**
- SOC (40515), SOH (40516), SOE (40517)
- Active power (40525), Reactive power (40544)
- Battery charge/discharge power (40507)
- Charge energy today (40468), Discharge energy today (40470)
- Total charge (40472), Total discharge (40476)
- Total yield (40560), Yield today (40562)
- Grid voltage A/B/C (40575-40577), Grid current A/B/C (40572-40574)
- Plant status, array status, string status
- 60+ alarm IDs via registers 50000-50007
- Environmental: irradiance, wind speed/direction, temperatures

**Available now (Acuvim L):**
- V, I, P, Q, S, PF, frequency per phase
- Harmonics to 63rd order (EL grade), THD
- Import/export energy (revenue-grade)
- Demand (kW, kVA)
- TOU energy by tariff period

**Gaps:**
- EPC CAB1000 live power/SOC data (no register map)
- Sinexcel operating state (no register map)
- Generator runtime/fuel/state from DSE8610 (no map)
- Battery BMS detail from Poweroad/CATL (if separate from SmartLogger path)

### 4.2 Billing / Metering

**Primary billing device: Acuvim L + AXM-WEB2**
- Class 0.2S/0.5 revenue-grade — legally defensible
- TOU tariff engine: 4 tariffs × 12 seasons × 14 schedules
- 8GB local data log at 1-second resolution — survives connectivity outages
- Push-capable: MQTT, HTTP, FTP → cloud receives data without polling
- Demand measurement for capacity billing

**Secondary consideration: Schneider PM5110**
- Class 0.5S — acceptable for billing but no native TOU on data output
- RS485 only — adds gateway complexity
- If sites use PM5110 instead of Acuvim L, billing accuracy is reduced
- **Recommendation to Johan:** standardise on Acuvim L for all revenue metering points

**SmartLogger pass-through registers:**
- Include power meter TOU price segments
- Not revenue-grade for billing purposes — use Acuvim L as billing source of truth

### 4.3 Remote Control

**Available now (SmartLogger RW registers):**

| Control Action | Register | Values |
|----------------|----------|--------|
| Working mode | 42256 | 0=none, 2=max self-consumption, 4=full grid feed, 5=TOU, 6=grid dispatch |
| Active power % | 40428 | 0-100% |
| Active power W (high-priority) | 40430 | Signed W |
| Reactive power VAr (high-priority) | 40432 | Signed VAr |
| Grid connection | 44376 | 0=on-grid, 1=off-grid |
| PV inverter off/on | 40196/40197 | — |
| ESS off/on | 40198/40199 | — |
| Array black start | 44360/44362 | — |

**Write path security note:** Port 502 accepts writes with no authentication at the Modbus protocol level. The edge agent must enforce authorization before forwarding any write command to the device.

---

## 5. Competitor Reference UIs (EMS Screenshots)

| Screenshot | Style | Key Features Observed |
|-----------|-------|-----------------------|
| **EMS_SA_company** | Operator portal | Power flow SLD diagram (live kW), Acuvim tabs per meter, time-series state bars for inverter/breaker/alarm, SOC |
| **EMS_Rex / Digital Twin** | Multi-site dashboard | Side-by-side site panels, mode/state indicators, generator widget, active alarms panel |
| **EMS_screen (Grafana-style)** | Engineering view | Multi-channel time-series, energy totals (charge/discharge/import/export), BMS metrics, raw numerical readouts |
| **EMS_Sungrow / SolarCloud** | Client portal | Energy savings (ZAR), production vs. consumption chart, CO2/environmental metrics, clean minimal UI |

**Design implication:** Build two distinct UX surfaces:
1. **Operator portal** (Johan's team): engineering depth, alarms, control interface, multi-site overview
2. **Client portal**: energy summary, financial savings, clean power-flow diagram, no controls

---

## 6. Architectural Shape

### Three-Layer Model

```
┌──────────────────────────────────────────────────────────────┐
│  APPLICATION LAYER                                            │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │   Operator Portal    │  │      Client Portal            │  │
│  │  (depth, control,    │  │  (summary, savings, clean)   │  │
│  │   alarms, multi-site)│  │                              │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  CLOUD INGEST / PLATFORM LAYER                               │
│  • Unified device schema / normalisation                     │
│  • Time-series storage                                       │
│  • Billing calculation pipeline                              │
│  • Multi-tenant site model                                   │
│  • Control command API (auth + audit)                        │
│  • Receives: edge agent telemetry + Acuvim direct push       │
├──────────────────────────────────────────────────────────────┤
│  EDGE LAYER (on-site per site)                               │
│  • Edge agent: polls SmartLogger + other Modbus TCP devices  │
│  • Local time-series buffer (connectivity resilience)        │
│  • Store-and-forward to cloud on reconnect                   │
│  • Forwards control commands to devices (with auth check)    │
│  • Acuvim L pushes independently via MQTT/HTTP               │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Edge architecture | Smart edge with local buffer | Cellular backup topology; billing data gaps are invoice disputes |
| Billing data source | Acuvim L as source of truth | Revenue-grade accuracy; local 8GB log survives cloud outages |
| Control write path | Edge agent with auth enforcement | Modbus has no auth — all authorization logic must live at edge agent |
| Multi-tenancy | Site-first data model | Johan will manage multiple client sites |
| Client connectivity | Async with eventual consistency | Don't design for synchronous polling — assume intermittent WAN |

---

## 7. Device Specifications Research (completed 2026-03-31)

Specs researched and documented in `discovery/specs/`:

| Device | Spec File | Key Finding |
|--------|-----------|-------------|
| Sinexcel PWS1-500K | `sinexcel_pws1_500k_protocol.md` | SunSpec Model 103 at register 500; proprietary map at 101–148 (unconfirmed for module arch); control at 53000+ |
| Acuvim L Modbus | `acuvim_l_modbus_registers.md` | Full map: Float32 at 0x0600+, energy at 0x0156+, TOU at 0x0200+, 100ms fast-read at 0x3000+ |
| AXM-WEB2 Push Config | `acuvim_l_axm_web2_configuration.md` | MQTT JSON payload schema, HTTP multipart/form-data, TLS cert auth, 3GB offline cache |
| DSE8610 MK2 | `dse8610_gencomm_register_map.md` | Native Modbus TCP (no add-on); full alarm map 39425+; engine/AC registers 1024–1801 |
| Schneider PM5110 | `schneider_pm5110_modbus_register_map.md` | Full map: measurements at 3000+, energy FLOAT32 at 2700+, demand at 3764+, alarms at 2421/2423 |
| EPC Power CAB1000 | `epc_power_cab1000_status.md` | No public register map; Lantronix Modbus TCP gateway; contact EPC Power directly |

---

## 8. Identified Gaps (as of 2026-03-31)

### Architecture decisions made (no longer blocking)

| Decision | Outcome |
|----------|---------|
| Multi-site model | Confirmed 1-N from day one — architecture already multi-tenant |
| User tiers | Two tiers confirmed: Operations (full access) and Client (aggregated read-only + billing) |
| Dashboard refresh | 5 min default, configurable, minimum ~30 s — decoupled from edge poll rate (10–30 s) |
| Billing data source | Acuvim L exclusively — never derived from polling other devices |
| Poweroad / CATL BMS | Not directly integrated — data available via Sinexcel PWS1 CAN pass-through and SmartLogger |
| Huawei sub-devices | Not directly integrated — all data via SmartLogger (collapses 4 devices to 1 endpoint) |

### Device spec gaps (technical research)

| Gap | Impact | Action |
|-----|--------|--------|
| EPC Power CAB1000 register addresses | Cannot poll/control EPC BESS sites | Download Eaton xStorage I/O manual P-164001236 in browser; or run `get-models.py` against live unit |
| Sinexcel PWS1-500K measurement regs (module arch) | Register addresses unconfirmed for 500K vs 30K unit — OpenEMS cross-validates but not 100% confirmed | Request PWS1 module protocol spreadsheet: sinexcel.us/wiki or +86 0755-8651-1588 |
| DSE8610 full control command list | Remote generator start/stop command set incomplete | Request official GenComm doc from DSE Technical Support |
| Sungrow MBB protocol | Cannot integrate SLD2-type sites | Research when model confirmed by Johan |
| Schneider PM3255 / PM5000 variants | Deployed models unknown | Confirm with Johan; PM5110 map already done as baseline |

### Business / requirements gaps (need Johan input)

See `requirements/QUESTIONS_FOR_JOHAN.md` for full structured question list. Key blockers:

| Gap | Why Blocking |
|-----|-------------|
| PPC make/model and role | Could collapse entire control architecture to one endpoint — or add significant complexity |
| What energy flows are billed | Directly determines which Acuvim L registers feed the billing engine |
| Tariff structure (flat/TOU/demand) | Determines billing engine complexity and Acuvim L TOU configuration |
| MOXA NPort model numbers | Needed for RS485 gateway configuration and deployment guide |
| Regulatory/retention requirements | Determines data retention policy in data model |

---

## 9. Source Documents Ingested

| File | Status | Notes |
|------|--------|-------|
| `Site description for cloud monitoring.pdf` | Read | Business context email from Johan |
| `Acuvim-L-Multifunction-Power-and-Energy-Meter-Datasheet.pdf` | Read | Full datasheet; billing-capable device confirmed |
| `PES_Schneider Electric_PowerLogic-PM5000-Power-Meters_METSEPM5110.pdf` | Read | Datasheet only; RS485 limitation confirmed |
| `SmartLogger V300R024C00SPC200 ModBus Interface Definitions new.pdf` | Read | Full 95-page register map; primary control surface |
| `Operating Manual of PWS1-500K series Storage.pdf` | Read (via PyMuPDF) | **Sinexcel** PWS1-500K 500kW bidirectional PCS operating manual V2.1. RS485+Ethernet+CAN. Operating manual only — separate register map document needed. |
| `Comms_SLD1.png` | Read | Simple site network topology |
| `Comms_SLD2.png` | Read | Complex multi-area site with IP table |
| `EMS_Rex.png` | Read | Reference UI: multi-site operator dashboard |
| `EMS_SA_company.png` | Read | Reference UI: SA company EMS, Acuvim-aware |
| `EMS_screen.png` | Read | Reference UI: Grafana-style engineering view |
| `EMS_Sungrow.png` | Read | Reference UI: SolarCloud consumer portal |
