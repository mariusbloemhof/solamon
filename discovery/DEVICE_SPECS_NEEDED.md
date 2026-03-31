# Device Technical Specifications — Research Checklist

**Purpose:** Close all technical gaps so the platform can integrate with every possible device in Johan's ecosystem. Each device listed here needs a complete integration specification before implementation begins.

**Status key:** `Done` | `Partial` | `Gap` | `Not Started`

---

## 1. Huawei SmartLogger `Status: Done`

**Model:** V300R024C00SPC200  
**Source:** `SmartLogger V300R024C00SPC200 ModBus Interface Definitions new.pdf` (in discovery folder)  
**What we have:**
- Full Modbus TCP register map (166 RO/RW registers documented)
- Port 502, device ID 0 = SmartLogger, 1-247 = connected devices
- All monitoring registers: SOC, SOH, SOE, power flows, energy, alarms, grid state
- All control registers: working mode, power setpoints, grid switch, start/stop
- Function codes: 0x03 (read), 0x06 (write single), 0x10 (write multiple), 0x2B (device ID)
- Communication: big-endian, max 256 bytes/frame

**What's missing:** Nothing significant. Implementation-ready.

---

## 2. Huawei SUN2000 Inverters `Status: Done (via SmartLogger)`

**Access path:** Via SmartLogger device IDs 1-247  
**What we have:** Accessible via SmartLogger pass-through registers (string-level monitoring)  
**Note:** Direct Modbus to inverters is possible but unnecessary — SmartLogger exposes all needed data.

**What's missing:** Nothing for standard monitoring. If inverter-specific alarms or configuration are needed, obtain SUN2000 Modbus spec separately.

---

## 3. Huawei Luna PCS + LUNA2000B Batteries `Status: Done (via SmartLogger)`

**Access path:** Via SmartLogger  
**What we have:** SOC, SOH, SOE, charge/discharge power all available via SmartLogger registers  
**What's missing:** Nothing for standard use case.

---

## 4. AccuEnergy Acuvim L + AXM-WEB2 Module `Status: Done`

**Sources:** Acuvim-L User Manual V2.0.3 (Dec 2025) + AXM-WEB2 User Manual V2.1.4 (Sep 2024) — both fully researched  
**Spec file:** `specs/acuvim_l_modbus_registers.md` and `specs/acuvim_l_axm_web2_configuration.md`

**What we have:**
- ✅ Full Modbus TCP register map (secondary 0x0130+, primary Float32 0x0600+, energy 0x0156+, TOU 0x0200+)
- ✅ AXM-WEB2 MQTT configuration: broker, port, TLS/SSL, LWT, topic, QoS, publish interval
- ✅ MQTT JSON payload schema (full example with field names)
- ✅ HTTP POST format (multipart/form-data wrapper + JSON body)
- ✅ Authentication: username/password + TLS client certificate support confirmed
- ✅ Offline cache: 3GB, auto-uploads on reconnect
- ✅ 50ms and 100ms fast-read mode registers documented
- ✅ Default network settings for commissioning

**Minor gaps:**
- Alarm register addresses not exposed via Modbus (alarm config is web-interface only)
- HTTP POST JSON body not explicitly documented (same as MQTT schema when JSON format selected)

---

## 5. Schneider Electric PM5110 `Status: Done`

**Sources:** PM51xx_PM53xx_PMC Register List v2011/v2021 R01 (Schneider authored, via GitHub); PM5100 User Manual EAV15105  
**Spec file:** `specs/schneider_pm5110_modbus_register_map.md`

**What we have:**
- ✅ Full Modbus RTU register map: V, I, P, Q, S, PF (3000–3110), energy FLOAT32 (2700–2722), energy INT64 (3204+), demand (3764+), THD (21300+), alarms (2421, 2423, 2441)
- ✅ Default RS485 settings: 8E1, 19200 baud, slave address 1
- ✅ Function codes: FC 01, 03, 06, 16
- ✅ All alarm bit definitions documented
- ✅ 4Q power factor decode rule documented
- ✅ Demand configuration registers

**Key limitation for billing:** PM5110 has **no TOU engine** — tariff differentiation must be applied in the cloud platform by timestamping energy deltas against a schedule. Note: `DOCA0005EN` does not apply to PM5000 series (it's for MasterPact circuit breakers). Correct reference: EAV15105.

---

## 6. Schneider Electric PM3255 `Status: Not Started`

**Note:** Mentioned in Johan's email as a device used on sites. No documentation in discovery folder.  
**What's needed:**

- [ ] **Datasheet** — basic capabilities, accuracy class, protocols
- [ ] **Modbus RTU register map** — all measurement registers
- [ ] **RS485 communication settings**

**Where to find:** Schneider Electric website — PowerLogic PM3255 product page

---

## 7. Schneider Electric PM5000 series (general) `Status: Not Started`

**Note:** Email mentions PM5000 series as a category. May overlap with PM5110 above.  
**What's needed:**

- [ ] Clarify with Johan which specific PM5000 models are deployed (PM5110, PM5310, PM5560?)
- [ ] For each model: datasheet + Modbus register map

---

## 8. EPC Power CAB1000 `Status: Partial`

**Note:** Mentioned in Johan's email as a device on sites. The `PWS1-500K` PDF is actually a **Sinexcel** device (see section 9).  
**Spec file:** `specs/epc_power_cab1000_status.md`

**What we have:**
- ✅ Confirmed Modbus TCP via Lantronix gateway (DHCP, port 502)
- ✅ EPC Power GitHub org confirmed: 12 repos including `sunspec-demo`, `pm`, `st` (EPyQ)
- ✅ SunSpec model 65534 confirmed — proprietary vendor extension model
- ✅ Static +20,000 Modbus register offset confirmed (all registers start at ~20001)
- ✅ CAN J1939 internal signals: CommandPower (0x0CFFAC41, ±90kW), StatusMeasuredPower, StatusBits, StatusFaults
- ✅ SunSpec control point names: CmdRealPwr, CmdReactivePwr, CtlSrc, St, StVnd, FltClr
- ✅ Eaton xStorage 250-1000kW uses CAB1000 as PCS; I/O manual (P-164001236) confirmed to have Modbus sections

**Remaining gap:**
- [ ] **Actual register addresses** — require `smdx_65534.xml` (download from live device via `get-models.py`) or Eaton I/O manual P-164001236
- [ ] Confirm Modbus Unit ID (likely 1)

**Next action:** Download Eaton xStorage I/O manual in browser (PDF too large for automated fetch) or run sunspec-demo against a live CAB1000

---

## 9. Sinexcel PWS1-500K `Status: Partial`

**Sources:** Sinexcel ESS Wiki (sinexcel.us), PWS2-30K SunSpec protocol spreadsheet (shared architecture), OpenEMS driver cross-validation, DEIF Multi-Line 2 ASC compatibility doc  
**Spec file:** `specs/sinexcel_pws1_500k_protocol.md`

**What we have:**
- ✅ Communication interfaces confirmed: RS485 Modbus RTU (default, 9600/19200), Ethernet Modbus TCP port 502, CAN for BMS
- ✅ SunSpec Model 103 (three-phase inverter) starting at register 500 — full register map (572–622)
- ✅ SunSpec fault bitfields (Event1 registers 610–612) — all bits documented
- ✅ Operating state register (608) values documented
- ✅ Proprietary measurement registers 101–148 (V, I, P, Q, S, PF, energy, temperatures)
- ✅ Active/reactive power setpoint registers 135/136 (PWS2; units 0.01 kW)
- ✅ Module-based control registers 53000+ (start/stop, on/off-grid, power setpoints, clear fault)
- ✅ **53622 = AC active power setpoint (units: 10W/count; 50000 = 500kW)**
- ✅ Command registers 650–658 (start, stop, clear fault, on/off-grid, standby, restart, grid stop)
- ✅ Full network config registers 300–333 (IP, mask, gateway, MAC, Modbus addr, baud, watchdog, BMS timeout, grid mode)
- ✅ Output config registers 748–894 (nominal V/Hz, wiring, grid code, Volt-VAr/Volt-Watt/Freq-Watt curves)
- ✅ SOC register addresses for three BMS protocol variants (SunSpec Vendor B, Vendor A, Vendor C)
- ✅ EMS watchdog timeout (register 327)
- ✅ **OpenEMS driver cross-validates all FC3 read ranges (1–31, 32–47, 101–148, 224–333, 650–658, 748–894, 934–967)**
- ✅ **DEIF Multi-Line 2 ASC confirms PWS1 ESS compatibility; firmware v1517 boundary documented**

**Remaining gap:**
- [ ] **Confirm measurement registers 101–148 apply to PWS1-500K** — OpenEMS driver reads them, but only PWS2-30K explicitly named in original Sinexcel docs
- [ ] **Obtain PWS1 module-based protocol spreadsheet** — sinexcel.us/wiki (login required) or direct request to Sinexcel (+86 0755-8651-1588)
- [ ] Confirm firmware version on Johan's installed units (v1517 boundary)

---

## 10. Poweroad Batteries `Status: Gap`

**Note:** Mentioned in Johan's email as one of the battery brands used.  
**What's needed:**

- [ ] **Clarify integration path**: Does SmartLogger already expose Poweroad BMS data? Or does Poweroad connect separately via RS485?
- [ ] If separate: **BMS Modbus register map** — SOC, SOH, cell voltage/temperature, alarm registers
- [ ] **Communication interface** — RS485 pin-out, protocol variant (Modbus RTU vs proprietary)

**Where to find:**
- Poweroad website or distributor documentation
- If connected through Huawei SmartLogger: check SmartLogger's supported third-party BMS list

---

## 11. CATL Batteries `Status: Gap`

**Note:** Present on complex site (SLD2 shows CATL MBB units).  
**What's needed:**

- [ ] **Clarify integration path**: Via Sinexcel/Sungrow inverter BMS interface, or separate communication?
- [ ] If accessible: **BMS data format** — SOC, SOH, cell-level data, thermal data, alarm registers
- [ ] CATL typically uses CAN bus internally; may only be accessible through the BESS inverter's registers

**Where to find:**
- CATL integration is typically through the BESS inverter (Sinexcel/Sungrow) — check those register maps first
- CATL direct integration documentation: contact CATL or their distributor

---

## 12. Deep Sea DSE8610 MK2 `Status: Done`

**Sources:** Senquip APN0029, Victron dbus-modbus-client dse.py, DSE8610 MK2 Operator Manual Issue 10  
**Spec file:** `specs/dse8610_gencomm_register_map.md`

**What we have:**
- ✅ Modbus TCP confirmed native (built-in Ethernet, no add-on module, up to 5 simultaneous clients)
- ✅ RS485 default: 115200 baud, slave address 10
- ✅ Full addressing formula: Address = (Page × 256) + Offset
- ✅ Identity/detection registers (768–771)
- ✅ Operating mode (772), Engine status (1408)
- ✅ AC electrical: frequency (1031), voltage L1/L2/L3 (1032–1037), current (1044–1049), active power per phase (1052–1057), total (1536–1537), energy (1800–1801)
- ✅ Engine: oil pressure (1024), coolant temp (1025), fuel level % (1027), battery voltage (1029), RPM (1030), run hours (1798–1799), start count (1808–1809)
- ✅ Full alarm register map (39425–39445) with 4-bit slot decode, all 88+ named alarms
- ✅ SCF control registers (4104–4105) structure documented

**Remaining gap:**
- Full control command list requires official GenComm document from DSE Technical Support (deepseaelectronics.com) — not publicly downloadable

---

## 13. MOXA RS485-to-Ethernet Converters `Status: Gap`

**Note:** MOXA devices appear in both SLD images as gateways for RS485 devices. Specific models unknown.  
**What's needed:**

- [ ] **Exact MOXA model numbers** from Johan (likely NPort 5100 or 5200 series)
- [ ] **Configuration documentation** — how to set up serial tunneling / virtual COM mode vs Modbus gateway mode
- [ ] **Network settings** — default IP, configuration web interface or utility
- [ ] **Modbus gateway mode configuration** — serial parameters forwarding, device ID mapping

**Where to find:**
- Once model numbers are known: moxa.com product documentation
- Common models: NPort 5110A (1-port), NPort 5210A (2-port), MGate MB3180 (dedicated Modbus gateway)

---

## 14. PPC (Power Plant Controller) `Status: Gap`

**Note:** Visible in SLD1 between the router and SmartLogger. Make and model unknown.  
**What's needed:**

- [ ] **Ask Johan** for make and model of the PPC on his sites
- [ ] Once identified: communication protocol and register map
- [ ] Understand role: is PPC pass-through to SmartLogger, or does it sit in front of SmartLogger for grid compliance commands?

**Note:** PPC typically implements SCADA/grid dispatch protocols (IEC 61850, Modbus TCP, DNP3). If Johan's sites have grid connection agreements, the PPC may be utility-mandated equipment.

---

## 15. Sungrow (MBB units) `Status: Not Started`

**Note:** SLD2 shows "MBB" units which appear to be Sungrow BESS. Sungrow has their own inverter/BMS stack.  
**What's needed:**

- [ ] **Exact Sungrow BESS model** from Johan (SBR, SBH, or PowerTitan series?)
- [ ] **Sungrow Modbus TCP register map** — Sungrow publishes communication protocols for their devices
- [ ] **Is there a Sungrow SmartLogger equivalent?** — Sungrow uses iSolarCloud as their platform; there may be a local API

**Where to find:**
- Sungrow website: sungrowpower.com — support/downloads section
- Search: "Sungrow BESS Modbus TCP interface definition"

---

## 16. Internet Router / Cellular Backup `Status: Not Started`

**Note:** Sites have broadband + 3G/4G/GSM cellular failover. Router model unknown.  
**What's needed (low priority):**

- [ ] Router model from Johan — relevant for OTA management and edge agent deployment
- [ ] Whether routers support remote management (Teltonika RUT series, for example, has cloud management)
- [ ] VPN capability assessment — some architectures tunnel edge traffic via VPN rather than exposing Modbus TCP to internet

---

## Summary — Priority Order for Research

| Priority | Device | Status | Next Action |
|----------|--------|--------|-------------|
| ~~P1~~ | ~~Acuvim L Modbus map + WEB2 config~~ | **Done** | See `specs/acuvim_l_*.md` |
| ~~P1~~ | ~~Schneider PM5110 register map~~ | **Done** | See `specs/schneider_pm5110_modbus_register_map.md` |
| ~~P2~~ | ~~DSE8610 MK2 GenComm~~ | **Done** | See `specs/dse8610_gencomm_register_map.md` |
| **P1** | Sinexcel PWS1-500K measurement regs | **Partial** | Request PWS1 module protocol spreadsheet from Sinexcel; register structure nearly complete via OpenEMS cross-validation |
| **P1** | EPC Power CAB1000 register map | **Partial** | Download Eaton xStorage I/O manual P-164001236 in browser; or run sunspec-demo `get-models.py` against live device |
| **P2** | MOXA device model numbers | **Not Started** | Ask Johan for model numbers from site documentation |
| **P3** | Sungrow BESS (MBB) register map | **Not Started** | Only needed for SLD2-type sites; confirm with Johan |
| **P3** | Poweroad / CATL BMS | **Not Started** | Verify if exposed via Sinexcel/SmartLogger first |
| **P3** | PPC make/model | **Not Started** | Ask Johan — may be pass-through only |
| **P4** | Schneider PM3255, PM5000 series | **Not Started** | Confirm deployed models with Johan before researching |
| **P4** | Router model / VPN capability | **Not Started** | Infrastructure concern; defer to deployment planning |
