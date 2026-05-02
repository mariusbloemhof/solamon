# AccuEnergy Acuvim-L — Modbus TCP Register Map

**Device:** Acuvim-L Series Multifunction Power and Energy Meter  
**Manufacturer:** AccuEnergy  
**Source:** Acuvim-L Series User Manual V2.0.3 (December 2025)  
**Modbus TCP port:** 502 (default; user range 2000–5999)  
**Function codes:** FC 03 (read holding registers), FC 16 (write multiple registers)  
**Byte order:** Big-endian (ABCD)

---

## 1. Communication Settings

| Interface | Default | Notes |
|-----------|---------|-------|
| Ethernet 1 (primary) | 192.168.1.254 static | Subnet 255.255.255.0, GW 192.168.1.1 |
| Ethernet 2 | DHCP | Check meter display N12 for IP |
| Wi-Fi AP | 192.168.100.1 | SSID: AXM-WEB2-WIFI-[serial]; password: accuenergy |
| Modbus TCP port | 502 | |
| Web interface | HTTP port 80 / HTTPS port 443 | Login: admin / admin |

**RS485 settings** (registers 0x0101–0x0112 are R/W via FC 03/16):
- Address: 1–247 (register 0x0101)
- Baud rate: 1200–57600 (register 0x0102)
- Parity: 0=Even, 1=Odd, 2=None-2stop, 3=None-1stop (register 0x0112)

---

## 2. Parameter Settings (R/W, 0x0100–0x0118)

| Hex Addr | Parameter | Range / Values |
|----------|-----------|----------------|
| 0x0100 | Access password | 0–9999 |
| 0x0101 | Modbus address | 1–247 |
| 0x0102 | Baud rate | 1200–57600 |
| 0x0103 | Voltage wiring type | 0=3LN, 1=3LL, 2=2LL, 3=1LN, 4=1LL |
| 0x0104 | Current wiring type | 0=3CT, 1=2CT, 2=1CT |
| 0x0105–0x0106 | PT1 primary (high+low) | 50.0–1,000,000.0 V |
| 0x0107 | PT2 secondary | 50.0–400.0 V |
| 0x0108 | CT1 primary | 1–50000 A |
| 0x0109 | CT2 secondary | 1, 5, or 333 mV |
| 0x010C | Demand sliding window | 1–30 min |
| 0x010F | Clear energy (0x0A = execute) | — |
| 0x0112 | Parity | 0=Even, 1=Odd, 2=None-2stop, 3=None-1stop |

---

## 3. Real-Time Measurements — Secondary Address (0x0130–0x0155)

**Scaling formulas:**
- V = Rx × (PT1/PT2) / 10 [V]
- I = Rx × (CT1/CT2) / 1000 [A]
- P/Q/S = Rx × (PT1/PT2) × (CT1/CT2) [W/var/VA]
- PF = Rx / 1000
- F = Rx / 100 [Hz]
- Unbalance = (Rx/1000) × 100%

| Hex Addr | Parameter | Type |
|----------|-----------|------|
| 0x0130 | Frequency | Word |
| 0x0131 | Phase voltage V1 (L-N) | Word |
| 0x0132 | Phase voltage V2 | Word |
| 0x0133 | Phase voltage V3 | Word |
| 0x0134 | Line voltage V12 (L-L) | Word |
| 0x0135 | Line voltage V23 | Word |
| 0x0136 | Line voltage V31 | Word |
| 0x0137 | Phase current I1 | Word |
| 0x0138 | Phase current I2 | Word |
| 0x0139 | Phase current I3 | Word |
| 0x013A | Neutral current In | Word |
| 0x013B | Phase active power Pa | Integer (signed) |
| 0x013C | Phase active power Pb | Integer |
| 0x013D | Phase active power Pc | Integer |
| 0x013E | System total active power Psum | Integer |
| 0x013F | Phase reactive power Qa | Integer |
| 0x0141 | Phase reactive power Qb | Integer |
| 0x0142 | System reactive power Qsum | Integer |
| 0x0143 | System apparent power Ssum | Word |
| 0x0144 | Power factor PFa | Integer |
| 0x0145 | Power factor PFb | Integer |
| 0x0146 | Power factor PFc | Integer |
| 0x0147 | System power factor PFsum | Integer |
| 0x0148 | Voltage unbalance | Word |
| 0x0149 | Current unbalance | Word |
| 0x014A | Load type (L/C/R) | Word (76/67/82) |
| 0x014B | Apparent power Sa | Integer |
| 0x014C | Apparent power Sb | Integer |
| 0x014D | Apparent power Sc | Integer |
| 0x014F | Apparent power demand | Integer |
| 0x0150 | Active power demand P_Dmd | Integer |
| 0x0151 | Reactive power demand | Integer |
| 0x0152 | Phase A current demand | Word |
| 0x0153 | Phase B current demand | Word |
| 0x0154 | Phase C current demand | Word |

---

## 4. Real-Time Measurements — Primary Address (0x0600–0x064B)

**Format:** IEEE 754 Float32 (2 registers each, big-endian). Values in engineering units — **no scaling required.**

| Hex Addr | Parameter | Unit |
|----------|-----------|------|
| 0x0600–0x0601 | Frequency | Hz |
| 0x0602–0x0603 | Phase voltage V1 | V |
| 0x0604–0x0605 | Phase voltage V2 | V |
| 0x0606–0x0607 | Phase voltage V3 | V |
| 0x0608–0x0609 | Line voltage V12 | V |
| 0x060A–0x060B | Line voltage V23 | V |
| 0x060C–0x060D | Line voltage V31 | V |
| 0x060E–0x060F | Phase current I1 | A |
| 0x0610–0x0611 | Phase current I2 | A |
| 0x0612–0x0613 | Phase current I3 | A |
| 0x0614–0x0615 | Neutral current In | A |
| 0x0616–0x0617 | Phase active power Pa | W |
| 0x0618–0x0619 | Phase active power Pb | W |
| 0x061A–0x061B | Phase active power Pc | W |
| **0x061C–0x061D** | **System total active power Psum** | **W** |
| 0x061E–0x061F | Phase reactive power Qa | var |
| 0x0620–0x0621 | Phase reactive power Qb | var |
| 0x0622–0x0623 | Phase reactive power Qc | var |
| **0x0624–0x0625** | **System reactive power Qsum** | **var** |
| **0x0626–0x0627** | **System apparent power Ssum** | **VA** |
| 0x0628–0x0629 | Power factor PFa | — |
| 0x062A–0x062B | Power factor PFb | — |
| 0x062C–0x062D | Power factor PFc | — |
| **0x062E–0x062F** | **System power factor PFsum** | **—** |
| 0x0630–0x0631 | Voltage unbalance | % |
| 0x0632–0x0633 | Current unbalance | % |
| 0x0636–0x0637 | Apparent power Sa | VA |
| 0x0638–0x0639 | Apparent power Sb | VA |
| 0x063A–0x063B | Apparent power Sc | VA |
| 0x063E–0x063F | Apparent power demand | VA |
| 0x0640–0x0641 | Active power demand P_Dmd | W |
| 0x0642–0x0643 | Reactive power demand | var |
| 0x0644–0x0645 | Phase A current demand | A |
| 0x0646–0x0647 | Phase B current demand | A |
| 0x0648–0x0649 | Phase C current demand | A |

> **Implementation note:** Prefer the primary Float32 registers (0x0600+) for simplicity. Use secondary registers (0x0130+) only if Float32 is not supported by your Modbus master library.

---

## 5. Fast Read Mode (Modbus TCP only, 100ms update)

Enable via AXM-WEB2 web interface. When enabled, all other protocols are suspended.

| Hex Addr | Parameter | Unit |
|----------|-----------|------|
| 0x3000–0x3001 | Frequency | Hz |
| 0x3002–0x3003 | Va | V |
| 0x3004–0x3005 | Vb | V |
| 0x3006–0x3007 | Vc | V |
| 0x300A–0x300B | Vab | V |
| 0x300C–0x300D | Vbc | V |
| 0x300E–0x300F | Vca | V |
| 0x3012–0x3013 | Ia | A |
| 0x3014–0x3015 | Ib | A |
| 0x3016–0x3017 | Ic | A |
| 0x301C–0x301D | Pa | W |
| 0x301E–0x301F | Pb | W |
| 0x3020–0x3021 | Pc | W |
| 0x3022–0x3023 | Psum | W |
| 0x302A–0x302B | Qsum | var |
| 0x3032–0x3033 | Ssum | VA |
| 0x303A–0x303B | PFsum | — |

**50ms Fast Read (0x3400–0x341D):** Va/b/c, Vab/bc/ca, Ia/b/c, Psum, Qsum, Frequency (Float32).

---

## 6. Energy Registers (R/W, 0x0156–0x017D)

**Format:** Dword (2 registers, high word first). **Scaling: Rx / 10 [kWh or kVArh or kVAh].**  
Write value 0 to reset. All R/W.

| Hex Addr | Parameter | Unit |
|----------|-----------|------|
| **0x0156–0x0157** | **System import active energy Ep_imp** | **kWh** |
| **0x0158–0x0159** | **System export active energy Ep_exp** | **kWh** |
| 0x015A–0x015B | System import reactive energy Eq_imp | kVArh |
| 0x015C–0x015D | System export reactive energy Eq_exp | kVArh |
| 0x015E–0x015F | System apparent energy Es | kVAh |
| 0x0160–0x0161 | Phase-A import active energy | kWh |
| 0x0162–0x0163 | Phase-A export active energy | kWh |
| 0x0164–0x0165 | Phase-B import active energy | kWh |
| 0x0166–0x0167 | Phase-B export active energy | kWh |
| 0x0168–0x0169 | Phase-C import active energy | kWh |
| 0x016A–0x016B | Phase-C export active energy | kWh |
| 0x016C–0x016D | Phase-A reactive import energy | kVArh |
| 0x016E–0x016F | Phase-A reactive export energy | kVArh |
| 0x0170–0x0171 | Phase-B reactive import energy | kVArh |
| 0x0172–0x0173 | Phase-B reactive export energy | kVArh |
| 0x0174–0x0175 | Phase-C reactive import energy | kVArh |
| 0x0176–0x0177 | Phase-C reactive export energy | kVArh |

---

## 7. TOU Energy Registers (R/W)

**Scaling:** Rx / 10 [kWh / kVArh / kVAh]. Each tariff has 5 Dword pairs: Ep_imp, Ep_exp, Eq_imp, Eq_exp, Es.

### Current Month (0x0200–0x0231)

| Hex Addr Range | Tariff |
|----------------|--------|
| 0x0200–0x0209 | Sharp (tariff 1) |
| 0x020A–0x0213 | Peak (tariff 2) |
| 0x0214–0x021D | Valley (tariff 3) |
| 0x021E–0x0227 | Normal (tariff 4) |
| 0x0228–0x0231 | Sum (all tariffs) |

### Last Month (0x0232–0x0263) — same structure

---

## 8. TOU Configuration Registers (R/W, 0x0800–0x0AEC)

| Hex Addr | Parameter | Range |
|----------|-----------|-------|
| 0x0800 | Number of seasons (time zones) | 0–12 |
| 0x0801 | Number of schedules (time tables) | 0–14 |
| 0x0802 | Number of intervals per schedule | 0–14 |
| 0x0803 | Number of tariffs (fees) | 0–3 |
| 0x0807 | TOU enable | 1=enabled |
| 0x0809 | Reset method | 0=end-of-month, 1=assigned date |
| 0x080A | Reset day | 1–31 |
| 0x080E | TOU error status | bitmask |
| 0x0820–0x0843 | Season table (12 entries × 3 reg) | MM, DD, schedule_ID |
| 0x0844–0x086D | Schedule 1 (14 segments × 3 reg) | HH, MM, tariff_ID |
| 0x086E–0x0897 | Schedule 2 | — |
| ... | Schedules 3–14 | — |
| 0x0A90–0x0AE9 | Special days (30 entries × 3 reg) | MM, DD, schedule_ID |
| 0x0AEA | Holiday enable | — |

---

## 9. Statistics — Max/Min with Timestamps (0x1000–0x105F)

Each entry: 4 registers [value_HH, value_LL, date(yy/mm dd/hh), time(mm/ss)].

| Hex Range | Parameter |
|-----------|-----------|
| 0x1000–0x1003 | Max V1 + timestamp |
| 0x1004–0x1007 | Max V2 + timestamp |
| 0x1008–0x100B | Max V3 + timestamp |
| 0x100C–0x100F | Max V12 + timestamp |
| 0x1010–0x1013 | Max V23 + timestamp |
| 0x1014–0x1017 | Max V31 + timestamp |
| 0x1018–0x101B | Max I1 + timestamp |
| 0x101C–0x101F | Max I2 + timestamp |
| 0x1020–0x1023 | Max I3 + timestamp |
| 0x1024–0x1027 | Max active power demand PDmd_MAX |
| 0x1038–0x103B | Max apparent demand SDmd_MAX |
| 0x103C–0x103F | Min V1 + timestamp |
| ... | Min V2, V3, V12, V23, V31, I1–I3 |

---

## 10. Power Quality / Harmonics (0x0400–0x04B9)

**Scaling:** THD% = (Rx / 10000) × 100. Harmonics same scale.

| Hex Addr | Parameter |
|----------|-----------|
| 0x0400 | THD V1 |
| 0x0401 | THD V2 |
| 0x0402 | THD V3 |
| 0x0403 | THD I1 |
| 0x0404 | THD I2 |
| 0x0405 | THD I3 |
| 0x0406–0x0423 | V1 harmonics 2nd–31st |
| 0x0424–0x0441 | V2 harmonics 2nd–31st |
| 0x0442–0x045F | V3 harmonics 2nd–31st |
| 0x0460–0x047D | I1 harmonics 2nd–31st |
| 0x047E–0x049B | I2 harmonics 2nd–31st |
| 0x049C–0x04B9 | I3 harmonics 2nd–31st |

> **EL-grade Acuvim-EL extends to 63rd harmonic** (0x0400–0x06FF range).

---

## 11. Clock (R/W, 0x0184–0x018A)

| Hex Addr | Parameter |
|----------|-----------|
| 0x0184 | Year (2000–2099) |
| 0x0185 | Month (1–12) |
| 0x0186 | Day (1–31) |
| 0x0187 | Hour (0–23) |
| 0x0188 | Minute (0–59) |
| 0x0189 | Second (0–59) |
| 0x018A | Day of week (0–6) |

---

## 12. Digital Output / Input Settings (R/W, 0x03C0–0x03D2)

| Hex Addr | Parameter |
|----------|-----------|
| 0x03C0 | DO1 function (0=pulse, 1=alarm) |
| 0x03C1 | DO2 function |
| 0x03C4 | DO1 energy output type (0=none, 1=Ep_imp, 2=Ep_exp, 3=Eq_imp, 4=Eq_exp) |
| 0x03C7 | DO1 alarm parameter |
| 0x03C8 | DO1 alarm condition (0=below, 1=above) |
| 0x03C9 | DO1 alarm limit |
| 0x03D0 | DI type (0=SOE/event, 1=counter, per bit per channel) |

> **Note:** Alarm configuration is managed via the AXM-WEB2 web interface, not Modbus registers. 16 alarm channels are available but not addressable via Modbus.

---

## 13. Run Time (R/W, 0x0180–0x0183)

| Hex Addr | Parameter | Scaling |
|----------|-----------|---------|
| 0x0180–0x0181 | Meter run time | ×0.1 hr (Dword) |
| 0x0182–0x0183 | Load run time | ×0.1 hr (Dword) |

---

## 14. Device identity — none on the wire

**Important:** The Acuvim L manual V2.0.3 (December 2025) documents **no identity registers** — no manufacturer code, model code, firmware version, or serial number is exposed via Modbus. Sister product Acuvim II exposes a SunSpec common-model block at `0xC350`+; the Acuvim L does not.

**Implication for fingerprinting:** the edge agent identifies an Acuvim L via a **negative fingerprint** — read `0xC350` and expect a Modbus exception `0x02` (illegal data address) — combined with positive capability probes at `0x0130` (frequency, secondary) or `0x0600` (frequency, primary Float32).

**Implication for site records:** capture serial number, firmware version, and Acuvim L sub-variant (`CL` / `DL` / `EL` / `KL`) from the **physical device label** or the **AXM-WEB2 web UI** at commissioning, and store them in the cloud `Device` record. There's no automated way to read these over Modbus.

---

## 15. Sub-variants — comms-capable Acuvim L

The Acuvim L family has six sub-variants per the manual §1.4:

| Variant | Comms? | I/O | Notes |
|---------|--------|-----|-------|
| `AL` | **No** | base | No comms port — out of scope for this project |
| `BL` | **No** | base + 2 DO | No comms port — out of scope |
| `CL` | RS485 | base | Comms-capable; standard install |
| `DL` | RS485 | base + extended I/O | Comms-capable |
| `EL` | RS485 | DL + TOU support | Comms-capable; needed for TOU billing features |
| `KL` | RS485 | simplified CL | Comms-capable |

**The Modbus register map is identical across CL / DL / EL / KL.** Sub-variant only affects which physical I/O is wired and (for EL) whether TOU energy registers are populated. Capture the variant at commissioning from the device label, not from the wire.
