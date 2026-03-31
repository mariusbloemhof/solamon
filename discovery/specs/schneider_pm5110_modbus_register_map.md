# Schneider Electric PowerLogic PM5110 — Modbus RTU Register Map

**Device:** PowerLogic PM5000 Series — PM5110 (METSEPM5110)  
**Manufacturer:** Schneider Electric  
**Source:** PM51xx_PM53xx_PMC Register List v2011/v2021 R01 (Schneider authored; via jecrespo/IoT-POWERLOGIC_PM5150 GitHub)  
**Accuracy class:** 0.5S  
**Connectivity:** RS485 only (no native Ethernet) — requires MOXA gateway for cloud integration

---

## 1. RS485 Default Communication Settings

| Parameter | Default | Options |
|-----------|---------|---------|
| Protocol | Modbus RTU | 0=Modbus RTU, 1=Jbus, 2=Modbus ASCII 8-bit, 3=Modbus ASCII 7-bit |
| Slave Address | **1** | 1–247 |
| Baud Rate | **19200** | 0=9600, 1=19200, 2=38400 |
| Parity | **Even** | 0=Even, 1=Odd, 2=None |
| Stop Bits | 1 (with parity) | — |
| Data Bits | 8 | — |
| Framing | **8E1** | — |

**Configuration registers (R/W via FC 03/16):**

| Register | Parameter | Default |
|----------|-----------|---------|
| 6500 | Protocol (0=Modbus RTU) | 0 |
| 6501 | Slave Address | 1 |
| 6502 | Baud rate (0=9600, 1=19200, 2=38400) | 1 |
| 6503 | Parity (0=Even, 1=Odd, 2=None) | 0 |

---

## 2. Function Codes Supported

| FC | Operation |
|----|-----------|
| FC 01 (0x01) | Read Coils (alarm status) |
| FC 02 (0x02) | Read Discrete Inputs |
| FC 03 (0x03) | Read Holding Registers — primary data read |
| FC 06 (0x06) | Write Single Register |
| FC 16 (0x10) | Write Multiple Registers |

> All measurement registers use **FC 03**. All data is **FLOAT32 (IEEE 754), 2 consecutive 16-bit registers, big-endian (ABCD word order).**

---

## 3. Current Measurements (1-second metering, FC 03)

| Register | Parameter | Unit |
|----------|-----------|------|
| 3000 | Current A (Phase 1) | A |
| 3002 | Current B (Phase 2) | A |
| 3004 | Current C (Phase 3) | A |
| 3006 | Current N (Neutral) | A |
| 3010 | Current Average (phases) | A |
| 3012 | Current Unbalance A | % |
| 3014 | Current Unbalance B | % |
| 3016 | Current Unbalance C | % |
| 3018 | Current Unbalance Worst | % |

---

## 4. Voltage Measurements (1-second metering, FC 03)

| Register | Parameter | Unit |
|----------|-----------|------|
| 3020 | Voltage A-B (V12, L-L) | V |
| 3022 | Voltage B-C (V23, L-L) | V |
| 3024 | Voltage C-A (V31, L-L) | V |
| 3026 | Voltage L-L Average | V |
| 3028 | Voltage A-N (V1, L-N) | V |
| 3030 | Voltage B-N (V2, L-N) | V |
| 3032 | Voltage C-N (V3, L-N) | V |
| 3036 | Voltage L-N Average | V |
| 3038 | Voltage Unbalance A-B | % |
| 3040 | Voltage Unbalance B-C | % |
| 3042 | Voltage Unbalance C-A | % |
| 3044 | Voltage Unbalance L-L Worst | % |
| 3046 | Voltage Unbalance A-N | % |
| 3048 | Voltage Unbalance B-N | % |
| 3050 | Voltage Unbalance C-N | % |
| 3052 | Voltage Unbalance L-N Worst | % |

---

## 5. Power Measurements (1-second metering, FC 03)

### Active Power

| Register | Parameter | Unit |
|----------|-----------|------|
| 3054 | Active Power A | kW |
| 3056 | Active Power B | kW |
| 3058 | Active Power C | kW |
| **3060** | **Active Power Total** | **kW** |

### Reactive Power

| Register | Parameter | Unit |
|----------|-----------|------|
| 3062 | Reactive Power A | kVAR |
| 3064 | Reactive Power B | kVAR |
| 3066 | Reactive Power C | kVAR |
| **3068** | **Reactive Power Total** | **kVAR** |

### Apparent Power

| Register | Parameter | Unit |
|----------|-----------|------|
| 3070 | Apparent Power A | kVA |
| 3072 | Apparent Power B | kVA |
| 3074 | Apparent Power C | kVA |
| **3076** | **Apparent Power Total** | **kVA** |

---

## 6. Power Factor (1-second metering, FC 03)

> **Important:** Registers 3078–3092 use a **four-quadrant encoded float (4Q_FP_PF)** — values outside the −1 to +1 range encode the quadrant:
> - If value > 1.0: PF = 2.0 − value (leading/capacitive)
> - If value < −1.0: PF = −2.0 − value (leading)
> - Otherwise: PF = value (lagging/inductive)

| Register | Parameter |
|----------|-----------|
| 3078 | Power Factor A (4Q encoded) |
| 3080 | Power Factor B (4Q encoded) |
| 3082 | Power Factor C (4Q encoded) |
| 3084 | Power Factor Total (4Q encoded) |
| **3192** | **Power Factor Total — simple float (IEC convention)** |
| **3194** | **Power Factor Total — simple float (Lead/Lag)** |

**Recommendation:** Use register **3192** (simple FLOAT32) to avoid quadrant decoding.

---

## 7. Frequency (1-second metering, FC 03)

| Register | Parameter | Unit |
|----------|-----------|------|
| **3110** | **Frequency** | **Hz** |

---

## 8. Energy Registers — FLOAT32 (preferred for implementation)

**Format:** FLOAT32, two registers each. Values in kWh/kVARh/kVAh — ready to use.

| Register | Parameter | Unit |
|----------|-----------|------|
| **2700** | **Active Energy Delivered (Import)** | **kWh** |
| **2702** | **Active Energy Received (Export)** | **kWh** |
| 2704 | Active Energy Total (Delivered + Received) | kWh |
| 2706 | Active Energy Net (Delivered − Received) | kWh |
| 2708 | Reactive Energy Delivered (Import) | kVARh |
| 2710 | Reactive Energy Received (Export) | kVARh |
| 2712 | Reactive Energy Total | kVARh |
| 2714 | Reactive Energy Net | kVARh |
| 2716 | Apparent Energy Delivered | kVAh |
| 2718 | Apparent Energy Received | kVAh |
| 2720 | Apparent Energy Total | kVAh |
| 2722 | Apparent Energy Net | kVAh |

---

## 9. Energy Registers — INT64 (high precision, 4 registers each)

For revenue-metering applications requiring Wh resolution rather than kWh.  
**Reading:** `Energy_Wh = reg[0]<<48 | reg[1]<<32 | reg[2]<<16 | reg[3]` (big-endian)

| Register | Parameter | Unit |
|----------|-----------|------|
| 3204 | Active Energy Delivered (Import) | Wh |
| 3208 | Active Energy Received (Export) | Wh |
| 3212 | Active Energy Total | Wh |
| 3216 | Active Energy Net | Wh |
| 3220 | Reactive Energy Delivered | VARh |
| 3224 | Reactive Energy Received | VARh |
| 3236 | Apparent Energy Delivered | VAh |
| 3240 | Apparent Energy Received | VAh |

> **For billing:** the PM5110 is Class 0.5S but has **no TOU engine** on its data output. TOU differentiation must be done in the cloud platform by timestamping incoming energy readings against a tariff schedule. This is a key limitation vs the Acuvim L.

---

## 10. Demand Registers (FC 03)

### Active Power Demand

| Register | Parameter | Unit |
|----------|-----------|------|
| 3764 | Last Power Demand | kW |
| 3766 | Present Power Demand | kW |
| 3768 | Predicted Power Demand | kW |
| **3770** | **Peak Power Demand** | **kW** |
| 3772 | Peak Power Demand DateTime | — |

### Reactive Power Demand

| Register | Parameter | Unit |
|----------|-----------|------|
| 3780 | Last Reactive Demand | kVAR |
| 3782 | Present Reactive Demand | kVAR |
| 3784 | Predicted Reactive Demand | kVAR |
| 3786 | Peak Reactive Demand | kVAR |

### Apparent Power Demand

| Register | Parameter | Unit |
|----------|-----------|------|
| 3796 | Last Apparent Demand | kVA |
| 3798 | Present Apparent Demand | kVA |
| 3800 | Predicted Apparent Demand | kVA |
| 3802 | Peak Apparent Demand | kVA |

### Current Demand

| Register | Parameter | Unit |
|----------|-----------|------|
| 3876 | Last Current Demand | A |
| 3878 | Present Current Demand | A |
| 3880 | Predicted Current Demand | A |
| 3882 | Peak Current Demand | A |

**Demand configuration:** Register 3701 (Method), 3702 (Interval, minutes), 3703 (Subinterval).

---

## 11. Alarm Status Registers

### Bitmap Registers (FC 03, read as 16-bit holding registers)

| Register | Description |
|----------|-------------|
| 2420 | Standard Alarm Group 1 Validity bitmap |
| **2421** | **Standard Alarm Group 1 Detected bitmap** |
| 2422 | Standard Alarm Group 2 Validity bitmap |
| **2423** | **Standard Alarm Group 2 Detected bitmap** |
| 2440 | Unary Alarm Validity bitmap |
| **2441** | **Unary Alarm Detected bitmap** |

**Register 2421 — bit assignments:**

| Bit | Alarm |
|-----|-------|
| 0 | Over Current (phase) |
| 1 | Under Current (phase) |
| 2 | Over Current (neutral) |
| 4 | Over Voltage (L-L) |
| 5 | Under Voltage (L-L) |
| 6 | Over Voltage (L-N) |
| 7 | Under Voltage (L-N) |
| 8 | Over Active Power |
| 9 | Over Reactive Power |
| 10 | Over Apparent Power |
| 11 | Leading Power Factor (True) |
| 12 | Lagging Power Factor (True) |
| 15 | Over Demand (Active Power, Present) |

**Register 2423 — bit assignments:**

| Bit | Alarm |
|-----|-------|
| 0–7 | Demand alarms (Last/Predicted for Active/Reactive/Apparent) |
| 8 | Over Frequency |
| 9 | Under Frequency |
| 10 | Over Voltage Unbalance |
| 11 | Over Voltage THD |
| 12 | Phase Loss |

**Register 2441 — System alarms:**

| Bit | Alarm |
|-----|-------|
| 0 | Meter Power Up (control power was lost) |
| 1 | Meter Reset |
| 2 | Meter Diagnostic |
| 3 | Phase Reversal |

---

## 12. THD — Harmonic Distortion (up to 15th harmonic on PM5110)

| Register | Parameter | Unit |
|----------|-----------|------|
| 21300 | THD Current A | % |
| 21302 | THD Current B | % |
| 21304 | THD Current C | % |
| 21306 | THD Current N | % |
| 21330 | THD Voltage A-N | % |
| 21332 | THD Voltage B-N | % |
| 21334 | THD Voltage C-N | % |

---

## 13. Implementation Notes

**Register addressing convention:** This map uses 1-based addresses (as per Schneider documentation). If your Modbus library uses 0-based addressing, subtract 1 from each register number.

**FLOAT32 byte order:** Big-endian ABCD word order. Read registers N and N+1; combine with:
```python
import struct
raw = [reg_n, reg_n1]
value = struct.unpack('>f', struct.pack('>HH', raw[0], raw[1]))[0]
```

**No TOU support:** Unlike the Acuvim L, the PM5110 does not compute TOU-differentiated energy. For billing on PM5110-equipped sites, the cloud platform must apply a tariff schedule to timestamped energy readings. This means the platform needs time-aligned energy deltas, not just cumulative counters.

**Gateway requirement:** PM5110 is RS485-only. An MOXA NPort or equivalent RS485-to-Ethernet converter is required. The MOXA device presents the PM5110 as Modbus TCP to the edge agent.

---

## 14. Source Documents

| Document | URL |
|----------|-----|
| Schneider PM5000 Register List (FA234017) | https://www.se.com/us/en/faqs/FA234017/ (browser access required) |
| Register List XLS (GitHub mirror) | https://github.com/jecrespo/IoT-POWERLOGIC_PM5150/blob/main/docs/PM51xx_PM53xx_PMC%20Register%20List_v2011_v2021_R01.xls |
| User Manual EAV15105 | https://www.productinfo.schneider-electric.com/pm5100/ |
