# Deep Sea Electronics DSE8610 MK2 — GenComm / Modbus Register Map

**Device:** DSE8610 MK2 Auto Start Control Module (generator controller)  
**Manufacturer:** Deep Sea Electronics (DSE), deepsea.co.uk  
**Source:** Senquip APN0029, Victron dbus-modbus-client dse.py, DSE8610 MK2 Operator Manual Issue 10  
**Status:** Near-complete for monitoring; control registers require official GenComm doc from DSE

---

## 1. Communication Interfaces

| Interface | Details |
|-----------|---------|
| **Modbus TCP (Ethernet)** | Built-in Ethernet port — no add-on module required. Up to 5 simultaneous Modbus master connections. Port: configurable (default 502 recommended; confirm in DSE Configuration Suite). |
| **Modbus RTU (RS485)** | RS485 port. Default: 115200 baud, slave address 10. |
| Both interfaces | Use identical GenComm register map — same addresses on TCP and RTU. |

**Configuration tool:** DSE Configuration Suite (free download from deepseaelectronics.com) — required for port number and RS485 settings.

---

## 2. Register Addressing Formula

All registers are **holding registers**, read with **FC 03**.

```
Modbus Register Address = (Page × 256) + Offset
```

**Invalid/unavailable values returned by controller:**
- uint16: `0xFFFF` (65535)
- sint16: `0x7FFF` (32767)
- uint32: `0xFFFFFFFF`
- sint32: `0x7FFFFFFF`

---

## 3. Identity / Device Detection Registers

| Register | Parameter | Type | Notes |
|----------|-----------|------|-------|
| 768 | Manufacturer Code | uint16 | DSE = 1 |
| 769 | Model Number | uint16 | DSE8610 MK2 = 32832 |
| 770–771 | Serial Number | uint32 | — |

---

## 4. Generator State Registers

| Register | Parameter | Type | Values |
|----------|-----------|------|--------|
| 772 | Operating Mode | uint16 mapped | 0=Stop, 1=Auto, 2=Manual, 3=Test on Load, 4=Auto+Manual Restore, 6=Test off Load, 7=Off |
| **1408** | **Engine Status Code** | **uint16 mapped** | **0=Stopped, 1=Pre-Start/Preheat, 2=Warming Up, 3=Running, 4=Cooling Down, 5=Stopped, 6=Post Run, 15=N/A** |

---

## 5. AC Electrical Measurements

| Register | Parameter | Type | Scale | Unit |
|----------|-----------|------|-------|------|
| 1031 | AC Frequency | uint16 | ÷10 | Hz |
| 1032–1033 | AC L1 Voltage | uint32 | ÷10 | V |
| 1034–1035 | AC L2 Voltage | uint32 | ÷10 | V |
| 1036–1037 | AC L3 Voltage | uint32 | ÷10 | V |
| 1044–1045 | AC L1 Current | uint32 | ÷10 | A |
| 1046–1047 | AC L2 Current | uint32 | ÷10 | A |
| 1048–1049 | AC L3 Current | uint32 | ÷10 | A |
| 1052–1053 | AC L1 Active Power | sint32 | ×1 | W |
| 1054–1055 | AC L2 Active Power | sint32 | ×1 | W |
| 1056–1057 | AC L3 Active Power | sint32 | ×1 | W |
| **1536–1537** | **AC Total Active Power** | **sint32** | **×1** | **W** |
| 1800–1801 | AC Energy Forward | uint32 | ÷10 | kWh (accumulated) |

> **Voltage note:** L-N vs L-L depends on CT/VT wiring configuration. Confirm with Johan's installation for each site.

---

## 6. Engine / Mechanical Measurements

| Register | Parameter | Type | Scale | Unit |
|----------|-----------|------|-------|------|
| 1024 | Oil Pressure | uint16 | ×1 | kPa |
| 1025 | Coolant Temperature | sint16 | ×1 | °C |
| 1026 | Oil Temperature | sint16 | ×1 | °C |
| 1027 | Fuel / Tank Level | uint16 | ×1 | % (0–100) |
| **1029** | **Battery / Starter Voltage** | **uint16** | **÷10** | **V** |
| **1030** | **Engine Speed** | **uint16** | **×1** | **RPM** |
| 1558 | Engine Load | sint16 | ÷10 | % |
| **1798–1799** | **Engine Operating Hours** | **uint32** | **×1** | **seconds ÷ 3600 = hours** |
| 1808–1809 | Engine Start Count | uint32 | ×1 | count |

---

## 7. Alarm / Fault Status Registers (GenComm Page 154)

**Base register:** 39425 (Page 154 × 256 + Offset 1)  
**Structure:** Each register holds **four 4-bit alarm slots**.

**4-bit alarm state values:**
| Value | Meaning |
|-------|---------|
| 0 | Disabled |
| 1 | Healthy (no alarm) |
| 2 | Warning |
| 3 | Shutdown |
| 4 | Electrical Trip |
| 15 | Unimplemented |

**Named Alarm Register Map (DSE8610 MK2):**

| Register | Bits 16–13 | Bits 12–9 | Bits 8–5 | Bits 4–1 |
|----------|-----------|-----------|----------|----------|
| 39425 | Emergency Stop | Low Oil Pressure | High Coolant Temperature | Low Coolant Temperature |
| 39426 | Under Speed | Over Speed | Generator Under Hz | Generator Over Hz |
| 39427 | Generator Low Voltage | Generator High Voltage | Battery Low Voltage | Battery High Voltage |
| 39428 | Charge Alternator Failure | Fail to Start | Fail to Stop | Generator Fail to Close |
| 39429 | Mains Fail to Close | Oil Pressure Sender Fault | Loss of MPU | MPU Open Circuit |
| 39430 | Generator Over Current | Controller Calibration Lost | Low Fuel Level | CAN ECU Warning |
| 39431 | CAN ECU Shutdown | CAN ECU Data Fail | Low Oil Level Switch | High Temperature Switch |
| 39432 | Low Fuel Level (switch) | Expansion Unit Watchdog | kW Overload Alarm | — |
| 39433 | Earth Fault Trip | Generator Phase Rotation | Auto Voltage Sense Fail | Maintenance Alarm |
| 39434 | Loading Frequency Alarm | Loading Voltage Alarm | Fuel Usage Running | Fuel Usage Stopped |
| 39435 | Protections Disabled | Protections Blocked | Generator Breaker Failed to Open | Mains Breaker Failed to Open |
| 39436 | Bus Breaker Failed to Close | Bus Breaker Failed to Open | Generator Reverse Power | Short Circuit Alarm |
| 39437 | Air Flap Closed | Failure to Sync | Bus Live | Bus Not Live |
| 39438 | Bus Phase Rotation | Priority Selection Error | MSC Data Error | MSC ID Error |
| 39439 | Bus Low Voltage | Bus High Voltage | Bus Low Frequency | Bus High Frequency |
| 39440 | MSC Failure | MSC Too Few Sets | MSC Alarms Inhibited | MSC Old Version Units |
| 39441 | Mains Reverse Power/Export | Minimum Sets Not Reached | Insufficient Capacity | Out of Sync |
| 39442 | Alternative Aux Mains Fail | Loss of Excitation | Mains ROCOF | Mains Vector Shift |
| 39443 | Mains Decoupling Low Freq | Mains Decoupling High Freq | Mains Decoupling Low Voltage | Mains Decoupling High Voltage |
| 39444 | Mains Decoupling Combined | Charge Air Temperature | Mains Phase Rotation | AVR Max Trim Limit |
| 39445 | High Coolant Temp Elec Trip | Temperature Sender Open Circuit | Out of Sync Bus | Out of Sync Mains |

**Reading alarm state example (Python):**
```python
def parse_alarm_register(raw_value, reg_offset):
    alarms = []
    for slot in range(4):
        bits = (raw_value >> (slot * 4)) & 0xF
        if bits not in (0, 1, 15):  # 0=disabled, 1=healthy, 15=unimplemented
            alarms.append({
                "register": 39425 + reg_offset,
                "slot": slot,
                "state": {2: "Warning", 3: "Shutdown", 4: "ElecTrip"}.get(bits, f"Unknown({bits})")
            })
    return alarms
```

**Digital Input alarms:** Registers 39169–39172 (DI 1–16, configurable labels).  
**PLC/User alarms:** Registers 39476–39478 (PLC Alarm 1–11).

---

## 8. Control Registers (System Control Function — SCF)

> **Warning:** Always read SCF Support Flags (registers 4096–4103) first to confirm which control functions the firmware supports before writing.

| Register | Purpose |
|----------|---------|
| 4096–4103 | SCF Support Flags (bitmask — read to check available commands) |
| 4104 | Write SCF control key |
| 4105 | Write bitwise complement of control key (65535 − key) |

Both registers 4104 and 4105 **must be written in a single multi-register write (FC 16)**.

| Key Value | Command |
|-----------|---------|
| 35701 | Select Auto Mode |
| 35732 | Telemetry Start |
| 35733 | Telemetry Stop |

> **Note:** The official GenComm document (available from DSE technical support) contains the full control command list. The above are the most commonly published values found in open sources.

---

## 9. Implementation Notes

**Polling strategy for monitoring:**
- Poll generator state (1408) and engine speed (1030) at 5s interval
- Poll AC measurements (1031–1057, 1536–1537) at 10s interval
- Poll alarm registers (39425–39445) at 10s interval
- Poll energy / run hours (1798–1799, 1800–1801) at 60s interval

**Alarm severity mapping for cloud platform:**
- State 2 (Warning) → alert notification to operator portal
- State 3 (Shutdown) → critical alarm + site alert
- State 4 (Electrical Trip) → critical alarm + immediate notification

---

## 10. Gaps and Actions

- [ ] **Obtain official DSE GenComm document** from DSE Technical Support (deepseaelectronics.com) — required for full control command list and any registers not listed above
- [ ] **Confirm Modbus TCP port** in DSE Configuration Suite (default 502 but not hardcoded)
- [ ] **Confirm voltage measurement type** (L-N vs L-L) per site installation
- [ ] Read DSE8610 MK2 Operator Manual Issue 10 (PDF at ers-cat.com) for site-specific configuration notes

---

## 11. Source Documents

| Document | URL |
|----------|-----|
| Senquip APN0029 — Modbus with DSE | http://cdn.senquip.com/wp-content/uploads/2024/04/18104724/APN0029-Rev-1.0-Modbus-Integration-With-Deep-Sea-Engine-Controller.pdf |
| Victron dse.py (authoritative register source) | https://github.com/victronenergy/dbus-modbus-client/blob/master/dse.py |
| DSE8610 MK2 Operator Manual Issue 10 | https://www.ers-cat.com/application/files/5617/0446/7487/DSE8610-MKII-Operator-Manual_5.pdf |
| DSE GenComm 2020 (Russian, 276pp) | https://energan.ru/bitrix/templates/landing24/download/gencomm-16-07-2020.pdf |
| DSE Standard Alarms CSV | https://github.com/jamesarbrown/modbus2sql/blob/master/dist/CSV%20Files/Deep%20Sea%20Electronics/Alarm%20List%20-%20Standard%20Alarms%20DSE%20Gencom.csv |
| Official GenComm doc | Available on request from DSE Technical Support (deepseaelectronics.com) |
