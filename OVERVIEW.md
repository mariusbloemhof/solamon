# Solar Monitor — Project Overview

**Client:** Johan Wolmarans  
**Consultant:** Marius Bloemhof  
**Phase:** Discovery & Architecture  
**Last updated:** 2026-03-31

---

## Purpose

Johan Wolmarans operates a solar energy business that installs and owns grid-tied solar PV and battery energy storage systems (BESS) at commercial and industrial client sites across South Africa. His business model is equipment rental plus energy services — he owns the hardware, clients pay for the energy and services delivered.

The Solar Monitor platform is the software layer that makes this business scalable. Without it, Johan's team monitors sites manually, billing requires manual meter reading, and remote control of equipment is not possible. With it, any number of sites can be monitored and billed from a single cloud platform, and equipment can be operated remotely.

---

## The Three Problems We Are Solving

| # | Problem | Solution |
|---|---------|---------|
| 1 | **No unified visibility** — each site has separate device interfaces with no consolidated view across the fleet | **Monitoring platform** — live and historical telemetry from all devices at all sites in a single dashboard |
| 2 | **Manual billing** — energy invoicing relies on manual meter reading and spreadsheets, which is error-prone and does not scale | **Automated billing** — revenue-grade energy data from AccuEnergy Acuvim L meters drives automated invoice generation |
| 3 | **No remote control** — changing operating modes or power setpoints requires a physical site visit | **Remote control** — mode switching, power setpoints, start/stop commands issued from the cloud with full audit trail |

---

## Scope

### In scope — v1

- Multi-site cloud platform (1 to N sites from day one)
- Edge agent deployed per site — polls all Modbus TCP devices on site LAN, buffers locally, forwards to cloud
- Integration with the following device types:
  - **Huawei SmartLogger** (aggregates all Huawei PV inverters, BESS, and batteries)
  - **AccuEnergy Acuvim L + AXM-WEB2** (revenue-grade billing meter — MQTT push)
  - **Sinexcel PWS1-500K** (500kW bidirectional BESS inverter / PCS)
  - **EPC Power CAB1000** (bidirectional BESS inverter / PCS)
  - **Schneider PM5110** (secondary energy meter, via MOXA RS485 gateway)
  - **Deep Sea DSE8610 MK2** (diesel generator controller)
  - **PPC** (Power Plant Controller — make/model TBD, pending Johan)
- Two user tiers: **Operations** (full access) and **Client** (aggregated read-only + billing)
- Automated invoice generation from Acuvim L energy interval data
- Configurable alerting with multi-channel notifications (email, SMS)
- Full audit trail for all control commands and billing adjustments

### Out of scope — v1

- Direct BMS integration (Poweroad, CATL) — SOC data available via PCS pass-through registers
- Individual Huawei sub-device telemetry — available aggregated via SmartLogger
- Sungrow MBB integration — pending model confirmation and site inventory from Johan
- Predictive analytics, ML forecasting, optimisation algorithms
- Grid services / VPP (Virtual Power Plant) dispatch
- IEC 61850, BACnet, DNP3 protocol support
- Mobile app (web-responsive only in v1)

---

## Architecture Summary

The system is structured in three layers. See [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) for the full specification.

```
┌─────────────────────────────────────────┐
│  APPLICATION LAYER                      │
│  Operations dashboard · Client portal   │
│  Billing module · Control console       │
└──────────────┬──────────────────────────┘
               │ REST / WebSocket API
┌──────────────▼──────────────────────────┐
│  CLOUD LAYER                            │
│  MQTT broker · Ingestion workers        │
│  Time-series DB · Relational DB         │
│  Billing engine · Alert engine          │
└──────────────┬──────────────────────────┘
               │ MQTT / REST (per site)
┌──────────────▼──────────────────────────┐
│  EDGE LAYER  (one agent per site)       │
│  Modbus TCP poller · Local buffer       │
│  Control relay · MQTT subscriber        │
│                                         │
│  Site LAN: SmartLogger · Acuvim L       │
│  Sinexcel PWS1 · EPC CAB1000           │
│  PM5110 · DSE8610 · PPC                │
└─────────────────────────────────────────┘
```

**Key design decisions:**
- Aggregation hubs reduce integration surface — SmartLogger covers all Huawei equipment; each PCS abstracts its own batteries
- Acuvim L is the exclusive billing data source — never synthesised from other devices
- Edge agent operates autonomously with local store-and-forward — site connectivity loss does not cause data or billing loss
- All control commands are verified by read-back and logged in an immutable audit trail

---

## Data Model Summary

See [architecture/data-model/DATA_MODEL.md](architecture/data-model/DATA_MODEL.md) for the full specification.

Core entities:

| Entity | Purpose |
|--------|---------|
| **Site** | A physical installation. One edge agent per site. |
| **Device** | A specific hardware unit at a site (SmartLogger, Acuvim L, etc.) |
| **Reading** | Time-series telemetry — all measurements from all devices |
| **EnergyInterval** | 15-minute billing-grade energy buckets from Acuvim L (immutable) |
| **Contract** | Commercial arrangement between Johan and a client |
| **Invoice / InvoiceLine** | Generated billing documents |
| **ControlCommand** | Every command sent to a device — audited, tracked, confirmed |
| **Alert / AlertRule** | Configurable threshold alerting |
| **User** | Operations tier (full access) or Client tier (aggregated read-only) |

Storage: TimescaleDB (PostgreSQL + time-series extension) — single database, two schemas. Raw telemetry retained 90 days; 15-minute billing aggregates retained 7 years.

---

## Device Ecosystem

The platform integrates with the following physical device categories present on Johan's sites:

| Category | Devices | Integration Path |
|----------|---------|-----------------|
| PV Generation | Huawei SUN2000 inverters | Via SmartLogger (no direct integration) |
| BESS (Huawei) | Luna PCS + LUNA2000B batteries | Via SmartLogger (no direct integration) |
| BESS (Sinexcel) | PWS1-500K 500kW PCS | Direct Modbus TCP |
| BESS (EPC Power) | CAB1000 bidirectional PCS | Direct Modbus TCP (via Lantronix gateway) |
| BESS (Sungrow) | MBB units (SLD2 sites) | TBD — pending model confirmation |
| Aggregation hub | Huawei SmartLogger V300R024 | Direct Modbus TCP — single endpoint for entire Huawei sub-system |
| Billing meter | AccuEnergy Acuvim L + AXM-WEB2 | MQTT push (primary) + Modbus TCP fallback |
| Secondary meter | Schneider PM5110 | Modbus TCP via MOXA NPort gateway |
| Generator | Deep Sea DSE8610 MK2 | Direct Modbus TCP |
| Grid compliance | PPC (make/model TBD) | TBD — pending Johan |
| RS485 gateway | MOXA NPort | Transparent bridge — not a data source |

Full device technical specifications are in [discovery/specs/](discovery/specs/).

---

## Current Phase and Next Steps

**Phase:** Discovery complete → Architecture defined → Awaiting requirements sign-off

| Step | Status |
|------|--------|
| Device ecosystem mapping | Complete |
| Device technical specifications | Partial (EPC CAB1000 register addresses outstanding) |
| System architecture | Draft v0.1 |
| Data model | Draft v0.1 |
| Questions for Johan | Ready — see [requirements/QUESTIONS_FOR_JOHAN.md](requirements/QUESTIONS_FOR_JOHAN.md) |
| Requirements (PRD) | Not started |
| Technical design (per component) | Not started |
| Implementation | Not started |

**Immediate next action:** Schedule session with Johan to work through [requirements/QUESTIONS_FOR_JOHAN.md](requirements/QUESTIONS_FOR_JOHAN.md). PPC identity (question A1) is the highest-priority item — it could significantly change the control architecture.

---

## Key Stakeholders

| Person | Role |
|--------|------|
| Johan Wolmarans | Client — business owner, subject matter expert on sites and commercial model |
| Marius Bloemhof | Technical consultant — architecture, discovery, requirements, implementation oversight |
