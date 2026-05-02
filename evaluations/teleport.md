# Vendor Evaluation — WithTheGrid Teleport

**Vendor:** WithTheGrid B.V. (Utrecht, Netherlands)
**Product:** Teleport — edge gateway hardware + Teleport Cloud SaaS
**Evaluation context:** Build-vs-buy decision for the **Edge Agent** in our solar monitoring + billing + remote control platform
**Author:** Marius Bloemhof
**Date:** 2026-05-02
**Status:** Working evaluation — pre-vendor-engagement

---

## 1. Executive summary

**Verdict — fallback / fit-with-effort.** Teleport is a real, functional, vendor-managed edge gateway with credible deployments in the Netherlands. It is **not a credible primary platform** for our build because of four independent concerns:

1. **Vendor-managed device library** — new device support is on WithTheGrid's roadmap, not in our YAML. Several of our specific devices (Acuvim L MQTT-push, EPC Power CAB1000, full DSE8610 register set) are not in the public asset library.
2. **SA-deployment friction** — no ICASA / NRCS / SABS certification; 1NCE SIM weak in SA; EU-only AWS cloud (no `af-south-1`); no NRS 097-2-1/-2-3 grid-code certification; no SA partners or installers. Mitigations are negotiable but stack up to the cost of just building our own.
3. **Tightly EU-centric** — ~90 % of disclosed customers are Dutch; data residency is EU-only; no Africa / Middle East / Americas / Asia deployments found.
4. **Seed-stage company with a thin API surface** — ~€4.5 M cumulative funding, ~36-50 staff, archived TypeScript SDK, no OpenAPI spec, no self-serve sandbox.

**Recommendation:** Continue building our own Edge Agent. Engage WithTheGrid sales for a single 30-minute discovery call to (a) confirm the device-support gaps, (b) get an indicative CAPEX+OPEX figure to put in front of Johan as a comparator, and (c) keep the option open for a later EU expansion. Do **not** block any architecture work on the outcome of that call.

**Headline trade-off:** Buying Teleport saves us roughly the edge-agent build effort (a single Linux daemon — material but bounded) at the cost of permanent dependency on a small foreign vendor for device coverage, cellular connectivity, regulatory fit, and language. The build effort is more contained than the dependency cost.

---

## 2. Vendor profile

### 2.1 Company background

- **Founded:** 2016, Utrecht NL
- **Founders:** Rob Everhardt, Steven Hulshof, Jeroen de Bruijn, Paul Mignot (CEO)
- **Original product:** "Asset Monitoring Platform" (AMP) — for grid-operator infrastructure monitoring
- **Current focus:** Teleport Gateway (the edge agent + cloud SaaS for renewable assets)
- **Sources:** [Crunchbase](https://www.crunchbase.com/organization/withthegrid), [LinkedIn](https://www.linkedin.com/company/withthegrid/)

### 2.2 Funding & team

- **Headcount:** ~36 (PitchBook estimate) to "50+" (own LinkedIn page)
- **Cumulative funding:** ~€4.5 M
- **Latest round:** **€3.5 M — March 2025** (€2 M equity from Move Energy + €1.5 M debt from Rabobank / Nationaal Groenfonds)
- **Stage:** Seed / pre-Series-A by funding scale
- **Source:** [pv-magazine 2025-03-19](https://www.pv-magazine.com/2025/03/19/withthegrid-expands-real-time-renewable-energy-asset-controlling-platform/), [funding press release](https://withthegrid.com/withthegrid-secures-funding/)

> **Risk flag:** A 5-year deployment for a SA client implies a 5-year vendor relationship. Seed-stage means meaningful runway risk — acceptable for a fallback role, less acceptable as a critical-path dependency.

### 2.3 Certifications

| Certification | Held? | Notes |
|---------------|-------|-------|
| ISO 27001 | Yes | Information security |
| ISO 9001 | Yes | Quality management |
| NIS2 compliance | Stated | EU critical-infrastructure directive |
| RfG (Requirements for Generators) | Multiple EU markets | Grid code certification |
| RTI (Real-Time Interface) | NL | Dutch grid-operator certification |
| Hardware safety | EN/UL/IEC 62368-1 | Standard industrial gateway certifications |
| SOC 2 | **Not found** | Common North American expectation |
| IEC 62443 | **Not found** | OT cybersecurity standard for industrial systems |
| GDPR DPA | Presumed | Not surfaced on public site; ask sales |
| POPIA DPA | **Unknown** | SA personal-data protection — see §9 |

---

## 3. Product overview

### 3.1 What Teleport is

A hybrid product:

- **Hardware:** A vendor-supplied gateway device (DIN-rail / IP65 industrial form factor, Ethernet + SIM, optional RS-485 add-on boards)
- **Firmware:** Managed by WithTheGrid; updated centrally; not user-modifiable
- **Cloud:** Teleport Cloud SaaS, EU-hosted, ISO 27001 certified
- **Source:** [Teleport product page](https://withthegrid.com/teleport/), [Teleport intro docs](https://teleport.withthegrid.com/introduction/)

This is fundamentally different from our planned Edge Agent (a Linux daemon we run on our own hardware, configured via cloud-pushed YAML, fully under our control).

### 3.2 Hardware

- DIN-rail mountable industrial gateway
- Ethernet (LAN-side device polling) + SIM (cellular WAN)
- Optional RS-485 add-on boards (to talk Modbus RTU to non-Ethernet devices)
- "Energy Hub" variant for sites with grid-edge control responsibilities
- **Source:** [Energy Hub product page](https://withthegrid.com/teleport/energy-hub/)

### 3.3 Cloud platform

- **Teleport Cloud** — proprietary EU-hosted SaaS
- Provides: device onboarding console, asset library, control strategy editor, dashboards, REST API, data forwarders
- Default telemetry cadence: **5 minutes** (1-minute / "flash" available at surcharge)
- Default cloud retention: **14 days** (then forwarded out via data forwarders to your own DB / broker)
- **Source:** [Teleport FAQ](https://teleport.withthegrid.com/faq/)

### 3.4 Local execution model

The device runs **local control strategies** so the site keeps operating during WAN outage:

- `limitPower` / `limitProductionPower` — caps export to grid based on local meter feedback
- `setBatteryOperation` — schedule-based charge/discharge
- `setEVOperation` — EV charger schedule
- `applyAfrrDeltaSetpoint` — frequency response / aFRR (advanced grid services)
- **Source:** [Teleport control strategies](https://teleport.withthegrid.com/control-strategies/)

This is genuinely useful prior art for our control design, regardless of whether we adopt Teleport.

---

## 4. Architecture & integration model

### 4.1 Where Teleport sits in a typical EMS

```
Site LAN devices (Modbus TCP / RS-485)
        │
        ▼
   Teleport device  ── runs local control strategies (limitPower, setBatteryOperation)
        │
        ▼ (cellular or fibre)
  Teleport Cloud (EU SaaS)
        │
        ├──► Console UI (operators & integrators)
        ├──► REST API (your cloud reads / commands)
        └──► Data forwarders (Kafka, MQTT, SQL DBs, S3, MSSQL...)
                │
                ▼
        Customer's own systems (e.g., your billing engine, dashboard)
```

The customer-facing integration pattern is **"Teleport device + your own cloud"** — exactly the role we'd consider for our project.

### 4.2 Data path (telemetry)

- Device polls assets on-site at configured cadence
- Pushes telemetry to Teleport Cloud (default 5-min)
- Cloud holds 14 days; forwards continuously to your endpoint via data forwarders
- **At-least-once** delivery on the forwarded stream — your downstream must dedupe on `(teleportHashId, assetIdentifier, measuredAt)`
- **Source:** [Teleport data forwarding](https://teleport.withthegrid.com/data-forwarding/)

### 4.3 Control path

- Operator issues command via Teleport Console UI or `PUT /v2/schedule/` REST endpoint
- Cloud accepts the schedule (HTTP 201 = "reached cloud, will deliver to device — including offline ones on reconnect")
- Device applies the command locally
- Closed-loop verification via continuous meter polling
- **No explicit per-command device-level ack** in the API response — confirmation is implicit via subsequent telemetry showing the change took
- **Source:** [scheduling asset commands](https://teleport.withthegrid.com/api/scheduling-asset-commands/)

### 4.4 Configuration / onboarding model

- Customer fills an **"Asset Onboarding Form"** for WithTheGrid
- WithTheGrid pre-configures the device for the customer's specific asset list
- Device ships **ready to install**
- Ongoing config via Teleport Console (UI) and API
- **Not a YAML/Git-Ops integrator-driven model** — config flows through WithTheGrid, not through our own deployment pipeline
- **Source:** [Teleport installation guide](https://teleport.withthegrid.com/installation-guide/)

> **Implication for our project:** Every site commissioning becomes a vendor-coordinated step rather than a self-service deployment. Acceptable for ~5 sites; problematic for ~50.

---

## 5. Device & protocol support

### 5.1 Protocol coverage

| Protocol | Supported? | Notes |
|----------|-----------|-------|
| Modbus TCP | Yes | Primary device protocol |
| Modbus RTU | Yes | Via add-on RS-485 boards |
| OPC XML-DA | Yes | Industrial / SCADA |
| SunSpec | Yes | Standard inverter/BESS register layout |
| IEC 60870-5-104 | Yes | Utility SCADA |
| IEC 61850 | Yes | Substation automation |
| MQTT (as device ingress) | **Not documented** | A blocker for AccuEnergy AXM-WEB2 push model |
| HTTP push (as device ingress) | **Not documented** | Same |
| BACnet, DNP3 | Not documented | — |

**Critical gap:** Our architecture assumes the **Acuvim L AXM-WEB2 pushes MQTT directly** to our cloud. Teleport doesn't appear to ingest MQTT push from a third-party device. We'd have to either (a) fall back to Modbus TCP polling of the Acuvim L (loses the AXM-WEB2's 3 GB offline cache benefit), or (b) push directly to our own cloud and bypass Teleport for billing data.

### 5.2 Device coverage vs our specific list

| Device | Our requirement | Teleport coverage |
|--------|----------------|-------------------|
| Huawei SmartLogger V300R024 | Required | **Yes** — Logger1000A, Logger3000A/B, COM100E, Modbus TCP confirmed |
| Sinexcel PWS1-500K | Required | **Partial** — PWS1725K-One PCS + Sparq listed; **PWS1-500K not confirmed by name** — needs vendor confirmation |
| EPC Power CAB1000 | Required | **Not found** in public asset library |
| Schneider PM5110 | Required | **Not confirmed** — Schneider listed under metering but PM5110 not by name |
| Deep Sea DSE8610 MK2 | Required | DSE family supported under generators; specific 8610 model unconfirmed |
| AccuEnergy Acuvim L (Modbus TCP) | Required | **Not found** in asset library |
| AccuEnergy AXM-WEB2 (MQTT push) | Required (billing path) | **Not supported as ingress** |
| MOXA NPort gateway | Transparent | Not relevant — the gateway looks like the bridged device |
| Lantronix gateway | Transparent | Same |
| PPC (TBD make/model) | Required | Cannot assess until model known |

**Sources:** [asset library index](https://teleport.withthegrid.com/installation-guide/asset-library/), [Huawei page](https://teleport.withthegrid.com/installation-guide/asset-library/solar/huawei/), [Sinexcel page](https://teleport.withthegrid.com/installation-guide/asset-library/battery/sinexcel/)

> **Bottom line on device fit:** Of 8 critical device types, 1 is fully confirmed (SmartLogger), 3-4 need vendor confirmation, and 2 (Acuvim L MQTT path, EPC CAB1000) appear genuinely missing. Adding new device support is gated on WithTheGrid's roadmap and pricing — explicit quote: *"we can make a small and cost-free adjustment to connect the Teleport to your park"* but lead time and cost ceiling not specified.

---

## 6. API maturity

**Verdict: Functional but thin / needs vendor support.** Real, versioned, rate-limited REST API — not vapourware. But several material gaps.

### 6.1 API style & versioning

- **REST + JSON, ISO-8601 dates** — [API getting started](https://teleport.withthegrid.com/api/)
- **URL-based versioning** (`/v1/`, `/v2/`)
- **Deprecation policy:** ≥6 months notice via email
- **No OpenAPI / Swagger spec published**
- **No Postman collection**

### 6.2 Authentication & access

- **Bearer tokens** provisioned manually by `support@withthegrid.com`
- No OAuth, no per-user scopes documented, no token rotation story documented
- **No self-serve sandbox** — sales-gated access

### 6.3 Data API

- **Pull endpoints exist but are thin** — the canonical pattern is to forward telemetry via "data forwarders" into your own DB / broker
- **No bulk S3 export**
- **No streaming pull**
- 14-day buffer on the cloud side for delivery retries

### 6.4 Control API

- `PUT /v2/schedule/` — typed commands (`LimitProductionPower`, `SetBatteryOperation`, `SetEVOperation`, `ApplyAfrrDeltaSetpoint`, `LimitPower`)
- HTTP 201 = "reached cloud, will deliver to device on reconnect"
- **No explicit per-command device-level ack** in response
- **No idempotency-key header** — `PUT` endpoint is idempotent by overwrite-per-asset semantics (re-submit overwrites prior schedule for that asset)
- **Source:** [scheduling asset commands](https://teleport.withthegrid.com/api/scheduling-asset-commands/)

> **Audit trail gap:** Public docs do not describe a signed write-log with operator identity, before/after values, and read-back confirmation. This is a non-trivial requirement for our system (compliance, dispute defence). Must be confirmed with sales.

### 6.5 SDKs & developer experience

- **Official TypeScript SDK:** `@withthegrid/platform-sdk`
- **Status: archived since June 2023** (read-only, last release v18.3.1 March 2023, 2 GitHub stars)
- **Source:** [github.com/withthegrid/platform-sdk](https://github.com/withthegrid/platform-sdk)
- **No Python, Go, Java, .NET SDK** found
- The SDK's archival is a meaningful negative signal — suggests low engineering investment in external integration patterns

### 6.6 Documentation quality

- Endpoint reference + cURL examples
- **Missing:** Postman collection, error-code catalogue beyond per-endpoint enums, public changelog page
- Documentation language: **English** (Dutch versions partial)

### 6.7 Sandbox & onboarding

- Demo Teleport device available **on request from their test lab — not self-serve**
- Sales conversation required before access
- This is normal for industrial vendors but a friction point compared to modern API-first products

### 6.8 Local API on the device

- **Local Modbus TCP server** exposed on the device itself — fixed register layout, FC 03/04/06/16
- **Real-Time Interface (RTI)** for grid operators (NL-specific)
- **No local REST API documented** — on-site engineers cannot debug via HTTP without internet to reach the cloud console

---

## 7. Data architecture

### 7.1 Telemetry cadence & retention

| Setting | Default | Configurable to |
|---------|---------|-----------------|
| Telemetry cadence | 5 minutes | 1 minute ("flash") at surcharge |
| Cloud retention | 14 days | — |
| Local device buffer | **Not quantified** | Ask sales |

> **Mismatch with our spec:** We've designed for 60-second heartbeat and 72-hour local buffer. Teleport's default is 60× slower and the local buffer depth is undocumented.

### 7.2 Data forwarders

Out of Teleport Cloud, into your own systems:

- HTTPS endpoint
- Apache Kafka
- RabbitMQ (AMQP)
- MQTT
- Influx
- Grafana Loki
- MySQL, MSSQL, PostgreSQL
- Amazon SNS
- Azure Service Bus
- **Source:** [data forwarding](https://teleport.withthegrid.com/data-forwarding/)

This is the **right integration pattern for our build** — Teleport handles the device side, our cloud receives over MQTT (or Postgres direct insert) and runs everything else.

### 7.3 Storage / retention

The 14-day cloud retention assumes the customer has set up at least one data forwarder. If a forwarder is unhealthy and the buffer fills, behaviour beyond 14 days is undocumented.

---

## 8. Control & audit

### 8.1 Available commands

| Command | Targets | Notes |
|---------|---------|-------|
| `LimitProductionPower` | PV inverters | Active power cap |
| `LimitPower` | Site / multiple assets | Aggregate site cap |
| `SetBatteryOperation` | BESS PCS | Schedule charge/discharge |
| `SetEVOperation` | EV chargers | Out of our scope |
| `ApplyAfrrDeltaSetpoint` | aFRR participants | Out of our v1 scope |

### 8.2 Closed-loop control

The device polls site meters continuously and adjusts inverter setpoints to maintain the target. This **is** the right pattern for grid-export limiting — useful prior art.

### 8.3 Audit trail (gap)

**Not documented in public material.** Our requirements explicitly need: who issued the command, when, what value, what the device confirmed. Must be confirmed with sales.

---

## 9. Localization & regional fit

**SA-fit verdict: "Fit-with-significant-effort".** Teleport is hardware-globally-deployable but commercially, regulatorily and operationally **EU-tuned**. The device itself can run on a SA C&I site; the cloud, certifications, connectivity bundle and grid-code evidence are all EU-shaped and require negotiation.

### 9.1 UI and language

- The marketing site offers an **EN / NL / EL** language toggle
- The **Teleport Console UI language is not stated publicly** — likely English-first, possibly Dutch
- Documentation is **English** (Dutch versions partial)
- No documented user-side language configuration per tenant
- **Source:** [withthegrid.com/teleport](https://withthegrid.com/teleport/), [console.teleport.withthegrid.com](https://console.teleport.withthegrid.com/) (page returned title only — login required)
- **Implication:** Johan's end-customer-facing portal can't be assumed multi-lingual; we'd render the client portal ourselves on top of the data forwarders rather than expose Console directly.

### 9.2 Hardware certifications

| Certification | Confirmed? | Notes |
|---------------|-----------|-------|
| ISO 27001, ISO 9001 | Yes | Information security + quality |
| RED 3.3 | Yes | EU radio equipment directive |
| NIS2 compliance | Stated | EU critical-infrastructure directive |
| CE / UKCA | **Not explicitly listed** | Likely covered by RED 3.3 but not stated |
| FCC | Not listed | No US-stated certification |
| **ICASA (SA radio approval)** | **Not listed** | Required for cellular use in SA |
| **NRCS / SABS (SA electrical)** | **Not listed** | Required for sale in SA |
| RCM (Australia) | Not listed | — |

- **Source:** [withthegrid.com/security](https://withthegrid.com/security/), [Teleport FAQ](https://withthegrid.com/teleport/faq/)
- **Implication:** Importing and operating an unapproved radio device in SA exposes the client to seizure and fines. Either WithTheGrid funds ICASA type approval, or we pursue a single-site Letter of Authority via SABS / NRCS, or we swap the cellular module for a locally-approved one (likely voids the device warranty).

### 9.3 Power, operating environment, hardware specs

| Spec | Value |
|------|-------|
| Power input | **8–36 VDC** (direct) |
| PSU (bundled) | **100–240 VAC, 50/60 Hz** with EU/UK/US/AU plug |
| Operating temperature | **-40 °C to 80 °C** |
| Cellular | **LTE Cat 1 (4G)** |
| Form factor | DIN-rail / IP65 |

- **Source:** [Teleport hardware specifications](https://teleport.withthegrid.com/installation-guide/appendix/specifications/)
- **Implication:** Physically the device runs on SA grid (230 V / 50 Hz) and copes with C&I summer temperatures. Hardware is not the blocker.

### 9.4 Cellular / SIM

- Bundled connectivity: **1NCE global SIM**
- Vendor's own FAQ explicitly warns: *"generally work well in the European Union and Great Britain but may have issues in the USA"*
- **No SA carrier list** (MTN / Vodacom / Cell C / Telkom Mobile)
- 1NCE relies on roaming agreements that historically don't cover SA reliably for permanent IoT
- **BYO-SIM is not publicly supported** but worth negotiating
- LTE Cat 1 band coverage on the modem must be verified specifically for **band 28 (700 MHz)** — the SA workhorse band
- **Source:** [Teleport FAQ](https://withthegrid.com/teleport/faq/)
- **Implication:** Connectivity is the second-biggest deployment blocker after certification. Mitigation requires explicit BYO-SIM clause in the contract.

### 9.5 Grid-code applicability

- Confirmed certifications: **RfG-aligned for NL (RTI), BE (Telecontrole), GR, DK**
- **No NRS 097-2-1** (SA small-scale embedded generation) reference
- **No NRS 097-2-3** (SA utility-scale) reference
- **No Eskom / SA municipality** mention anywhere in vendor material
- **No load-shedding awareness** documented
- **Source:** [withthegrid.com/teleport](https://withthegrid.com/teleport/), [withthegrid.com/be/teleport-en](https://withthegrid.com/be/teleport-en/), [NRS 097-2-1:2024](https://www.sseg.org.za/wp-content/uploads/2024/02/NRS-097-2-1-Published-2024.pdf)
- **Implication:** For any grid-tied control duty (curtailment, export limit) Teleport's compliance evidence is RfG, not what a SA SSEG application requires. The protection function on a SA site must remain with the inverter's own NRS-097-2-1 certified protection relay; Teleport cannot be claimed as the protection device on the SSEG application.

### 9.6 Data residency and POPIA

- *"Cloud services run on top of AWS infrastructure, in the EU only"* — explicit vendor statement
- **No `af-south-1` (AWS Cape Town) option**
- **No customer choice of region**
- GDPR DPA presumed; **POPIA not mentioned** in any public document
- **Source:** [Teleport docs introduction](https://teleport.withthegrid.com/introduction/), [withthegrid.com/security](https://withthegrid.com/security/)
- **Implication:** SA customers must accept EU storage and sign cross-border-transfer safeguards under POPIA Section 72. The self-hosted cloud-receiver option (under contract / escrow) becomes essential rather than nice-to-have.

### 9.7 Locale formatting (timezone, currency, date)

- **Not stated in any public document**
- No documented `Africa/Johannesburg` timezone option
- No documented **ZAR** currency rendering
- No documented DD/MM/YYYY date format setting
- **Confidence:** Low — silence rather than denial
- **Implication:** Risk of EUR / CET / DD-MM-YYYY hardcoded assumptions in reports and invoices. The mitigation is to never let Teleport Console face the end-customer — render dashboards and invoices in our own application layer where we control the formatting.

### 9.8 Support coverage in SA timezone

- Single phone number: **+31 (0)8 57 99 01 45** (Netherlands)
- Email: `info@withthegrid.com`, `support@withthegrid.com`
- Vendor claims *"24/7 system monitoring backed by SLAs"* but team is NL-based → **CET working hours, not SAST on-call documented**
- **No SA installer or partner network**
- Field commissioning is remote-only or fly-in
- **Source:** [WithTheGrid — Become a partner](https://withthegrid.com/become-a-partner/)
- **Implication:** Johan's team becomes the Tier-1 support layer in SA. WithTheGrid retained for Tier-2 with at least 09:00-18:00 SAST overlap (which is 08:00-17:00 CET in summer / 09:00-18:00 CET in winter — workable).

### 9.9 White-labelling and branding

- Partner programme exists with co-marketing
- **No white-label client portal product is publicly disclosed**
- Console URL is fixed: `console.teleport.withthegrid.com`
- White-label cost / minimum commitment not public
- **Source:** [Become a partner](https://withthegrid.com/become-a-partner/)
- **Implication:** Johan can't easily sell Teleport Console to his end-customers under his own brand. The mitigation is the same as §9.7 — render the client portal in our own application.

### 9.10 Roadmap signals — Africa / SA

- Vendor statement: *"Can be used globally. Already deployed in NL, ES, BE, SE, UK"*
- **Africa / SA never mentioned** in vendor material reviewed
- No staff with documented SA presence on LinkedIn
- No SA-relevant features (load-shedding, NRS 097, ZAR, SAST) on any documented roadmap
- **Source:** [Teleport FAQ](https://withthegrid.com/teleport/faq/)
- **Implication:** No tailwind from the vendor. Anything we want for SA we have to negotiate in.

### 9.11 SA-specific blockers (consolidated)

| # | Blocker | Severity | Mitigation requirement |
|---|---------|---------|------------------------|
| 1 | No ICASA / NRCS / SABS certification | **Critical** | Type-approval funded by WithTheGrid, or per-site LoA via SABS, or modem swap (warranty risk) |
| 2 | 1NCE SIM weak in SA | **Critical** | Negotiate BYO-SIM (MTN / Vodacom IoT APN); verify LTE band 28 on modem |
| 3 | EU-only cloud (no `af-south-1`) | **High** | Self-hosted cloud-receiver under contract; deploy in `af-south-1`; or accept EU + POPIA Section 72 safeguards |
| 4 | No NRS 097-2-1/-2-3 certification | **High** | Use Teleport for monitoring/billing only; keep grid-protection on the inverter's certified relay |
| 5 | No SA support presence | **Medium** | Johan's team is Tier-1; WithTheGrid Tier-2 with SAST-overlap SLA |
| 6 | No white-label client portal | **Medium** | Render client portal in our own application layer over the data forwarder |
| 7 | Locale (ZAR / SAST / DD-MM-YYYY) silence | **Medium** | Never expose Console to end-customer; render everything in our own app |
| 8 | No load-shedding awareness | **Low** | Implement load-shedding handling in our own application logic |

> **Bottom line on §9:** The device is fine. The cloud and commercials are EU-shaped. If we buy Teleport, we must budget for at least: ICASA approval (or modem swap), a BYO-SIM clause, a self-hosted cloud-receiver clause, and an application layer above the Console for end-customer UX. **All four of those mitigations together approach the cost of just building our own Edge Agent.**

---

## 10. Commercial model

### 10.1 Pricing structure

- **Hardware purchase + connectivity + subscription**
- **<1 MWp sites:** 3-year all-inclusive CAPEX bundle
- **>1 MWp sites:** CAPEX + recurring OPEX
- **Pricing not published** — quote required via Console / sales
- **Source:** [Teleport FAQ](https://withthegrid.com/teleport/faq/)

### 10.2 What's included (default)

- Device hardware
- Cellular SIM (1NCE) and connectivity
- 5-minute telemetry cadence
- 14-day cloud retention
- Console access
- Standard asset library coverage
- Firmware updates

### 10.3 Surcharges

- 1-minute / "flash" telemetry cadence
- Custom asset additions ("small and cost-free" for some, paid for others — not clarified)
- Source-code escrow for self-hosted cloud receiver
- White-labelling (terms not disclosed)

### 10.4 Hardware ownership

Customer owns the device; subscription covers cloud + connectivity. Subscription lapse implications (does the device stop functioning, does telemetry stop forwarding, does local control keep running?) not explicitly documented.

---

## 11. References & deployments

### 11.1 Named customers

| Customer / project | Country | Vertical | Disclosed scale |
|-------------------|---------|----------|-----------------|
| Novar | NL | Utility-scale solar | **650 MW** portfolio |
| Return / SemperPower "Castor" | NL | BESS | **30.7 MW** (largest battery in NL at time of writing) |
| Vattenfall | SE | Utility / IPP | not disclosed |
| Eneco | NL | Utility | not disclosed |
| Essent | NL | Utility | not disclosed |
| Edmij | NL | Solar + wind + BESS aggregator | not disclosed |
| Vandebron | NL | Wind turbine control | not disclosed |
| Johan Cruijff ArenA | NL | Stadium battery | ~3 MWh (well-known) |
| Port of Amsterdam | NL | Energy hub | not disclosed |
| Pannenweg II energy hub | NL (Limburg) | C&I park (GTO with Enexis) | 14 companies, 1 Teleport per site |
| Steddion (integrator partner) | NL | C&I solar + BESS + EV | "all customer locations" |
| HEDNO | GR | Utility-scale (>400 kW) | Target market — no named projects |
| OM\|Nieuwe Energie, NieuweStroom, Skoon, ELIX, Groendus, Repowered | NL/BE | Various | Logos only |

**Sources:** [Teleport product page](https://withthegrid.com/teleport/), [Pannenweg II case study](https://withthegrid.com/how-pannenweg-ii-implements-gto/), [Steddion partnership](https://withthegrid.com/steddion-and-withthegrid-partnership/), [pv-magazine 2025-03-19](https://www.pv-magazine.com/2025/03/19/withthegrid-expands-real-time-renewable-energy-asset-controlling-platform/)

### 11.2 Aggregate scale

- **Vendor claim:** "single sites to 1 GW under management"
- **Vendor claim:** 450+ asset types supported
- **Disclosed total:** No public total-device or total-site count

### 11.3 Geographic distribution

- **Confirmed deployments:** NL, BE, ES, SE, UK
- **Expansion-stage:** Belgium, Greece (per March 2025 announcement)
- **No deployments found:** Africa, Middle East, Americas, Asia
- **Concentration risk:** ~90 % NL — meaningful for a SA client

---

## 12. Comparison vs. building our own Edge Agent

| Dimension | Teleport (buy) | Our build |
|-----------|----------------|-----------|
| Hardware sourcing | Vendor-provided, ready to install | Off-the-shelf industrial PC / Teltonika / Raspberry Pi 4 — we choose |
| Device integration | WithTheGrid roadmap-gated | Self-service via register-map config in our cloud |
| Modbus TCP polling | Yes | Yes |
| Modbus RTU (RS-485) | Via add-on board | Via MOXA NPort (already required) |
| MQTT-push ingress (Acuvim L) | **Not supported** | Yes — native to our stack |
| Telemetry cadence | 5 min default; 1 min surcharge | 10 s / 30 s / 60 s tiered (per metric type) |
| Local buffer | Undocumented | 72 h, designed-in |
| Heartbeat | Not stated | 60 s, designed-in |
| Control commands | Yes — typed | Yes — Modbus FC06/FC16 with read-back |
| Read-back verification | **Not documented** | Yes — designed-in |
| Audit trail | **Not documented** | Yes — every command logged immutable |
| Cloud platform | Their SaaS, EU-only | Ours, region of choice |
| Data residency | EU only by default | Wherever we deploy |
| Multi-tenancy | Their model | Our model — multi-site from day one |
| Client portal | Not part of Teleport | First-class in our scope |
| Billing engine | Not part of Teleport | First-class in our scope |
| White-labelling | Possible (terms unclear) | First-class in our scope |
| Time to first telemetry | Faster — pre-configured devices ship | Slower — write integration code per device |
| Time to a complete platform | **Same or slower** — we still build cloud+app+billing | Self-paced |
| Cost model | CAPEX + recurring per-site | Engineering effort up front; minimal recurring |
| Vendor lock-in | High — re-platforming requires hardware swap | None |
| Vendor risk | Seed-stage NL company | Internal team |

> **Critical observation:** Buying Teleport saves us the **edge** build effort but **doesn't shorten the cloud + dashboard + billing engine work** — which is the bulk of the project. We'd still need to build everything Johan actually pays us for. The edge agent is the smallest, most contained, most well-specified component of our platform; outsourcing it for the largest, least-bounded dependency cost is a poor trade.

---

## 13. Risks & concerns for our use case

| Risk | Severity | Notes |
|------|---------|-------|
| **No ICASA / NRCS / SABS certification** | **Critical** | Importing and operating an unapproved radio device in SA exposes the client to seizure and fines |
| **1NCE SIM weak in SA** | **Critical** | Vendor's own FAQ flags non-EU/UK issues; no SA carrier list; BYO-SIM not publicly supported |
| **EU-only AWS cloud (no `af-south-1`)** | **High** | POPIA cross-border-transfer obligations; needs Section 72 safeguards or self-hosted receiver |
| **No NRS 097-2-1/-2-3 grid-code certification** | **High** | Cannot be claimed as protection device on SA SSEG application; protection function stays with inverter |
| Acuvim L MQTT-push path not supported | **High** | Forces fall back to Modbus polling for billing; loses AXM-WEB2 3 GB cache benefit |
| EPC Power CAB1000 not in asset library | **High** | Same problem as our own build, but with vendor lead time added |
| Audit trail not documented | **Medium-High** | Hard to ship Johan's commercial model without one |
| Seed-stage vendor (~€4.5 M total funding) | **Medium** | 5-year deployment risk; mitigated by self-hosted receiver option (under contract) |
| No SA support presence (NL CET hours) | **Medium** | Johan's team becomes Tier-1; WithTheGrid Tier-2 with SAST overlap |
| No white-label client portal | **Medium** | We render our own client portal regardless |
| Locale silence (ZAR / SAST / DD-MM-YYYY) | **Medium** | Risk of EUR / CET hardcoding; mitigated by rendering reports in our own app |
| Archived TypeScript SDK | **Medium** | Engineering signal; no current SDK maintenance |
| Vendor-managed config / onboarding | **Medium** | Acceptable at 5 sites; problematic at 50 |
| No SOC 2, no IEC 62443 | **Low–Medium** | Some SA enterprise customers will want these |
| 5-min default telemetry cadence | **Low** | 1-min surcharge available |
| 14-day cloud retention | **Low** | Adequate if data forwarder is reliable |
| No load-shedding awareness | **Low** | Handle in our application layer |

---

## 14. Decision matrix

| Criterion | Weight | Teleport | Build | Notes |
|-----------|--------|----------|-------|-------|
| Coverage of our specific devices | High | 4 / 10 | 9 / 10 | Major gaps on Acuvim L MQTT, EPC CAB1000 |
| Time to first telemetry | Medium | 8 / 10 | 5 / 10 | Pre-configured device ships faster |
| Time to a complete platform | High | 5 / 10 | 7 / 10 | Cloud / app / billing still to build either way |
| API quality for our cloud | High | 5 / 10 | 10 / 10 | Their API thin; ours is whatever we need |
| Control & audit capability | High | 5 / 10 | 9 / 10 | Audit trail not documented in Teleport |
| Data residency / POPIA | High | 3 / 10 | 10 / 10 | EU-only by default |
| Vendor risk | High | 4 / 10 | 9 / 10 | Seed-stage NL vs. internal team |
| Cost (5-year TCO) | Medium | Unknown | Predictable | Pricing opaque |
| Flexibility for future devices | High | 4 / 10 | 10 / 10 | Their roadmap vs. our config |
| Localization fit for SA | High | 2 / 10 | 10 / 10 | No ICASA / NRCS / NRS-097; EU-only cloud; weak SA SIM; no SA partners — see §9 |
| White-label client portal | Medium | TBD | 10 / 10 | First-class in our scope |
| **Weighted total (qualitative)** | | **~5 / 10** | **~9 / 10** | Build wins on most weighted criteria |

---

## 15. Recommendation

**Build our own Edge Agent.** Use Teleport as a **comparator and fallback option** but do not block any architectural work on the outcome of WithTheGrid engagement.

**Specific actions:**

1. **Continue the architecture and data-model work** as drafted — no changes from this evaluation.
2. **Send WithTheGrid sales a single email** with the open questions in §16. Goal: indicative pricing + confirmation of device-support gaps. Budget 30 minutes for a follow-up call.
3. **Capture the result** in this document as an Appendix and treat the matter as closed unless something material changes.
4. **Revisit if** (a) we expand to EU markets, (b) we find a SA partner deploying Teleport already, or (c) WithTheGrid announces SA presence / certification.

---

## 16. Open questions for WithTheGrid sales engagement

### Device support
1. Is **Sinexcel PWS1-500K** specifically supported (you confirm only PWS1725K-One in public material)? Lead time and cost to add if not?
2. Confirm support for **EPC Power CAB1000** (over Lantronix serial-to-TCP gateway)
3. Confirm support for **AccuEnergy Acuvim L** including the **AXM-WEB2 MQTT push** as ingress
4. Confirm specific support for **Schneider PM5110** (vs. generic Schneider)
5. Confirm specific support for **Deep Sea DSE8610 MK2** (full register set)

### Operational behaviour
6. **Local store-and-forward** — how many hours of telemetry does the device buffer if WAN drops? Is the buffer FIFO-bounded? Persistent across reboots?
7. **Heartbeat / sample rate** — cost delta for 60-second vs. default 5-minute, per-tag vs. per-device pricing?
8. **Audit trail** — are control writes logged with operator identity, timestamp, before/after values, and read-back confirmation? Is the log exportable?

### Regulatory & SA-specific
9. **ICASA / NRCS / SABS approval** — does the device hold any SA-relevant certifications? If not, will WithTheGrid sponsor type-approval, or is per-site Letter-of-Authority via SABS the only path?
10. **Cellular** — can the bundled SIM be swapped for an MTN / Vodacom / Cell C SA SIM? Is dual-SIM failover supported? Does the modem cover **LTE band 28 (700 MHz)** — the SA workhorse?
11. **NRS 097-2-1 / NRS 097-2-3** — any plan to certify? Without it, what control duties can Teleport perform on a SA SSEG application?
12. **POPIA** — is a POPIA-aligned Data Processing Agreement available, or only GDPR? Section 72 cross-border transfer terms?

### Data residency & deployment
13. **Self-hosted cloud receiver** — under what commercial terms is the source code provided (escrow, license cost, ongoing fees)? Can it be deployed in `af-south-1`? What's still SaaS-bound (firmware updates, asset library, Console)?
14. **Subscription lapse behaviour** — does the device continue local control? Does data forwarding stop? Does the asset library license persist?

### Pricing & commercial
15. **Indicative pricing** for a 5-site, ~500 kW-each SA portfolio over 3 years — both CAPEX bundle and recurring, with the SA-specific clauses (BYO-SIM, ICASA, self-hosted receiver) included.
16. **White-labelling** — terms, costs, minimum commitment for custom domain, custom email sender, custom PDF header.

### Support & operations
17. **SA support coverage** — overlap hours guaranteed in SAST? Tier-2 SLA? Any local partner WithTheGrid would appoint?
18. **Local UI / on-site engineer access** — can a field tech debug a Modbus comms issue without internet access?
19. **Locale config** — can the Console show data in `Africa/Johannesburg`, currency in **ZAR**, dates in DD/MM/YYYY?

---

## 17. Appendix: sources

### Primary (vendor)

- [WithTheGrid — Teleport product page](https://withthegrid.com/teleport/)
- [WithTheGrid — Teleport FAQ (marketing)](https://withthegrid.com/teleport/faq/)
- [WithTheGrid — Energy Hub / local EMS](https://withthegrid.com/teleport/energy-hub/)
- [WithTheGrid — Integrations](https://withthegrid.com/teleport/integrations/)
- [WithTheGrid — What we don't do](https://withthegrid.com/what-we-dont-do/)
- [WithTheGrid — Security & certifications](https://withthegrid.com/security/)
- [Teleport docs — Introduction](https://teleport.withthegrid.com/introduction/)
- [Teleport docs — Installation guide](https://teleport.withthegrid.com/installation-guide/)
- [Teleport docs — Asset library](https://teleport.withthegrid.com/installation-guide/asset-library/)
- [Teleport docs — Huawei SmartLogger](https://teleport.withthegrid.com/installation-guide/asset-library/solar/huawei/)
- [Teleport docs — Modbus TCP local server](https://teleport.withthegrid.com/api/local/modbus/)
- [Teleport docs — Control strategies](https://teleport.withthegrid.com/control-strategies/)
- [Teleport docs — Monitoring](https://teleport.withthegrid.com/monitoring/)
- [Teleport docs — Data forwarding](https://teleport.withthegrid.com/data-forwarding/)
- [Teleport docs — API getting started](https://teleport.withthegrid.com/api/)
- [Teleport docs — Scheduling asset commands](https://teleport.withthegrid.com/api/scheduling-asset-commands/)
- [Teleport docs — FAQ (technical)](https://teleport.withthegrid.com/faq/)

### Case studies (vendor-published)

- [How Pannenweg II implements GTO](https://withthegrid.com/how-pannenweg-ii-implements-gto/)
- [Steddion & WithTheGrid partnership](https://withthegrid.com/steddion-and-withthegrid-partnership/)
- [WithTheGrid secures funding (March 2025)](https://withthegrid.com/withthegrid-secures-funding/)

### Localization-specific

- [Teleport hardware specifications](https://teleport.withthegrid.com/installation-guide/appendix/specifications/)
- [Teleport — Belgium product page](https://withthegrid.com/be/teleport-en/)
- [WithTheGrid — Become a partner](https://withthegrid.com/become-a-partner/)

### Third-party

- [pv-magazine — WithTheGrid expands real-time renewable energy asset controlling platform (2025-03-19)](https://www.pv-magazine.com/2025/03/19/withthegrid-expands-real-time-renewable-energy-asset-controlling-platform/)
- [Crunchbase — WithTheGrid](https://www.crunchbase.com/organization/withthegrid)
- [LinkedIn — WithTheGrid company page](https://www.linkedin.com/company/withthegrid/)
- [GitHub — withthegrid/platform-sdk (archived)](https://github.com/withthegrid/platform-sdk)

### SA regulatory references

- [NRS 097-2-1:2024 — SSEG, SA](https://www.sseg.org.za/wp-content/uploads/2024/02/NRS-097-2-1-Published-2024.pdf)
- [NRS 097-2-3:2023 — utility-scale embedded generation, SA](https://www.sseg.org.za/wp-content/uploads/2014/01/NRS-097-2-3-Feb2023.pdf)

### See also

- [architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) — our Edge Agent architecture (the comparison baseline)
- [CLAUDE.md](../CLAUDE.md) — project context, device list, and architectural decisions
- [GLOSSARY.md](../GLOSSARY.md) — definitions for Teleport, Edge Agent, EMS, PCS, etc.
