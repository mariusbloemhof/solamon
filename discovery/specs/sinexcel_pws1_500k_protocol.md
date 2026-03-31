# Sinexcel PWS1-500K — Modbus Communication Protocol

**Device:** PWS1-500K / PWS1-500KTL Series 500kW Bidirectional Energy Storage PCS  
**Manufacturer:** Shenzhen Sinexcel Electric Co., Ltd.  
**Source:** Sinexcel ESS Knowledge Base (sinexcel.us/wiki), PWS2-30K SunSpec spreadsheet (shared architecture)  
**Status:** Partial — measurement register addresses for module-based 500K architecture require direct request from Sinexcel

---

## 1. Communication Interfaces

| Interface | Details |
|-----------|---------|
| RS485 (default EMS) | Modbus RTU, terminals 9 & 10 on HMI board; baud 9600 or 19200; 8 data bits, no parity, 1 stop bit |
| Ethernet (Modbus TCP) | Port RJ25 on HMI/touch screen; port 502; fixed static IP configured via HMI |
| CAN (BMS default) | Terminals 7 & 8; supports JUNWEI, NANDU, XIEXIN, XINWANGDA, PAINENG, GAOTE, and generic BMS protocols |
| Protocol standard | **SunSpec / MESA** compatible on both RS485 and Ethernet |

**Configuration (via HMI Settings > Advanced > HMI):**
- IP address, Gateway, Subnet mask
- Modbus address: 1–247
- RTU baud rate: 9600 or 19200

**EMS timeout watchdog:** Register 327 (seconds, 0 = disabled). If no Modbus communication within timeout, PCS stops accepting remote commands.

---

## 2. SunSpec Register Map (starting at address 500)

SunSpec ID at register 500 = `0x53756E53`. Protocol uses FC 03 (read) only for this block.  
Scale factors (sunssf) are signed 16-bit integers; apply as: **real value = raw × 10^SF**

### Common Block — SunSpec Model 1 (addresses 502–568)

| Address | Parameter | Size |
|---------|-----------|------|
| 502 | SunSpec_DID_0001 = 1 | 1 |
| 503 | Block length = 65 | 1 |
| 504–519 | Manufacturer string | 16 |
| 520–535 | Model string | 16 |
| 536–543 | Options string | 8 |
| 544–551 | Version string | 8 |
| 552–567 | Serial Number string | 16 |
| 568 | Device Address (RW) | 1 |

### Inverter Block — SunSpec Model 103 (Three-Phase, addresses 570–622)

| Address | Size | Type | Parameter | Unit |
|---------|------|------|-----------|------|
| 570 | 1 | uint16 | SunSpec_DID = 103 | — |
| 571 | 1 | uint16 | Block length | — |
| **572** | 1 | uint16 | Total AC Current | A |
| **573** | 1 | uint16 | Phase A Current | A |
| **574** | 1 | uint16 | Phase B Current | A |
| **575** | 1 | uint16 | Phase C Current | A |
| 576 | 1 | sunssf | Current scale factor | — |
| **577** | 1 | uint16 | Voltage AB | V |
| **578** | 1 | uint16 | Voltage BC | V |
| **579** | 1 | uint16 | Voltage CA | V |
| **580** | 1 | uint16 | Voltage AN | V |
| **581** | 1 | uint16 | Voltage BN | V |
| **582** | 1 | uint16 | Voltage CN | V |
| 583 | 1 | sunssf | Voltage scale factor | — |
| **584** | 1 | int16 | AC Power (signed: neg=charging) | W |
| 585 | 1 | sunssf | Power scale factor | — |
| **586** | 1 | uint16 | Frequency | Hz |
| 587 | 1 | sunssf | Frequency scale factor | — |
| **588** | 1 | int16 | AC Apparent Power | VA |
| 589 | 1 | sunssf | Apparent power SF | — |
| **590** | 1 | int16 | AC Reactive Power | var |
| 591 | 1 | sunssf | Reactive power SF | — |
| **592** | 1 | int16 | AC Power Factor | Pct |
| 593 | 1 | sunssf | PF scale factor | — |
| **594** | 2 | acc32 | AC Energy (accumulated) | Wh |
| 596 | 1 | sunssf | Energy scale factor | — |
| **597** | 1 | uint16 | DC Current | A |
| 598 | 1 | sunssf | DC current SF | — |
| **599** | 1 | uint16 | DC Voltage | V |
| 600 | 1 | sunssf | DC voltage SF | — |
| **601** | 1 | int16 | DC Power | W |
| 602 | 1 | sunssf | DC power SF | — |
| 603 | 1 | int16 | Cabinet Temperature | °C |
| 604 | 1 | int16 | Heat Sink Temperature | °C |
| 605 | 1 | int16 | Transformer Temperature | °C |
| 606 | 1 | int16 | DCDC Heat Sink Temperature | °C |
| 607 | 1 | sunssf | Temperature SF | — |
| **608** | 1 | enum16 | Operating State | — |
| 609 | 1 | enum16 | Vendor Operating State | — |
| **610** | 2 | bitfield32 | Event1 (SunSpec standard faults) | — |
| **612** | 2 | bitfield32 | Event Bitfield 2 (vendor faults) | — |
| 614–620 | 8 | bitfield32×4 | Vendor Event Bitfields 1–4 | — |
| 622 | 1 | uint16 | SunSpec End Block (0xFFFF) | — |
| 623 | 1 | uint16 | End block length = 0 | — |

**Operating State (register 608):**
| Value | State |
|-------|-------|
| 1 | OFF |
| 5 | THROTTLED (derating) |
| 7 | FAULT |
| 8 | STANDBY |
| 9 | STARTED/RUNNING |

**Event1 (register 610) — Standard SunSpec fault bits:**
| Bit | Fault |
|-----|-------|
| 0 | GROUND_FAULT |
| 1 | DC_OVER_VOLT |
| 2 | AC_DISCONNECT |
| 3 | DC_DISCONNECT |
| 4 | GRID_DISCONNECT |
| 6 | MANUAL_SHUTDOWN |
| 7 | OVER_TEMP |
| 8 | OVER_FREQUENCY |
| 9 | UNDER_FREQUENCY |
| 10 | AC_OVER_VOLT |
| 11 | AC_UNDER_VOLT |
| 14 | MEMORY_LOSS |

**Event Bitfield 2 (register 612) — Vendor fault bits:**
| Bit | Fault |
|-----|-------|
| 0 | Output ground fault |
| 1 | Grid phase lock (PLL) failed |
| 2 | Internal air over-temperature |
| 3 | Grid-connected condition timeout |
| 4 | Module renumber failure |
| 5 | CANB communication failure |
| 6 | Power frequency sync failure |
| 7 | Carrier sync failure |
| 8 | AC OVP |
| 9 | AC UVP |
| 10 | AC OFP |
| 11 | AC UFP |
| 12 | Grid voltage unbalance |
| 13 | Grid phase reverse |
| 14 | Islanding |
| 15 | On/off-grid switching error |

---

## 3. Proprietary Register Map (PWS2-30K architecture — likely shared with PWS1-500K)

> **Note:** The measurement register addresses below (32–148) are confirmed for the PWS2-30K single-unit product. The PWS1-500K module-based architecture likely shares the same measurement map. Confirm with Sinexcel before production deployment.

### Status Registers (RO, FC 03)

| Address | Parameter | Notes |
|---------|-----------|-------|
| 32 | System status bitmap | Bit0=fault, Bit1=alarm, Bit2=running, Bit3=grid-tied, Bit4=off-grid, Bit5=derate, Bit7=standby |
| 36 | AC fault register 1 | Bit0=OVP, Bit1=UVP, Bit2=OFP, Bit3=UFP, Bit4=V unbalance, Bit5=phase reverse, Bit6=island, Bit9=PLL fail |
| 37 | AC fault register 2 | Bit0=EPO, Bit7=fan fault, Bit8=BUS OV, Bit9=BUS UV, Bit13=output V abnormal, Bit15=heatsink OT |
| 38 | AC fault register 3 | Bit0=overload timeout, Bit2=AC soft start fail, Bit3=inverter start fail |
| 39 | Warning register | Bit3=inverter overload, Bit5=slave lost |
| 40 | DC status | Bit0=charging, Bit1=discharging, Bit2=fully charged, Bit3=battery empty, Bit4=DC fault, Bit5=DC alarm |
| 44 | DC fault register | Bit0=DC OVP, Bit1=DC UVP, Bit3=BMS alarm, Bit4=BMS timeout, Bit5=EMS timeout |

### Measurement Registers (RO, FC 03)

| Address | Parameter | Precision | Unit |
|---------|-----------|-----------|------|
| 101 | AC Voltage A-B | 0.1 | V |
| 102 | AC Voltage B-C | 0.1 | V |
| 103 | AC Voltage C-A | 0.1 | V |
| 104 | AC Current Phase A | 0.1 | A |
| 105 | AC Current Phase B | 0.1 | A |
| 106 | AC Current Phase C | 0.1 | A |
| 107 | Grid Frequency | 0.01 | Hz |
| 110 | AC Active Power Phase A | 0.01 | kW |
| 111 | AC Active Power Phase B | 0.01 | kW |
| 112 | AC Active Power Phase C | 0.01 | kW |
| 113 | AC Reactive Power Phase A | 0.01 | kVAR |
| 114 | AC Reactive Power Phase B | 0.01 | kVAR |
| 115 | AC Reactive Power Phase C | 0.01 | kVAR |
| 116 | AC Apparent Power Phase A | 0.01 | kVA |
| 117 | AC Apparent Power Phase B | 0.01 | kVA |
| 118 | AC Apparent Power Phase C | 0.01 | kVA |
| 119 | Power Factor Phase A | 0.01 | — |
| 120 | Power Factor Phase B | 0.01 | — |
| 121 | Power Factor Phase C | 0.01 | — |
| **122** | **Total 3-Phase Active Power** | **0.01** | **kW (signed: neg=charging)** |
| 123 | Total 3-Phase Reactive Power | 0.01 | kVAR |
| 124 | Total 3-Phase Apparent Power | 0.01 | kVA |
| 125 | Total 3-Phase Power Factor | 0.01 | — |
| **126–127** | AC Discharged Energy (uint32) | 0.1 | kWh (RW; write 0 to reset) |
| **128–129** | AC Charged Energy (uint32) | 0.1 | kWh (RW; write 0 to reset) |
| 130–131 | Reactive Energy (uint32) | 0.1 | kVArh |
| 132 | AC Heat Sink Temperature | 1 | °C |
| **135** | **AC Active Power Setpoint** | **0.01** | **kW (RW; neg=charge, pos=discharge)** |
| **136** | **AC Reactive Power Setpoint** | **0.01** | **kVAR (RW)** |
| **141** | DC Power | 0.01 | kW |
| **142** | DC Voltage | 0.1 | V |
| **143** | DC Current | 0.1 | A |
| **144–145** | DC Charged Energy (uint32) | 0.1 | kWh (RW; write 0 to reset) |
| **146–147** | DC Discharged Energy (uint32) | 0.1 | kWh (RW; write 0 to reset) |
| 148 | DCDC Heat Sink Temperature | 1 | °C |

**Sign convention:** Negative active power (register 122) = charging (absorbing power from grid). Positive = discharging (injecting to grid).

### Communication Configuration Registers (RW, FC 03/06)

Full block confirmed by OpenEMS driver and Sinexcel wiki (registers 224–333):

| Address | Parameter | Default | Notes |
|---------|-----------|---------|-------|
| 300 | IP Address octet 1 | 192 | — |
| 301 | IP Address octet 2 | 168 | — |
| 302 | IP Address octet 3 | 1 | — |
| 303 | IP Address octet 4 | 100 | — |
| 304 | Subnet Mask octet 1 | 255 | — |
| 305 | Subnet Mask octet 2 | 255 | — |
| 306 | Subnet Mask octet 3 | 255 | — |
| 307 | Subnet Mask octet 4 | 0 | — |
| 308 | Gateway octet 1 | 192 | — |
| 309 | Gateway octet 2 | 168 | — |
| 310 | Gateway octet 3 | 1 | — |
| 311 | Gateway octet 4 | 1 | — |
| 312–315 | MAC Address (4 × uint16) | — | Read-only |
| **316** | **Modbus Device Address** | **1** | **1–247** |
| **320** | **Baud rate** | **0** | **0=19200, 1=9600** |
| **325** | **Interface** | **1** | **0=RS485, 1=Ethernet** |
| **326** | **Protocol** | **1** | **0=disabled, 1=SunSpec** |
| **327** | **EMS timeout (seconds)** | **5** | **0=disabled; watchdog stops commands if exceeded** |
| 328 | EPO (Emergency Power Off) enable | 0 | 0=disabled, 1=enabled |
| 329 | BMS communication timeout (seconds) | 30 | — |
| 330 | BMS protocol | 0 | 0=CAN, 1=RS485; protocol variant configured via HMI |
| **331** | **Default grid mode** | **0** | **0=on-grid, 1=off-grid** |
| 333 | Factory reset | — | Write specific key value to trigger reset |

### Command Registers (RW, FC 06) — Addresses 650–658

Confirmed via OpenEMS `io.openems.edge.batteryinverter.sinexcel` driver and Sinexcel wiki.  
Write to trigger one-shot commands. FC 06 (write single register).

| Address | Write Value | Command |
|---------|------------|---------|
| **650** | **1** | **Start** |
| **651** | **1** | **Stop** |
| **652** | **1** | **Clear Fault** |
| **653** | **1** | **Switch to On-grid mode** |
| **654** | **1** | **Switch to Off-grid mode** |
| 655 | 0 / 1 | Enter Standby / Exit Standby |
| 656 | 1 | Restart |
| 657 | 1 | Grid Stop (emergency disconnect) |

> **Note (firmware v1517+):** DEIF Multi-Line 2 ASC documentation notes that Sinexcel firmware v1517 changed the register addresses for voltage/frequency offset parameters. If the PCS firmware is v1517 or later, verify control register addresses against the firmware-specific protocol document.

---

### Output Configuration Registers (RW, FC 03/06) — Addresses 748–894

| Address | Parameter | Notes |
|---------|-----------|-------|
| 748 | Nominal output voltage (V) | Set per grid standard |
| 749 | Nominal output frequency (Hz) | 50 or 60 |
| 750 | Output wiring | 0=3-phase 4-wire, 1=3-phase 3-wire, 2=single-phase |
| 751 | Switching device type | 0=contactor, 1=breaker |
| 752 | Module rated power (kW) | Factory-set |
| 753 | Startup delay (seconds) | — |
| 754 | Startup mode | 0=auto, 1=manual |
| 755 | Float charge voltage | 0.1V per unit |
| 756 | Topping charge voltage | 0.1V per unit |
| 800–849 | Grid code protection thresholds | OVP/UVP/OFP/UFP limits per grid standard |
| 850–869 | Volt-VAr curve points | 10 V/Q pairs (per SunSpec Model 126) |
| 870–889 | Volt-Watt curve points | 10 V/P pairs (per SunSpec Model 126) |
| 890–894 | Freq-Watt curve parameters | f/P pairs for frequency response |

> Full 748–894 table requires Sinexcel module-based protocol spreadsheet (sinexcel.us/wiki, login required).

---

## 4. PWS1-500K Module-Based Control Registers (53000+ series)

These are confirmed for the PWS1-500K module architecture. FC 06 (write single) or FC 16 (write multiple).

### Operating Mode (RW)

| Register | Value | Description |
|----------|-------|-------------|
| 53600 | 0 | On-grid (grid-tied) mode |
| 53600 | 1 | Off-grid (island) mode |
| 53601 | 0 | Energy dispatch: AC mode |
| 53601 | 1 | Energy dispatch: DC mode |
| 53601 | 2 | Energy dispatch: String mode |

### Power Control (RW)

| Register | Description |
|----------|-------------|
| 53620 | Reactive power mode: 0=constant PF, 1=constant Q, 2=Volt-Var |
| 53622 | AC active power setpoint (AC dispatch mode) — **units: 10W per count** (write 50000 = 500kW discharge, write −50000 = 500kW charge) |
| 53636 | Active power regulation mode: 0=constant, 1=Volt-Watt, 2=Freq-Watt, 3=combined |

### Start / Stop Commands (Write)

| Register | Write Value | Description |
|----------|------------|-------------|
| **53900** | **1** | **Start all modules** |
| **53901** | **1** | **Stop all modules** |
| **53903** | **1** | **Clear fault (all modules)** |
| 53920 | 1 | Start string 1 |
| 53921 | 1 | Stop string 1 |
| 53923 | 1 | Clear fault string 1 |
| 53930 | 1 | Start string 2 |
| 53931 | 1 | Stop string 2 |
| ... | ... | Strings 3–8 follow +10 per string |

**Prerequisite:** Register 53011 bit 10 must = 0 (no faults) before start commands are accepted.

### Per-String Power Setpoints (String Dispatch mode)

| Register | String |
|----------|--------|
| 55600 | String 1 active power setpoint |
| 55601 | String 2 |
| 55602–55607 | Strings 3–8 |

---

## 5. SOC (State of Charge)

The PWS1-500K PCS **does not natively expose SOC in its own register map**. SOC is managed by the BMS via CAN bus. Depending on BMS brand/protocol, SOC may be accessible via pass-through registers:

**SunSpec BMS protocol (Vendor B):**
| Address | Parameter | Unit |
|---------|-----------|------|
| 184 | SOC | % (with SF at 185) |
| 186 | SOH | % |

**Vendor A BMS protocol:**
| Address (hex) | Decimal | Parameter | Precision |
|---------------|---------|-----------|-----------|
| 0xF003 | 61443 | Battery SOC | 0.4% per count |
| 0xF004 | 61444 | Battery SOH | 0.4% per count |

**Vendor C BMS protocol:**
| Address (hex) | Decimal | Parameter |
|---------------|---------|-----------|
| 0x1085 | 4229 | System SOC (0–100%) |
| 0x1086 | 4230 | System SOH (‰) |

---

## 6. Validation and Cross-References

**OpenEMS cross-validation:** The open-source `io.openems.edge.batteryinverter.sinexcel` Java driver (github.com/OpenEMS/openems) reads the following FC3 blocks as part of normal operation — confirming these register ranges are valid and readable:
- 1–31 (system status, hardware version)
- 32–47 (all fault/warning bitmaps)
- 101–148 (all AC/DC measurements)
- 224–333 (configuration including full 300-333 network block)
- 650–658 (command registers)
- 748–894 (output configuration)
- 934–967 (additional status/config)

This is the strongest available cross-validation that the proprietary register map is correct for shipping hardware.

**DEIF Multi-Line 2 ASC confirmation:** The DEIF ASC (Automatic Synchronizer Controller) documentation explicitly confirms compatibility with Sinexcel PWS1 ESS, with a firmware v1517 boundary note — earlier firmware used different register addresses for voltage/frequency offset parameters.

## 7. Outstanding Gaps

- [ ] **Confirm measurement register addresses (101–148) apply to PWS1-500K module architecture** — OpenEMS driver suggests yes, but only PWS2-30K is explicitly named in original Sinexcel docs
- [ ] **Obtain PWS1 module-based protocol spreadsheet** from Sinexcel (requires login at sinexcel.us/wiki or direct request) — needed for full 748-894 output config table and any 500kW-specific addressing
- [ ] Confirm which BMS register map applies to Poweroad/CATL batteries connected to this PCS
- [ ] Confirm firmware version on Johan's installed units (v1517 boundary)

**Contact:** Sinexcel hotline +86 0755-8651-1588 | sinexcel.us | sinexcel.com  
**Request doc:** "PWS1 module-based protocol spreadsheet" or "PWS1-500K Modbus communication interface definition"

---

## 8. Source Documents

| Document | URL / Location |
|----------|---------------|
| PWS1-500K Operating Manual V2.1 | `discovery/Operating Manual of PWS1-500K series Storage 操作手册20200506.pdf` |
| Sinexcel Module-Based Protocol Wiki | https://sinexcel.us/wiki/doku.php?id=manual:module-based:protocol_manual |
| PWS2-30K SunSpec Protocol Spreadsheet | https://sinexcel.us/wiki/lib/exe/fetch.php?media=manual:pws2-30k:pws2-30k-sunspec_v108_revised_20211207_c.xlsx |
| AC Module Fault List | https://sinexcel.us/wiki/doku.php?id=manual:module-based:fault_list_of_ac_module |
| OpenEMS Sinexcel driver (register cross-validation) | https://github.com/OpenEMS/openems/tree/develop/io.openems.edge.batteryinverter.sinexcel |
| DEIF Multi-Line 2 ASC (PWS1 ESS confirmed) | https://www.deif.com/power-plant-controllers/asc-multi-line-2/ |
