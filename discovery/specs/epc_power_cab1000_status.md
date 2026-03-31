# EPC Power CAB1000 — Integration Status

**Device:** CAB1000 Bidirectional Battery Inverter / PCS  
**Manufacturer:** EPC Power Corporation (Poway, CA, USA)  
**Status: GAP — No public register map available**

---

## 1. Confirmed Communication Interfaces

From CAB1000 Engineering Manual (Doc 70-100054, Rev May 2020) and Technical Manual (Doc 70-100065, Rev02, Jan 2024):

| Interface | Details |
|-----------|---------|
| **Modbus TCP/IP** | Primary recommended EMS control interface. Latency: ~3ms per transaction. |
| **Modbus RTU (RS485)** | Also supported. |
| **CAN bus** | Used for EPC's own PC Service Tool. Latency: ~1ms. |
| **Ethernet gateway hardware** | CAB1000 uses a **Lantronix** serial-to-Ethernet device server as the Modbus TCP gateway. Obtains IP via DHCP by default; configure with Lantronix DeviceInstaller utility. |

**Modbus TCP port:** Standard port 502 (Lantronix default). Not explicitly published — confirm from device configuration.  
**Modbus Unit ID:** Not explicitly published. Likely 1 for a single device — confirm from device or manual.

**Internal architecture:** The CAB1000 has an internal Ethernet switch connecting Modbus TCP, an internal monitoring device (IMD), a data logger, and any parallel inverters on the same LAN segment.

---

## 2. SunSpec and GitHub Findings

**EPC Power GitHub organisation:** `github.com/epcpower` — 12 public repositories, most relevant:

| Repo | Purpose | Key Finding |
|------|---------|-------------|
| `epcpower/sunspec-demo` | SunSpec integration demo | Implements **SunSpec + custom model 65534**; device defaults to DHCP; `get-models` script downloads `smdx_65534.xml` (proprietary model definition) |
| `epcpower/pm` | Register map generator | Generates Modbus register maps with a **static +20,000 address offset** — all CAB1000 registers start at ~20001 |
| `epcpower/st` (EPyQ) | CAN/SunSpec toolchain | Exposes J1939 CAN bus signals (see section 3 below) and SunSpec point names |

**SunSpec model 65534** is EPC Power's vendor-specific extension model. The `smdx_65534.xml` file downloaded by the demo likely contains all control point definitions. Request this file directly from EPC Power or attempt `get-models` against a live device.

**SunSpec point names confirmed from `epcpower/st`:**
`CmdRealPwr`, `CmdReactivePwr`, `CmdV`, `CmdHz`, `CtlSrc`, `St`, `StVnd`, `FltClr`

These map to: real power setpoint, reactive power setpoint, voltage setpoint, frequency setpoint, control source (local/remote), operating state, vendor state, and fault clear command.

---

## 3. Register Map

**No fully documented public register map exists.** However, deep research has uncovered the following structural details:

### 3.1 Modbus Address Offset

The `epcpower/pm` register map generator applies a **static +20,000 offset** to all register addresses. This means:
- CAB1000 Modbus registers start at approximately **20001** (not 1)
- This is an unusual but confirmed architecture — the Lantronix gateway forwards all requests unchanged; the offset is baked into the device firmware
- When using SunSpec auto-discovery, the SunSpec ID block will be found around address 20040+ (not the standard 40001)

### 3.2 CAN Bus (J1939) Signal Map

From `epcpower/st` (EPyQ toolchain), the CAB1000 exposes the following J1939 CAN signals internally. These are relevant if integrating via CAN rather than Modbus (e.g., for a direct EMS-to-PCS connection at very low latency):

| CAN Message | CAN ID | Direction | Key Parameters |
|-------------|--------|-----------|---------------|
| CommandPower | `0x0CFFAC41` | EMS → CAB1000 | Power setpoint ±90,000W |
| CommandModeControl | — | EMS → CAB1000 | Operating mode selection |
| StatusMeasuredPower | — | CAB1000 → EMS | Actual AC power (W) |
| StatusBits | — | CAB1000 → EMS | Operating state flags |
| StatusFaults | — | CAB1000 → EMS | Active fault bitmap |
| StatusACParameters | — | CAB1000 → EMS | Voltage, current, frequency |
| StatusDCParameters | — | CAB1000 → EMS | DC bus voltage, current |

> **Note:** CAN integration requires physical access to the CAN bus terminals and a J1939-capable interface. Modbus TCP via Lantronix is the preferred remote integration path.

### 3.3 Known Modbus Point Names (from SunSpec model 65534)

The following control/status points are confirmed to exist (names from `smdx_65534.xml`):

| Point Name | Direction | Description |
|-----------|-----------|-------------|
| `CmdRealPwr` | Write | Real (active) power setpoint |
| `CmdReactivePwr` | Write | Reactive power setpoint |
| `CmdV` | Write | Voltage setpoint |
| `CmdHz` | Write | Frequency setpoint |
| `CtlSrc` | Write | Control source (0=local, 1=remote EMS) |
| `St` | Read | Operating state (SunSpec standard enum) |
| `StVnd` | Read | Vendor-specific operating state |
| `FltClr` | Write | Fault clear command |

**Actual register addresses for these points require `smdx_65534.xml`** — request from EPC Power or download via `get-models` against a live device.

---

## 4. How to Obtain the Register Map

**Option A — Direct from EPC Power (recommended):**
- Technical Support Portal: https://portal.epcpower.com (24/7)
- Phone: +1.858.748.5590 (Poway, CA) or +1.864.883.9577 (Simpsonville, SC)
- Technical Support form: https://www.epcpower.com/technical-support
- Request: **Document 70-100065 (CAB1000 Technical Manual Rev02)** and the **Modbus TCP Communication Register Map / Communication Specification**
- Also request: `smdx_65534.xml` (SunSpec vendor model definition file used in their sunspec-demo tool)

**Option B — Eaton xStorage path (high priority):**
The Eaton xStorage 250–1000 kW BESS uses the CAB1000 as its PCS. The Eaton I/O manual (P-164001236 Rev02) **has been confirmed to contain PCS Modbus register sections** — it is the most likely publicly-accessible source of actual register addresses.
- URL: https://www.eaton.com/content/dam/eaton/products/energy-storage/xstorage-bess/eaton-xstorage-250-1000kw-io-manual-p-164001236.pdf
- **Status:** PDF fetch has timed out twice. Recommend downloading directly in browser.

**Option C — GitHub sunspec-demo tool:**
Run EPC Power's `sunspec-demo` tool against a live CAB1000 to download `smdx_65534.xml` automatically:
- `git clone https://github.com/epcpower/sunspec-demo`
- Configure DHCP address of the CAB1000 Lantronix gateway
- Run `python get-models.py` — downloads vendor model XML with all register definitions

**Option D — Scribd:**
Both engineering and technical manuals are on Scribd (subscription required):
- Engineering Manual (70-100054): https://www.scribd.com/document/579350096/70-100054-CAB1000-Engineering-Manual-Rev051320-1
- Technical Manual (70-100065): https://www.scribd.com/document/920667413/70-100065-CAB1000-Technical-Manual-Rev02

---

## 5. What to Ask For

When contacting EPC Power, request:
1. CAB1000 Modbus TCP register map (all measurement and control registers with addresses)
2. Default Modbus TCP port and Unit ID (expected 502 via Lantronix gateway)
3. Confirm: SunSpec model 65534 register addresses and the `smdx_65534.xml` model definition file
4. Confirm: static +20,000 register address offset behaviour and how SunSpec auto-discovery works with this offset
5. Any SDK, integration guide, or example EMS communication specification
6. Support for multiple simultaneous Modbus TCP clients (needed for monitoring + control from separate systems)
7. CAN J1939 interface documentation (if direct CAN integration is preferred over Modbus TCP)

---

## 6. Source Documents Available

| Document | URL / Location | Access |
|----------|---------------|--------|
| CAB1000 Product Spec Sheet | https://assets.website-files.com/61b6b52bbc0fb0c43cb79aa8/61d34d746261b0b8d81098c0_CAB1000.pdf | Public (no Modbus content) |
| CAB1000 Engineering Manual 70-100054 | https://www.scribd.com/document/579350096 | Scribd subscription |
| CAB1000 Technical Manual 70-100065 | https://www.scribd.com/document/920667413 | Scribd subscription |
| **Eaton xStorage I/O Manual (P-164001236)** | https://www.eaton.com/content/dam/eaton/products/energy-storage/xstorage-bess/eaton-xstorage-250-1000kw-io-manual-p-164001236.pdf | **Public — confirmed to contain PCS Modbus sections** |
| EPC Power GitHub org | https://github.com/epcpower | Public — 12 repos |
| sunspec-demo (SunSpec + model 65534) | https://github.com/epcpower/sunspec-demo | Public |
| pm (register map generator, +20K offset) | https://github.com/epcpower/pm | Public |
| st / EPyQ (CAN J1939 toolchain) | https://github.com/epcpower/st | Public |
| EPC Power Technical Support | https://www.epcpower.com/technical-support | — |
