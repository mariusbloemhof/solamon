# Solar Monitor

Cloud platform for monitoring, billing, and remote control of solar PV and battery storage installations.

**Client:** Johan Wolmarans | **Consultant:** Marius Bloemhof | **Phase:** Discovery & Architecture

---

## What is this?

Read [OVERVIEW.md](OVERVIEW.md) for the full picture — purpose, scope, architecture summary, device ecosystem, and current phase.

---

## Workspace Navigation

### Current focus

| Document | Description |
|----------|-------------|
| [OVERVIEW.md](OVERVIEW.md) | Purpose, scope, architecture and data model summary, current phase |
| [GLOSSARY.md](GLOSSARY.md) | Plain-language reference for every acronym, vendor, protocol, and piece of in-house jargon |
| [requirements/QUESTIONS_FOR_JOHAN.md](requirements/QUESTIONS_FOR_JOHAN.md) | Structured questions to close before writing PRD — **next action** |

### Architecture

| Document | Description |
|----------|-------------|
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 3-layer system architecture (edge / cloud / app), integration surface, data flows, resilience, security |
| [architecture/data-model/DATA_MODEL.md](architecture/data-model/DATA_MODEL.md) | Full entity model, time-series design, billing data model, user tiers, storage strategy |

### Discovery

| Document | Description |
|----------|-------------|
| [discovery/DISCOVERY_SUMMARY.md](discovery/DISCOVERY_SUMMARY.md) | Device ecosystem, site topology, architectural decisions, remaining gaps |
| [discovery/DEVICE_SPECS_NEEDED.md](discovery/DEVICE_SPECS_NEEDED.md) | Per-device research checklist and status |
| [discovery/documents/](discovery/documents/) | Original source documents (PDFs, SLD diagrams, reference UI screenshots) |

### Vendor evaluations

| Document | Description |
|----------|-------------|
| [evaluations/teleport.md](evaluations/teleport.md) | WithTheGrid Teleport — full build-vs-buy assessment (verdict: build our own; Teleport as fallback only) |

### Device Specifications

| Document | Device | Status |
|----------|--------|--------|
| [discovery/specs/sinexcel_pws1_500k_protocol.md](discovery/specs/sinexcel_pws1_500k_protocol.md) | Sinexcel PWS1-500K BESS inverter | Partial |
| [discovery/specs/acuvim_l_modbus_registers.md](discovery/specs/acuvim_l_modbus_registers.md) | AccuEnergy Acuvim L — Modbus register map | Complete |
| [discovery/specs/acuvim_l_axm_web2_configuration.md](discovery/specs/acuvim_l_axm_web2_configuration.md) | AccuEnergy AXM-WEB2 — MQTT / HTTP push config | Complete |
| [discovery/specs/dse8610_gencomm_register_map.md](discovery/specs/dse8610_gencomm_register_map.md) | Deep Sea DSE8610 MK2 generator controller | Complete |
| [discovery/specs/schneider_pm5110_modbus_register_map.md](discovery/specs/schneider_pm5110_modbus_register_map.md) | Schneider PM5110 energy meter | Complete |
| [discovery/specs/epc_power_cab1000_status.md](discovery/specs/epc_power_cab1000_status.md) | EPC Power CAB1000 BESS inverter | Partial — register addresses outstanding |

---

## Status

| Area | Status |
|------|--------|
| Discovery — device ecosystem | Complete |
| Discovery — device specs | Partial (EPC CAB1000 register addresses; Sinexcel module confirmation) |
| Architecture | Draft v0.1 |
| Data model | Draft v0.1 |
| Questions for Johan | Ready |
| Requirements (PRD) | Not started — pending Johan Q&A |
| Implementation | Not started |

---

## Three Business Objectives

1. **Remote Monitoring** — live and historical visibility into all site equipment across the fleet
2. **Billing / Metering** — automated invoice generation from revenue-grade Acuvim L energy data
3. **Remote Control** — mode switching, power setpoints, start/stop with full audit trail
