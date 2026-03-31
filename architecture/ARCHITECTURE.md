# Solar Monitor — System Architecture

**Version:** 0.1 (draft — pre-PRD)  
**Author:** Marius Bloemhof  
**Date:** 2026-03-31  
**Status:** Working draft. Open questions flagged with ❓ — to be closed with Johan before v1.0.

---

## 1. Guiding Principles

1. **Aggregation hubs first.** Most devices report through a hub (SmartLogger, Acuvim L AXM-WEB2). The edge agent integrates with the hub, not individual sub-devices. This keeps the integration surface small and maintainable.
2. **Edge autonomy.** Sites may run on cellular or unreliable links. The edge agent operates independently and buffers locally; the cloud is the consumer, not the controller.
3. **Push where available, poll everywhere else.** The Acuvim L AXM-WEB2 supports MQTT push — no polling needed. All other devices are polled by the edge agent via Modbus TCP.
4. **Revenue-grade data is sacred.** Billing data flows from the Acuvim L only. It is never synthesised, estimated, or derived from non-revenue-grade sources.
5. **Control is audited and idempotent.** Every command sent to a device is logged with who sent it, when, and what the device confirmed. Commands that fail are retried with exponential back-off; ambiguous states are escalated to alert.
6. **Multi-site from day one.** The data model, APIs, and edge agent design are multi-tenant from the start. Single-site is a degenerate case of the multi-site model.

---

## 2. System Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                        │
│   Web dashboard  ·  Billing module  ·  Control console         │
│   Client portal (❓ future)  ·  Alerting / notifications        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST / WebSocket API
┌───────────────────────────▼─────────────────────────────────────┐
│                          CLOUD LAYER                            │
│   API server  ·  MQTT broker  ·  Ingestion workers             │
│   Time-series store  ·  Relational store  ·  Blob store        │
│   Billing engine  ·  Alert engine  ·  Background jobs          │
└────────────┬────────────────────────────────┬───────────────────┘
             │ MQTT (push from Acuvim L)       │ MQTT / REST
             │                                 │ (edge → cloud)
┌────────────▼─────────────────────────────────▼───────────────────┐
│                          EDGE LAYER                              │
│                   (one instance per site)                        │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  Edge Agent                                              │  │
│   │  · Modbus TCP poller  · MQTT subscriber (Acuvim)        │  │
│   │  · Store-and-forward buffer  · Control command relay    │  │
│   └──────────────┬───────────────────────────────────────────┘  │
│                  │  Site LAN (192.168.x.x)                       │
│   ┌──────────────▼───────────────────────────────────────────┐  │
│   │  Device Endpoints (Modbus TCP)                           │  │
│   │  · SmartLogger :502   · Sinexcel PWS1 :502              │  │
│   │  · EPC CAB1000 :502   · PM5110 via MOXA :502            │  │
│   │  · DSE8610 :502       · PPC ❓                          │  │
│   └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Edge Layer

### 3.1 Edge Agent

A lightweight polling daemon deployed as a single binary (or Docker container) on an industrial PC or Raspberry Pi at each site. It has no user interface; all configuration is delivered from the cloud.

**Responsibilities:**
- Poll each Modbus TCP endpoint on a configurable schedule
- Subscribe to the Acuvim L AXM-WEB2 MQTT broker (local or cloud) for push readings
- Write all received readings to a local time-series buffer
- Flush buffered readings to the cloud (MQTT or REST) when connectivity is available
- Execute control commands received from the cloud; confirm result; report outcome
- Emit heartbeat to cloud every 60 seconds; raise site-offline alert if missed

**Configuration model:**
- Agent config lives in the cloud (device registry, poll intervals, register lists)
- On startup the agent fetches its site config from the cloud API by site ID
- Config changes propagate automatically on next poll cycle

**Store-and-forward:**
- Local SQLite or flat-file ring buffer, configurable depth (default 72 hours)
- Readings older than buffer depth are dropped; this is acceptable for telemetry (not billing)
- Billing-grade data from Acuvim L is double-persisted: local buffer AND direct MQTT push to cloud (two independent paths)

### 3.2 Integration Endpoints (per site)

The edge agent connects to these endpoints on the site LAN. This is the complete integration surface — individual sub-devices within a hub are not directly addressed.

| Endpoint | Protocol | Port | Unit ID | What It Covers |
|----------|----------|------|---------|---------------|
| **Huawei SmartLogger** | Modbus TCP | 502 | 1 | All SUN2000 PV inverters, Luna PCS (Huawei BESS), LUNA2000B batteries — full Huawei sub-system in one endpoint |
| **AccuEnergy Acuvim L / AXM-WEB2** | MQTT push | 1883/8883 | — | Revenue-grade billing meter; push interval configurable (1–60 min) |
| **AccuEnergy Acuvim L / AXM-WEB2** | Modbus TCP | 502 | 1 | Fallback / on-demand polling if MQTT unavailable |
| **Sinexcel PWS1-500K** | Modbus TCP | 502 | 1 | 500kW bidirectional PCS + connected BMS (Poweroad/CATL via CAN pass-through SOC registers) |
| **EPC Power CAB1000** | Modbus TCP | 502 | 1 (❓) | Bidirectional BESS inverter + connected battery cabinets; via Lantronix serial-to-Ethernet gateway |
| **Schneider PM5110** | Modbus TCP | 502 | 1 | Secondary energy meter; RS485 device bridged via MOXA NPort |
| **Deep Sea DSE8610 MK2** | Modbus TCP | 502 | 10 | Generator controller — status, measurements, alarms, start/stop |
| **PPC** | ❓ TBD | ❓ | ❓ | Grid compliance controller; may be the site master — make/model required from Johan |

**Devices NOT directly integrated** (data flows through a hub above):
- Huawei SUN2000 inverters → SmartLogger
- Huawei Luna PCS → SmartLogger
- Huawei LUNA2000B batteries → SmartLogger
- Poweroad / CATL BMS → Sinexcel PWS1 CAN pass-through → PWS1 register map
- EPC Power battery cabinets → CAB1000 internal
- MOXA NPort → transparent RS485-to-TCP gateway; no data model entity

### 3.3 Poll Intervals and Dashboard Refresh

**Edge agent poll intervals** (how often the agent reads from devices on the LAN — independent of cloud push rate):

| Data Category | Poll Interval | Rationale |
|---------------|----------|-----------|
| Power (kW, kVAR) | 10 s | Captures fast state changes in local buffer |
| SOC / temperatures | 30 s | Slower-moving; reduces bus load |
| Energy counters (kWh) | 60 s | Sufficient for aggregation |
| Operating state / alarms | 10 s | Fast fault detection |
| Generator status | 10 s | Safety-critical |
| Configuration registers | On startup + on change | Read-once with invalidation |

**Dashboard refresh rate** (how often the cloud pushes updates to the browser — decoupled from poll rate above):

- **Default:** 5 minutes
- **Configurable per user / per view** — operators may want faster for active control sessions
- **Minimum floor:** never lower than 30 seconds — this is not a real-time SCADA system; sub-30s refresh adds complexity without meaningful value for this use case
- The edge agent always buffers at the poll rate above; the refresh rate only controls how often that buffer is flushed to the UI

Acuvim L push interval: configurable per AXM-WEB2 (default 5 min for energy). This is independent of the dashboard refresh rate — billing data arrives at its own cadence and is stored regardless of when the UI polls for it.

---

## 4. Cloud Layer

### 4.1 Component Overview

| Component | Purpose |
|-----------|---------|
| **MQTT Broker** | Receives edge agent publishes and Acuvim L direct push. Topics are site-scoped. |
| **Ingestion Workers** | Consume MQTT, validate, normalise units, write to time-series store. Stateless, horizontally scalable. |
| **Time-Series Store** | All telemetry readings. High write throughput, time-range queries, downsampling. |
| **Relational Store** | Sites, devices, customers, contracts, invoices, users, alert rules, audit log. Source of truth for all configuration. |
| **Blob Store** | Raw MQTT payloads (audit trail), generated invoice PDFs, config snapshots. |
| **API Server** | REST + WebSocket API consumed by the application layer. Handles auth, authorisation, device commands. |
| **Billing Engine** | Background job that aggregates energy intervals, applies tariff rules, generates invoice line items. Runs on schedule and on demand. |
| **Alert Engine** | Evaluates alert rules against incoming telemetry. Triggers notifications (email, SMS, webhook). |
| **Control Relay** | Queues and delivers control commands from the API to the edge agent; tracks acknowledgement and result. |

### 4.2 MQTT Topic Structure

```
solar/{site_id}/telemetry/{device_id}         ← edge agent publishes readings
solar/{site_id}/billing/{meter_id}            ← Acuvim L direct push (AXM-WEB2)
solar/{site_id}/status/{device_id}            ← operating state + alarms
solar/{site_id}/heartbeat                     ← edge agent liveness
solar/{site_id}/commands/{device_id}          ← cloud → edge (control commands)
solar/{site_id}/commands/{device_id}/ack      ← edge → cloud (command acknowledgement)
```

### 4.3 Ingestion Flow

```
Edge Agent / Acuvim L push
    → MQTT Broker
        → Ingestion Worker (validate, tag, normalise)
            → Time-Series Store (raw readings, 1-second resolution)
            → Relational Store (latest device state snapshot)
            → Alert Engine (threshold evaluation)
```

### 4.4 Technology Options

These are recommendations; final selection is a separate decision:

| Component | Recommended | Alternatives |
|-----------|-------------|--------------|
| MQTT Broker | EMQX / Mosquitto | AWS IoT Core, HiveMQ |
| Time-Series Store | TimescaleDB (PostgreSQL extension) | InfluxDB, AWS Timestream |
| Relational Store | PostgreSQL | — |
| Blob Store | S3 / S3-compatible | Azure Blob |
| API Server | FastAPI (Python) or NestJS (Node) | — |
| Edge Agent runtime | Python (pymodbus) or Go | — |
| Message format | JSON (MQTT payloads) | — |

TimescaleDB is recommended because it co-locates time-series and relational data in a single PostgreSQL instance — simplifying operations, enabling JOIN queries between telemetry and billing data, and supporting standard SQL tooling.

---

## 5. Application Layer

Two distinct user tiers with different access levels, served by the same API with role-scoped responses:

### Tier 1 — Operations (Johan's team)

Full-access interface. All four modules are available.

| Module | Key Capabilities |
|--------|-----------------|
| **Monitoring Dashboard** | Live site map, per-device status, historical charts (any interval), alarm feed |
| **Control Console** | Mode switching, power setpoints, start/stop, command history, read-back confirmation |
| **Billing Module** | Energy interval data, invoice generation, tariff config, export to accounting |
| **Admin** | Site config, device registry, user management, alert rule configuration |

### Tier 2 — Client portal (Johan's customers)

Read-only, scoped to the client's own site(s) and contract. **No control capabilities. No access to raw device telemetry or individual device registers.**

| View | What the client sees |
|------|---------------------|
| **Usage summary** | Aggregated energy consumption/production per day/month — pre-summarised, not raw readings |
| **Billing summary** | Current period usage, previous invoices, invoice PDFs |
| **Site status** | Simple "online / offline" per site — no device-level detail |

> **API design implication:** The client-facing API endpoints return pre-aggregated summaries only. Raw `Reading` records are never exposed to client users. This is both a security boundary and a UX decision — clients don't need (or want) Modbus register data.

---

## 6. Data Flows

### 6.1 Monitoring Flow

```
Device → Modbus TCP → Edge Agent → MQTT → Cloud Ingestion → Time-Series Store
                                                           → WebSocket → Dashboard
```

### 6.2 Billing Flow

```
Acuvim L → MQTT push (AXM-WEB2) → Cloud MQTT Broker → Ingestion Worker
    → EnergyInterval records (15-min buckets, Wh precision)
    → Billing Engine (applies tariff rules, aggregates to invoice period)
    → Invoice line items → PDF generation → Client delivery
```

Billing data is **never derived from polling** — only from Acuvim L push. If Acuvim L push is unavailable, the 3 GB offline cache on AXM-WEB2 stores up to 3 months of data which is replayed on reconnection.

### 6.3 Control Flow

```
Operator (browser) → API Server → Control Relay → MQTT commands topic
    → Edge Agent → Modbus FC06/FC16 write → Device
    → Device acknowledgement (read-back verification)
    → MQTT ack topic → Control Relay → API Server → Operator (result)
```

Control commands are **verified by read-back**: after writing a setpoint the edge agent reads the register back after 500 ms and confirms the value changed. Discrepancy raises an alert.

---

## 7. Connectivity and Resilience

| Scenario | Behaviour |
|----------|-----------|
| Site internet down | Edge agent buffers locally (72 h default). Dashboard shows site as "offline". No billing data loss (AXM-WEB2 has 3 GB local cache). |
| Edge agent process crash | Systemd / Docker restart policy. Resumes polling within 30 s. Buffer preserved on disk. |
| Individual device unreachable | Edge agent logs read timeout, marks device as "unreachable", continues polling other devices. Alert raised after configurable consecutive failures. |
| Cloud ingestion backlog | MQTT broker persists messages (QoS 1). Ingestion workers auto-scale or drain queue on recovery. |
| Command delivery failure | Command stays in "pending" state. Edge agent retries with back-off. Command expires after configurable TTL (default 5 min); operator notified. |

---

## 8. Security Considerations

| Concern | Approach |
|---------|---------|
| Edge-to-cloud transport | MQTT over TLS (port 8883); mutual TLS certificates per site |
| Edge agent credentials | Per-site credentials stored in environment variables; rotatable via cloud config push |
| Site LAN | Edge agent on isolated IoT VLAN; no inbound connections from internet to site |
| Modbus TCP | No auth at protocol level (limitation of Modbus). Mitigated by LAN isolation and firewall rules |
| API authentication | JWT bearer tokens; role-based access control |
| Billing data integrity | Acuvim L readings are immutable once written; correction via adjustment entries, never overwrite |
| Audit log | All control commands, billing adjustments, and config changes are append-only audit log entries |

---

## 9. Open Questions

### Closed

| # | Question | Answer |
|---|----------|--------|
| 1 | How many sites? | 1-N — multi-site from day one; no fixed upper bound |
| 5 | Do clients get their own portal? | Yes — two tiers: Operations (full access) and Client (aggregated read-only; see section 5) |
| 6 | Acceptable dashboard data latency? | 5 min default; configurable; minimum floor ~30 s (never 1 s) |

### Pending (for Johan)

| # | Question | Why It Matters |
|---|----------|---------------|
| 2 | What is the PPC make/model? | May collapse entire control architecture to single endpoint — highest priority unknown |
| 3 | What exactly gets billed? (kWh imported from grid, kWh from battery, both?) | Defines which Acuvim L energy registers feed the billing engine |
| 4 | What is the billing period and tariff structure? (flat rate, TOU, demand charge?) | Defines billing engine complexity and Acuvim L TOU configuration |
| 7 | Are there regulatory reporting obligations? (NERSA, grid compliance data, data retention?) | May require additional retention periods and report formats |
| 8 | MOXA NPort model numbers deployed? | Needed for RS485 gateway configuration guide |
| 9 | Is Sungrow MBB deployed at any sites? | Determines whether Sungrow integration is in v1 scope |

---

## 10. Out of Scope (for v1)

- Direct BMS integration (Poweroad / CATL) — data available via PCS register pass-through
- Individual Huawei inverter telemetry — available aggregated via SmartLogger
- IEC 61850, BACnet, DNP3 protocols — Acuvim L supports these but no identified use case
- Predictive analytics, ML forecasting
- Grid services / VPP dispatch (may be v2 if PPC integration is confirmed)
