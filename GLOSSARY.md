# Solar Monitor — Glossary

**Purpose:** Plain-language reference for every acronym, vendor, protocol, and piece of in-house jargon that appears in this project. Written for two audiences: Marius (learning the energy domain) and Johan (decoding our software jargon).

> **How to use:** Sections are grouped by domain. Each entry has the expansion, a one-paragraph explanation, and where useful a **In our system** note explaining how the term applies specifically to the Solar Monitor platform.

---

## Quick navigation

1. [Electrical fundamentals](#1-electrical-fundamentals)
2. [Solar PV terminology](#2-solar-pv-terminology)
3. [Battery storage terminology](#3-battery-storage-terminology)
4. [Grid & utility — including South Africa](#4-grid--utility--including-south-africa)
5. [Metering, billing & tariffs](#5-metering-billing--tariffs)
6. [Communication protocols](#6-communication-protocols)
7. [Modbus deep dive](#7-modbus-deep-dive)
8. [Networking & IT infrastructure](#8-networking--it-infrastructure)
9. [Equipment vendors & products](#9-equipment-vendors--products)
10. [Site infrastructure](#10-site-infrastructure)
11. [Software architecture (our stack)](#11-software-architecture-our-stack)
12. [Project-specific jargon](#12-project-specific-jargon)

---

## 1. Electrical fundamentals

| Term | Meaning |
|------|---------|
| **AC** | Alternating Current — the form electricity takes on the grid (in SA, 230 V at 50 Hz). Voltage and current cycle direction 50 times per second. |
| **DC** | Direct Current — flows in one direction. Solar panels and batteries are inherently DC; an inverter converts it to AC for grid use. |
| **V** (Volt) | Unit of electrical pressure. SA single-phase is 230 V; three-phase is 400 V (line-to-line). |
| **A** (Amp / Ampere) | Unit of electrical current — how much charge flows per second. |
| **Hz** (Hertz) | Cycles per second of AC. SA grid runs at 50 Hz; deviation outside ~49.5–50.5 Hz indicates grid stress. |
| **W / kW / MW** | Watt — instantaneous power (V × A in DC; more complex in AC). 1 kW = 1,000 W; 1 MW = 1,000 kW. |
| **Wh / kWh / MWh** | Watt-hour — energy: power × time. 1 kW running for 1 hour = 1 kWh. The unit you pay for on an electricity bill. |
| **kVA** | Apparent power — what the cabling and transformer must physically carry, even if some of it is "reactive" and doing no useful work. Always ≥ kW. |
| **kVAr** | Reactive power — the part of AC power that oscillates between source and load without doing useful work, but is needed to energise motors, transformers, etc. Pronounced "kay-var". |
| **PF (Power Factor)** | Ratio of real power (kW) to apparent power (kVA), between 0 and 1. PF = 1.0 means all power is doing useful work; PF = 0.85 is a common minimum the grid expects. Low PF means more current for the same useful work — utilities sometimes penalise it. |
| **THD (Total Harmonic Distortion)** | A measure of how "clean" the AC waveform is. Inverters and non-linear loads inject distortion; high THD damages equipment. Acuvim L measures THD up to the 63rd harmonic. |
| **Three-phase** | AC delivered as three sinusoidal voltages 120° apart. Industrial sites are almost always three-phase. Phases are usually labelled L1/L2/L3 or A/B/C or R/Y/B (red/yellow/blue). |
| **Single-phase** | Just one of the three phases — typical for domestic loads. |
| **Grounding / Earthing** | Connecting metal enclosures to earth so a fault current has a safe path. Critical for safety; affects PCS configuration. |
| **GFDI** | Ground Fault Detector / Interrupter — protection that trips on earth leakage current. Often appears as an alarm code. |
| **Anti-islanding** | A safety function: if the grid goes down, the inverter must stop exporting power so utility workers aren't electrocuted by an "island" of energised wires. Required by every grid code. |

---

## 2. Solar PV terminology

| Term | Meaning |
|------|---------|
| **PV (Photovoltaic)** | Solar panels — semiconductor devices that convert sunlight directly to DC electricity. |
| **Module / Panel** | A single PV unit, typically 350-550 W today. |
| **String** | A series-connected line of modules feeding one input on an inverter. Higher voltage at lower current; reduces wiring losses. |
| **Array** | The whole collection of strings and modules at a site. |
| **Inverter** | Converts DC (from PV or battery) to AC (for the grid). On its own this is a "PV inverter" or "string inverter". |
| **Hybrid inverter** | An inverter that handles PV, battery, and grid inputs/outputs — common in smaller systems. |
| **MPPT** | Maximum Power Point Tracking — a control algorithm in the inverter that adjusts voltage to extract the most power from PV strings as conditions change. Bigger inverters have multiple MPPT inputs. |
| **String inverter** | One inverter per array of strings (the Huawei SUN2000 family). |
| **Central inverter** | One large inverter for the entire array (less common at C&I scale). |
| **Microinverter** | One small inverter per panel (rare at C&I scale). |
| **C&I** | Commercial & Industrial — the market segment Johan operates in (vs. residential or utility-scale). |
| **Yield / Generation** | Energy produced by the PV array, in kWh. "Yield today" is a standard register on the SmartLogger. |
| **Irradiance** | Solar power hitting a surface, in W/m². Needed to interpret yield (was generation low because of clouds, or a fault?). |
| **Self-consumption** | Using PV power directly on-site rather than exporting it. Highest value mode in SA where feed-in tariffs are weak. |
| **Curtailment** | Deliberately reducing PV output below what the panels could produce — usually because the grid is full or the battery is full. |

---

## 3. Battery storage terminology

| Term | Meaning |
|------|---------|
| **BESS** | Battery Energy Storage System — the whole battery installation: cells + BMS + PCS + enclosure. |
| **PCS (Power Conversion System)** | The bidirectional inverter that sits between the battery (DC) and the grid (AC). Charges the battery in one direction, discharges it in the other. Sinexcel PWS1-500K and EPC CAB1000 are PCS units. |
| **BMS (Battery Management System)** | Embedded electronics inside the battery cabinet that monitors cell voltages and temperatures, balances cells, and protects against over/under voltage and current. The PCS talks to the BMS to know what's safe. |
| **Cell** | The smallest battery unit (e.g. one LFP pouch). |
| **Module** | A pack of cells, electrically series + parallel, with a small BMS slave. |
| **Pack / Rack / Cabinet** | A collection of modules forming a deployable unit. |
| **String (battery)** | Modules connected in series to reach the PCS DC operating voltage. |
| **SOC (State of Charge)** | How full the battery is, 0–100 %. Reported by the BMS, exposed by the PCS over Modbus. |
| **SOH (State of Health)** | The battery's remaining capacity vs. when new, 0–100 %. Drops slowly over years. |
| **SOE (State of Energy)** | Energy currently stored, in kWh. Like SOC but absolute rather than percentage. |
| **DOD (Depth of Discharge)** | How deeply you cycled the battery. 100 % DOD = fully drained; lifetime is longer if you stay above 20 % SOC. |
| **C-rate** | A measure of charge/discharge speed relative to capacity. 1 C means full discharge in 1 hour; 0.5 C in 2 hours. Higher C-rate stresses the battery more. |
| **Cycle** | One full charge + discharge. Battery warranties are quoted in cycles (e.g. 6,000 cycles to 80 % SOH). |
| **LFP (Lithium Iron Phosphate)** | The chemistry used in CATL, Poweroad, and most C&I batteries today. Safer and longer-lived than NMC, slightly less energy-dense. |
| **NMC** | Nickel-Manganese-Cobalt — older lithium chemistry, higher energy density, less safe for stationary storage. |
| **Charge / Discharge power** | The rate at which the PCS is moving energy. By convention in our system: **positive = discharge, negative = charge** (Sinexcel and most PCS conventions). |
| **Round-trip efficiency** | Energy out ÷ energy in for one full cycle. Typical 85-92 % including PCS losses. |
| **Black start** | Starting a generator or BESS from a totally dead grid (no external reference frequency). Requires the inverter to "form" the grid voltage itself — not all inverters can. |
| **Grid-forming inverter** | An inverter that creates its own voltage and frequency reference (so it can run an island). |
| **Grid-following inverter** | An inverter that follows an existing grid voltage/frequency — the more common type. Cannot run an island on its own. |

---

## 4. Grid & utility — including South Africa

| Term | Meaning |
|------|---------|
| **Grid** | The interconnected electricity network. In SA the "national grid" is mostly Eskom; municipalities run distribution networks under their footprint. |
| **Eskom** | South Africa's state-owned electricity utility — generation + transmission + some distribution. |
| **NERSA** | National Energy Regulator of South Africa — regulates electricity, piped gas, and petroleum. Issues generation licences and approves tariffs. Any generation registration is logged with NERSA. |
| **Municipality (as utility)** | Many SA cities (Tshwane, Joburg, eThekwini, Cape Town) buy bulk from Eskom and resell to end-customers. The municipality may set its own tariffs. |
| **IPP (Independent Power Producer)** | A privately-owned generation business that sells power to the grid or directly to customers. Johan's clients may register as small-scale IPPs in some configurations. |
| **PPA (Power Purchase Agreement)** | Long-term contract between an IPP and an off-taker for energy delivery at agreed prices. |
| **Wheeling** | Using the utility's network to transport power from one private location to another (e.g. PV farm in one province, customer in another). Becoming legal in SA. |
| **Load shedding** | Eskom-mandated rolling blackouts when generation can't meet demand. "Stage 4" means about 4,000 MW must be cut. Sites with BESS can ride through stages. |
| **Grid connection agreement** | Contract with the utility specifying maximum import and export at the connection point. Often includes a maximum demand limit. |
| **PCC (Point of Common Coupling)** | The single physical point where a customer's installation connects to the utility grid — typically the main meter or main breaker. Export limits and revenue meters live here. |
| **Curtailment (grid-imposed)** | The utility instructing a generator to reduce output, usually for grid stability or full-network conditions. |
| **Frequency response** | Adjusting active power up or down in response to grid frequency drift. Some BESS earn revenue providing this. Out of v1 scope. |
| **VPP (Virtual Power Plant)** | Coordinating many small distributed assets (BESS, PV, demand) to behave like one large dispatchable plant. Out of v1 scope. |
| **DER (Distributed Energy Resource)** | Any small-scale generation or storage at the distribution level — solar, BESS, generators. The whole device fleet under our platform is "DER". |
| **Net metering** | Tariff arrangement where exported energy offsets imported energy at a 1:1 ratio. Rare in SA; most municipalities pay a lower rate for export. |
| **Feed-in tariff** | Price the utility pays for exported energy. Usually well below the import price. |
| **Time of Use (TOU)** | Tariff that varies by time of day (peak / standard / off-peak), and often by season. Eskom's Megaflex is a textbook TOU tariff. |
| **Demand charge** | A fee based on the highest 15-minute (or 30-minute) average power drawn during a billing period. Punishes spiky loads even if total kWh is small. Acuvim L calculates this natively. |
| **Maximum demand** | The peak 15-minute kW reading in a period — the value the demand charge is based on. |
| **PPC (Power Plant Controller)** | Site-level master controller that sits between the utility and all on-site inverters / BESS / generators. Enforces the grid connection terms, applies setpoints across the fleet, may handle reactive power and frequency response. **The PPC make/model on Johan's sites is currently unknown — see [QUESTIONS_FOR_JOHAN.md](requirements/QUESTIONS_FOR_JOHAN.md) A1.** |

---

## 5. Metering, billing & tariffs

| Term | Meaning |
|------|---------|
| **Energy meter** | A device that measures cumulative kWh and instantaneous power. May be revenue-grade or not. |
| **Revenue-grade** | Certified accurate enough to bill against (legally defensible). Defined by accuracy class. |
| **Accuracy class** | Standard for meter precision. **Class 0.2** = ±0.2 % error (top tier, used for utility metering). **Class 0.5** = ±0.5 % (acceptable for revenue billing). The Acuvim L is Class 0.2/0.5 depending on model variant. |
| **MID (Measuring Instruments Directive)** | EU certification that the meter is fit for billing. Often quoted on datasheets even for non-EU markets as a quality signal. |
| **Bidirectional meter** | Measures both import (grid → load) and export (load → grid) separately. All Acuvim L installs in our context are bidirectional. |
| **Import / Export** | Energy direction relative to the customer site. **Import** = grid feeding the site. **Export** = site pushing back to the grid. |
| **Active energy (kWh)** | Real energy consumed or generated. The thing that costs money. |
| **Reactive energy (kVArh)** | Energy associated with reactive power — usually only relevant for industrial customers with PF penalties. |
| **TOU period / band** | A named time window with its own rate (e.g. "peak", "standard", "off-peak"). Eskom Megaflex has 3 bands; some tariffs have only 2; some have 4. |
| **Tariff schedule** | The mapping from time of day → TOU period. Differs by weekday/weekend and season. |
| **Tariff structure** | The overall billing model: flat / TOU / TOU-with-demand / etc. |
| **Billing period** | The window covered by one invoice — typically a calendar month in SA. |
| **15-minute interval data** | Revenue-grade energy data is reported in 15-minute buckets (the global standard for utility billing). Our `EnergyInterval` table stores exactly these. |
| **VAT (Value Added Tax)** | 15 % in SA, applied to invoice totals. Whether VAT is line-item or total-only is a design decision — see B4. |
| **Arrears** | Unpaid amounts past due date. |

---

## 6. Communication protocols

| Term | Meaning |
|------|---------|
| **Modbus** | The industrial standard protocol for talking to PCS, meters, controllers. Simple master/slave model: master asks for register N, slave returns the value. Originated in 1979 and refuses to die. See [§7](#7-modbus-deep-dive) for detail. |
| **Modbus RTU** | Modbus over a serial line (RS485 or RS232). Compact binary framing. Widely deployed but needs a physical bus. |
| **Modbus ASCII** | Same protocol, ASCII-encoded framing. Rarely used. |
| **Modbus TCP** | Modbus over an Ethernet network using TCP port 502. Same register concepts, just transported over IP. Our preferred protocol whenever the device supports it. |
| **MQTT** | A lightweight publish-subscribe messaging protocol designed for unreliable networks. Devices publish to "topics" on a "broker"; subscribers receive matching messages. Acuvim L AXM-WEB2 supports MQTT push natively. |
| **MQTT Broker** | The server that all MQTT clients connect to. EMQX and Mosquitto are common open-source brokers. |
| **MQTT Topic** | A hierarchical string identifying a message stream — e.g. `solar/site42/telemetry/smartlogger`. Subscribers can wildcard (`solar/+/telemetry/#`). |
| **QoS (Quality of Service)** | MQTT delivery guarantee: 0 = at-most-once, 1 = at-least-once, 2 = exactly-once. We use QoS 1 — every message arrives, possibly with duplicates we deduplicate. |
| **LWT (Last Will and Testament)** | A message the broker publishes on a client's behalf if it disconnects unexpectedly. Used for "device went offline" notifications. |
| **TLS** | Transport Layer Security — encryption + authentication for connections. MQTT over TLS uses port 8883 (vs. 1883 unencrypted). |
| **SunSpec** | An open standard built on Modbus that defines a common register layout for inverters and BESS. If a device is "SunSpec-compliant" you can read it without a vendor-specific register map. EPC CAB1000 uses a SunSpec extension; Sinexcel partially implements it. |
| **MESA** | An extension of SunSpec specifically for energy storage. Defines battery / BMS / PCS register groups. |
| **IEC 61850** | A serious utility-grade protocol for substation automation. Acuvim L supports it via the AXM-WEB2-FOLC variant. Not in v1 scope. |
| **DNP3** | Another utility-grade protocol common in North America. Out of v1 scope. |
| **BACnet** | Building automation protocol (HVAC, lighting). Not in v1 scope despite Acuvim L supporting it. |
| **HTTP / HTTPS** | Web protocols; HTTPS is HTTP + TLS. The application API uses HTTPS exclusively. |
| **REST** | An API style: HTTP verbs (GET, POST, etc.) acting on resources at URLs. Our cloud → application API is REST. |
| **WebSocket** | A persistent two-way connection between browser and server, used for live dashboard updates. |
| **FTP / FTPS / SFTP** | File transfer protocols. AXM-WEB2 can push to FTP; we don't plan to use this path. |

---

## 7. Modbus deep dive

(For when you need to read a register map and not get lost.)

| Term | Meaning |
|------|---------|
| **Register** | A 16-bit integer storage slot inside a device, identified by an address. Most modern values are spread across 2 registers (32-bit float or int) or 4 registers (64-bit). |
| **Holding register** | A 16-bit register that can be read or written by the master. Function code 03 reads, FC06 writes single, FC16 writes multiple. |
| **Input register** | Read-only 16-bit register. Function code 04 reads. |
| **Coil** | A 1-bit on/off output that can be read or written. FC01 reads, FC05 writes single. |
| **Discrete input** | A 1-bit read-only input. FC02 reads. |
| **Function Code (FC)** | The operation code in a Modbus request: FC03 = read holding registers, FC04 = read input registers, FC06 = write single holding register, FC16 = write multiple holding registers. We mostly use FC03 + FC16. |
| **Unit ID / Slave ID / Station ID** | An 8-bit identifier for the device on a Modbus bus (1–247 typically). Modbus TCP keeps this for compatibility but it's mostly redundant — usually 1, sometimes 0 or 10 (DSE8610 defaults to 10). |
| **Address offset** | Some devices number registers from 0, some from 1, some have a vendor-specific base offset. **EPC CAB1000 adds +20,000 to every register address** — a known gotcha. Always verify the offset with a known register before trusting a map. |
| **Scaling factor** | Many registers store a value × 10ⁿ to keep precision in a 16-bit integer. E.g. Sinexcel's active power setpoint at register 53622 is in 10 W units — write 50,000 to mean 500 kW. Always check the scaling. |
| **Endianness** | The byte order within a multi-register value. Modbus is "network byte order" (big-endian) by spec, but many devices swap word order for 32-bit values ("middle-endian" / "word swap"). Test against a known value before going to production. |
| **FLOAT32 / Float** | A 32-bit IEEE 754 float spread across two consecutive 16-bit registers. PM5110 and Acuvim L both expose float values. |
| **Register profile / map** | The full document of "register N at this device means metric X with units Y and scaling Z". Each device has its own. |
| **Read-back verification** | After writing a register, read it back to confirm the value took. Critical for control commands — just because the write succeeded doesn't mean the device accepted it. |
| **Polling** | Periodically reading registers from a device. The edge agent polls each device on a schedule (10 s for power, 30 s for SOC, 60 s for energy counters). |
| **Push** | Device sends data on its own initiative (no polling). The Acuvim L AXM-WEB2 supports MQTT push. |

---

## 8. Networking & IT infrastructure

| Term | Meaning |
|------|---------|
| **LAN (Local Area Network)** | The Ethernet network inside one site — typically 192.168.x.x. All on-site devices live on the LAN. |
| **VLAN** | Virtual LAN — software-isolated segment of a physical network. Used to separate the device LAN from the office LAN at larger sites. |
| **VPN** | Virtual Private Network — encrypted tunnel between two networks, used to extend the office LAN to the cloud or to provide secure remote support. |
| **DHCP** | Dynamic Host Configuration Protocol — automatic IP address assignment. We avoid this for devices: meters and gateways need **fixed/static IPs** so the edge agent always knows where to find them. |
| **Static IP** | Manually assigned, never changes. Standard for industrial devices. |
| **NAT** | Network Address Translation — converts private IPs (192.168.x.x) to public ones at the router. The edge agent connects outbound; nothing connects inbound to the site. |
| **Firewall** | Filters traffic between networks. The site firewall typically only allows outbound from the device LAN. |
| **Cellular failover / 4G / LTE** | Backup internet over the mobile network when fibre is down. Common at SA sites. |
| **TCP** | Connection-oriented transport — guaranteed delivery, ordered. Modbus TCP and HTTPS use TCP. |
| **UDP** | Connectionless transport — fire and forget. Not used in our stack. |
| **Port** | A 16-bit number identifying a network service on a host. Modbus TCP = 502, HTTPS = 443, MQTT = 1883/8883, SSH = 22. |
| **MAC address** | Hardware identifier of a network card; only matters within one LAN segment. |
| **DNS** | Domain Name System — converts hostnames to IPs. |
| **REST API** | The cloud HTTPS API the dashboards talk to. |
| **JWT (JSON Web Token)** | A signed token used for API authentication. The dashboard logs in once, gets a JWT, sends it on every API call. |
| **PostgreSQL** | The relational database we use for both relational data and time-series (via TimescaleDB extension). |
| **TimescaleDB** | A PostgreSQL extension that adds time-series superpowers — automatic partitioning, compression, and continuous aggregates. We use it for `Reading` and `EnergyInterval`. |
| **Hypertable** | TimescaleDB's name for a table that's automatically partitioned by time. Looks like a normal table to queries. |
| **Continuous aggregate** | A TimescaleDB feature that maintains pre-computed rollups (1-min, 15-min, 1-hour averages) automatically. Makes dashboard queries fast. |
| **Materialised view** | A SQL view whose result is physically stored and refreshed on a schedule. We use one for `ClientUsageSummary`. |
| **Schema (database)** | A namespace inside a PostgreSQL database. We use two: `timeseries` and `app`. |
| **S3 / Blob storage** | Object storage for files (invoice PDFs, audit dumps). AWS S3 or any S3-compatible service. |
| **Container / Docker** | A packaged runtime that includes the app + its dependencies. We deploy the edge agent as a Docker container so it's isolated from whatever else is on the site PC. |

---

## 9. Equipment vendors & products

> Listed in the order they appear in our integration surface. The status column reflects the discovery work to date.

| Product | Vendor | What it is | Status |
|---------|--------|-----------|--------|
| **SmartLogger V300R024C00SPC200** | Huawei | Aggregation gateway that collects data from all Huawei inverters, Luna PCS, and LUNA2000B batteries on a site. We integrate with the SmartLogger and never directly with the sub-devices. | Full register map ingested |
| **SUN2000** | Huawei | Family of three-phase string PV inverters. Behind the SmartLogger. | Via SmartLogger |
| **Luna PCS** | Huawei | Battery PCS for the Huawei BESS. Behind the SmartLogger. | Via SmartLogger |
| **LUNA2000B** | Huawei | Lithium battery pack. Behind the Luna PCS, behind the SmartLogger. | Via SmartLogger |
| **Acuvim L** | AccuEnergy | Revenue-grade three-phase power and energy meter. Class 0.2/0.5 accuracy. Has a built-in TOU tariff engine. **The exclusive billing data source in our system.** | Full spec documented |
| **AXM-WEB2** | AccuEnergy | Communication module that plugs into the Acuvim L. Adds Ethernet, MQTT/HTTP/FTP push, BACnet, IEC 61850, 3 GB local data cache. The "smart" half of the meter. | Full spec documented |
| **PWS1-500K** | Sinexcel | 500 kW bidirectional PCS for utility-scale BESS. Talks Modbus RTU (RS485) or Modbus TCP. SunSpec-partial. Has CAN pass-through to the BMS so we can read SOC without integrating the BMS directly. | Partial spec; module register confirmation outstanding |
| **CAB1000** | EPC Power | Bidirectional PCS in a self-contained outdoor cabinet (PCS + battery cabinets). Modbus TCP via a Lantronix gateway. **Public register map not available — register addresses outstanding.** | Partial spec; register addresses outstanding |
| **PM5110** | Schneider Electric | Three-phase energy meter, RS485 only (no native Ethernet). Used as a secondary meter behind the Acuvim L. Not used for billing in our system. | Full spec documented |
| **PM3255 / PM5000 (variants)** | Schneider Electric | Cousins of the PM5110 with similar register layouts. May or may not be deployed — pending Johan. | Not researched |
| **DSE8610 MK2** | Deep Sea Electronics | Diesel generator controller. Native Modbus TCP (no add-on needed). Default unit ID 10. Uses Deep Sea's "GenComm" register conventions (page × 256 + offset addressing). | Full spec documented |
| **MBB** | Sungrow | Sungrow's BESS unit deployed at SLD2-type sites. Model details not yet confirmed. | Not researched |
| **NPort** | MOXA | Family of RS485-to-Ethernet gateways. Transparent — they make a serial device look like a TCP endpoint. Not a data source itself, just a wire converter. **Specific NPort model numbers TBD with Johan.** | Configuration only |
| **Lantronix gateway** | Lantronix | A serial-to-Ethernet gateway used in front of the EPC CAB1000. Model TBD. | Configuration only |
| **PPC** | TBD | The Power Plant Controller — a site-level master controller. Make and model unknown. **Top-priority unknown for the project.** | Unknown |
| **Poweroad / CATL** | Poweroad / CATL | Battery cells and packs (LFP). Inside the Sinexcel-fronted BESS at some sites. We do not integrate directly — SOC and SOH come via Sinexcel's CAN pass-through. | Not directly integrated |
| **Teltonika** | Teltonika | Industrial routers with cellular + LAN + Linux compute. Sometimes used as the edge agent host platform. | Possible host hardware |

### Disambiguation: "EPC"
- **EPC Power** is a US-based PCS manufacturer (the CAB1000 vendor).
- **EPC contractor** stands for **Engineering, Procurement, Construction** — the firm that builds a site end-to-end. *Different thing.* Always check context.

### Disambiguation: "EMS"
- In our domain, **EMS = Energy Management System** — the software that schedules and dispatches generation/storage on a site. Sinexcel's "Remote" mode is EMS-controlled.
- Avoid confusion with **EMS = Environmental Management System** (a corporate sustainability framework — different field entirely).

---

## 10. Site infrastructure

| Term | Meaning |
|------|---------|
| **SLD (Single Line Diagram)** | A simplified electrical schematic showing how everything connects — inverters, batteries, transformers, breakers, the grid. The SLD1 / SLD2 PNG files in `discovery/documents/` are this. |
| **PCC (Point of Common Coupling)** | The single physical point where the customer connects to the utility. The revenue meter sits here. |
| **Switchgear** | High-voltage switching equipment — breakers, contactors, isolators. |
| **Breaker / Circuit breaker** | An automatic switch that trips on overcurrent or fault. Manually resettable. |
| **Transformer** | Steps voltage up or down. Most C&I sites have one stepping the utility's MV (medium voltage, ~11 kV) down to LV (~400 V). |
| **MV / LV** | Medium Voltage (1-35 kV typically) and Low Voltage (<1 kV). |
| **Combiner box** | Where multiple PV strings are combined onto one cable run to the inverter. |
| **Earthing / Grounding kit** | Equipment for safe earth bonding. |
| **Switchboard / Distribution board (DB)** | Where breakers and busbars are mounted. |
| **Busbar** | A solid metal conductor that distributes current to multiple breakers. |
| **CT (Current Transformer)** | A donut-shaped sensor that measures current without making electrical contact with the wire. Meters use CTs to read big currents safely. |
| **VT / PT (Voltage / Potential Transformer)** | A small transformer that scales high voltages down for safe measurement. |
| **HMI (Human-Machine Interface)** | A touchscreen or display on a piece of equipment for local configuration. The Sinexcel PWS1 has one; you set the IP address there. |
| **NOC (Network Operations Centre)** | The team that monitors operational alerts 24/7 (or business hours). |
| **Genset** | Slang for a diesel generator set. Driven by the DSE8610 controller in our stack. |
| **STS (Static Transfer Switch)** | An automatic switch that transfers a load between two AC sources very fast (sub-cycle). Sinexcel offers this as an option for off-grid capability. |

---

## 11. Software architecture (our stack)

Terms used inside the [ARCHITECTURE.md](architecture/ARCHITECTURE.md) and [DATA_MODEL.md](architecture/data-model/DATA_MODEL.md).

| Term | Meaning |
|------|---------|
| **Three-layer architecture** | Edge → Cloud → Application. Each layer has its own responsibilities and failure modes. |
| **Edge layer** | Software running at the site itself — collects local data, buffers it, executes commands. |
| **Cloud layer** | Centralised servers that ingest data, store it, generate invoices, serve the API. |
| **Application layer** | The dashboards humans interact with — Operations and Client portals. |
| **REST + WebSocket API** | Cloud talks to apps via REST (request/response) and WebSocket (live push). |
| **Microservice** | An independently-deployable service. Our cloud may decompose into several (ingestion worker, billing engine, alert engine, API server). |
| **Idempotent** | An operation you can safely repeat — "set power to 200 kW" is idempotent, "increase by 10 kW" is not. Control commands are designed idempotently. |
| **At-least-once delivery** | Guarantee that every message arrives, possibly with duplicates. We deduplicate by message ID. |
| **Eventual consistency** | The dashboard may briefly disagree with the device (e.g. command succeeded but UI hasn't refreshed yet). Acceptable for monitoring; not for billing. |
| **Multi-tenant** | One platform serving many independent customers (Johan's clients) with strict data isolation. |
| **Tiered access** | Different user types (Operations vs. Client) see different parts of the same data through different APIs. |
| **Audit trail / immutable log** | A record of every significant action that is never modified or deleted. Used for control commands and billing adjustments. |
| **Soft delete** | Marking a record inactive without physically removing it. We use this for sites and devices so we keep historical billing accuracy. |
| **Append-only** | Records can be inserted but never updated or deleted. `EnergyInterval`, `AuditLog`, `EnergyAdjustment` are append-only. |

---

## 12. Project-specific jargon

These terms are ours — invented for this project. If they show up in conversation, this is what they mean.

| Term | Meaning |
|------|---------|
| **Edge Agent** | The lightweight daemon we will run at each site. Polls Modbus TCP devices, subscribes to local MQTT, buffers locally, forwards to cloud, executes control commands. **One per site.** Configuration comes from the cloud; the agent has no local UI. |
| **Aggregation Hub Principle** | Our integration rule: "Do not integrate sub-devices directly when a hub exists." We talk to the SmartLogger, not to each Huawei inverter. We talk to the Sinexcel PCS, not to the BMS behind it. This collapses our integration surface from ~14 device types to 7 endpoints per site. |
| **Integration surface** | The complete set of devices/protocols our edge agent talks to. Smaller is better. |
| **Store-and-forward** | The edge agent's resilience pattern: write every reading to a local buffer first, then forward to cloud when connectivity allows. Default buffer depth is 72 hours. |
| **Read-back verification** | After writing a control register, wait 500 ms, read it back, and confirm it took. If it didn't, raise an alert. Applied to every command. |
| **Control Relay** | The cloud component that queues control commands, dispatches them to the edge via MQTT, tracks acknowledgements, and surfaces the result back to the operator. |
| **Operations tier / Operations user** | Johan's team. Full access — raw telemetry, control, billing admin, device registry, alert configuration. |
| **Client tier / Client user** | Johan's customers. Aggregated read-only view scoped to their own contract. **No raw `Reading` access. No control. No device-level data.** |
| **Reading** | A single data point — one device, one metric, one timestamp, one value. Lives in the `Reading` hypertable. |
| **EnergyInterval** | A 15-minute energy bucket from the Acuvim L (the billing-grade source). Immutable once written. Lives in its own hypertable. **The only billing data lineage in the system.** |
| **EnergyAdjustment** | An immutable correction record applied on top of an EnergyInterval — never overwrites the original. Required for every billing correction (meter swap, missed interval, etc.). |
| **DeviceSnapshot** | The latest state per device, kept in a relational table for fast "current status" lookups without querying time-series. Updated on every successful poll. |
| **ControlCommand** | A row in the audit table for every command we ever send to a device. Tracks status: pending → sent → acknowledged → confirmed (or failed). |
| **BillingMeter** | The device designated as the revenue source for a site. Deliberately a separate entity from `Device` so the billing data lineage is explicit. |
| **ClientUsageSummary** | A pre-aggregated materialised view that the client portal reads. Clients never join to `Reading`. |
| **Tariff band** | One slot in a TOU tariff (peak / standard / off-peak / flat). Stored on `InvoiceLine`. |
| **Heartbeat** | A 60-second "I'm alive" message the edge agent publishes. Missing heartbeats trigger a "site offline" alert. |
| **Push interval** | How often the Acuvim L pushes a billing record to MQTT (typically 1-15 minutes, configurable). Independent of edge agent poll rates. |
| **Poll interval** | How often the edge agent reads a device's registers. Per-metric: power = 10 s, SOC = 30 s, energy counters = 60 s. |
| **Refresh rate** | How often the dashboard updates from the cloud. Default 5 minutes, minimum 30 seconds. **Decoupled from poll interval — the cloud has all the data, the dashboard just chooses how often to display it.** |
| **Site slug** | A URL-safe identifier for a site (e.g. `pretoria-north`) used in MQTT topics and API URLs. |
| **Pass-through (CAN pass-through)** | A pattern where one device exposes data from another it talks to internally. The Sinexcel PCS exposes BMS data via its own register map even though we never talk to the BMS directly. |
| **Two-tier API** | Our API surface design: Operations endpoints serve raw + aggregated data; Client endpoints serve aggregated only. Same code base, different authorisation. |
| **Closed question / pending question** | Tracking convention in our requirements docs. **Closed** = decided, do not relitigate. **Pending** = needs Johan input. |
| **v1 / v2 scope** | What ships in the first release vs. later. Anything labelled "out of scope for v1" in [ARCHITECTURE.md](architecture/ARCHITECTURE.md) is deliberately deferred — flag if a discussion implies bringing it in. |

---

## See also

- [OVERVIEW.md](OVERVIEW.md) — project purpose and scope
- [CLAUDE.md](CLAUDE.md) — full architectural decisions and device technical facts
- [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) — system architecture
- [architecture/data-model/DATA_MODEL.md](architecture/data-model/DATA_MODEL.md) — data model
- [discovery/specs/](discovery/specs/) — per-device protocol details
- [requirements/QUESTIONS_FOR_JOHAN.md](requirements/QUESTIONS_FOR_JOHAN.md) — open questions
