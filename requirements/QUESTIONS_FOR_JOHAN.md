# Questions for Johan — Pre-Requirements Session

**Prepared by:** Marius Bloemhof  
**Date:** 2026-05-02 (refreshed for today's in-person session; original drafted 2026-03-31)  
**Purpose:** Close remaining unknowns before writing formal product requirements (PRD).

Questions are grouped by topic and ordered by architectural impact — the first two sections have the highest downstream consequences and should be covered first. Sections in **bold** below are the ones most likely to reshape the architecture or billing engine; everything else is configuration detail that can be deferred if time runs short.

> **Recommended running order:** A → B → C → D → E → F. Aim to leave A1 (PPC) and B2/B3 (billing flows + tariff) settled before the session ends — these are the only items that can stall the PRD.

---

## A. Grid & Compliance *(Highest priority — answers could change the control architecture)*

### A1. PPC — what is it, who owns it?
*This is the single most impactful unknown in the entire system.*

- What is the make and model of the PPC (Power Plant Controller) on your sites?
- Who supplied and installed it — your EPC contractor, the utility, or a specialist?
- Is it utility-mandated as part of the grid connection agreement, or did your team choose it?
- Does it have a northbound interface your team can access? (i.e., can we send it setpoints, or can we only read from it?)
- Is the same PPC model deployed across all sites, or does it vary?

> **Why it matters:** If the PPC is the master aggregator and exposes a single control interface, our cloud system sends all setpoints to one endpoint rather than to SmartLogger, Sinexcel, and EPC CAB1000 individually. This could collapse the control architecture significantly. If the PPC is utility-owned and locked, we need to know exactly what commands we're allowed to send.

---

### A2. Grid connection agreements
- Do your sites operate under formal grid connection agreements with Eskom or a municipality?
- Do those agreements include curtailment obligations? (i.e., can the grid operator instruct you to reduce output remotely?)
- Are there active power export limits at the point of common coupling?

---

### A3. Regulatory / reporting obligations
- Are there any NERSA licence conditions or municipal reporting requirements for the energy data?
- Does any third party (utility, auditor, insurance, finance provider) require access to the generation or storage data?
- What is the minimum retention period for billing and metering records? (Accounting legislation, contractual requirements?)

---

## B. Commercial Model & Billing *(Defines the entire billing engine)*

### B1. What exactly is the commercial arrangement with clients?
- Is the model: Johan owns the equipment and rents it to the client? Energy-as-a-service (client buys kWh)? Both, depending on client?
- What does a typical contract look like in one sentence?

### B2. What energy flows are invoiced?
- Is the client billed for energy **imported from the grid** through the meter?
- Is the client billed for energy **discharged from the battery** (Johan's asset)?
- Is the client billed for **PV generation** (self-consumption credit, net metering)?
- Or is it a fixed monthly rental + consumption above a threshold?

> **Why it matters:** This directly determines which Acuvim L registers feed the billing engine. The meter captures all flows separately; we need to know which ones appear on an invoice.

### B3. Tariff structure
- Is billing at a **flat rate** per kWh, or does it use **time-of-use (TOU)** with peak/off-peak/standard bands?
- Is there a **maximum demand charge** — a fee based on the highest 15-minute power demand in the billing period?
- Are there any **seasonal rate variations** (summer vs. winter)?

> **Why it matters:** The Acuvim L already supports all of this natively (TOU with 4 tariffs × 12 seasons × 14 schedules). We just need to configure it correctly and match the billing engine logic to the same bands.

### B4. Billing period and invoicing process
- Is billing monthly or quarterly?
- Does Johan want invoices **auto-generated and emailed** to the client at period end, or does the finance team review and approve before sending?
- What accounting system does Johan use? (Xero, Sage, QuickBooks, other?) — determines the export format for invoice line items.
- Are clients invoiced **per site** or **per organisation** (one invoice if a client has multiple sites)?
- Is invoicing always in **ZAR**, or are any clients invoiced in another currency?
- Is **VAT** applied on the invoice (15% SA standard), and is it line-item or total-only?
- What are the **payment terms** (e.g. 30 days from issue) and how are arrears handled?

### B5. Sub-metering — can one site have multiple billing meters?
- Is there ever a case where a single site is **sub-metered** for multiple tenants or cost centres (e.g. an industrial park where each tenant gets a separate invoice from the same Acuvim L installation, or multiple Acuvim L meters at one site)?
- If yes, how is the relationship between meter and tenant currently tracked?

> **Why it matters:** The data model currently assumes one `BillingMeter` per `Site`. If sub-metering exists we need a `Site → Tenant → Meter` relationship instead, which changes contract structure and the client portal scoping.

### B6. Non-payment / cut-off policy
- If a client falls into arrears, is **disconnect-on-non-payment** part of the commercial agreement?
- If yes, is it executed **manually** by an operator, or should the platform support **automated cut-off** (e.g. open the grid breaker / send a stop command after N days arrears)?
- Are there any commands that should be **explicitly blocked** for clients in dispute (no remote control changes until resolved)?

> **Why it matters:** Automated cut-off is a high-impact control feature with regulatory and liability consequences. Better to know now whether it's in scope at all.

---

## C. Sites & Infrastructure *(Needed for edge agent deployment planning)*

### C1. Site count and rollout
- How many sites are currently live?
- How many are planned in the next 6 months? 12 months?
- Are all live sites structurally similar (same device mix), or are there significant variations?
- Do the two SLD diagrams (SLD1 and SLD2) represent the two main site archetypes, or are there others?

### C2. Edge hardware
- What hardware currently exists at each site that could host the edge agent? (Industrial PC, existing SCADA box, Raspberry Pi, router with compute capability like Teltonika?)
- Or does new edge hardware need to be procured? If so, is there a preferred vendor/form factor?
- Is there a site operations team who manages on-site hardware, or is everything managed remotely?

### C3. Site network
- What is the internet connectivity at each site? (Fibre only? Fibre + LTE failover? LTE only?)
- Is there an existing IT/OT network segregation — are the devices on an isolated LAN, or on the same network as office IT?
- Is there a VPN in place, or will the edge agent communicate with the cloud over the open internet (with TLS)?
- Do the MOXA NPort gateways have fixed IP addresses on the site LAN?

### C4. Device inventory confirmation
- What are the **MOXA NPort model numbers** deployed? (Likely on the site documentation / SLD drawings — model is usually on the device label.)
- What is the **Sinexcel PWS1-500K firmware version** on installed units? (Visible on the HMI touch screen under Settings > About.) — relevant because firmware v1517 (DEIF release) shifted some voltage/frequency register addresses.
- Can we get **remote or physical access to one EPC Power CAB1000** to run a tool against it and download the register definitions? (The public datasheet doesn't list register addresses; we either need the Eaton xStorage I/O manual P-164001236 or to run `get-models.py` from `epcpower/sunspec-demo` against a live unit.)
- Are the **Sungrow MBB units** (from SLD2) deployed at multiple sites or just one? What is the exact Sungrow model?
- Are there **Schneider PM3255 or PM5000** variants deployed at any sites, or is it exclusively PM5110?
- What is the **Lantronix gateway model** in front of the EPC CAB1000? (Needed for serial-to-Ethernet config.)

### C5. Site timezones and locations
- All sites currently in South Africa (timezone `Africa/Johannesburg`)? Any sites planned outside SA?
- Is there a likelihood of sites in **other African markets or beyond** in the next 12-24 months?

> **Why it matters:** Billing periods, TOU tariff schedules, and 15-minute energy intervals are all timezone-anchored. Multi-timezone support is cheap if designed in from day one but expensive to retrofit.

---

## D. Operations & Alerting

### D1. Who monitors the sites operationally?
- Is there a dedicated operations/NOC team, or does Johan and a small team handle this?
- What hours do they need to be reachable for critical alerts? (24/7 or business hours?)
- What notification channels should alerts use? (Email, SMS, WhatsApp, Teams/Slack?)

### D2. Escalation and severity
- What constitutes a **critical alert** that requires immediate response? (Battery fault? Generator fail to start? Site completely offline?)
- Are there alerts that should go to the client as well as the operations team?

### D3. Remote control permissions
- Should remote control (power setpoints, mode switching, start/stop) require **two-person authorisation** — or is a single operator sufficient?
- Are there any control actions that should be **explicitly blocked** remotely and only possible on-site? (Emergency stops, for example.)
- Should the system enforce a **minimum SOC floor** to prevent batteries from being discharged below a safe threshold via remote command?

### D4. Service expectations for the platform itself
- What **availability target** should the cloud platform meet? (e.g. 99% / 99.5% / 99.9% — each is a different cost and operations posture.)
- What is the acceptable **data loss window** for billing data in a worst-case cloud failure? (RPO — recovery point objective.)
- What is the acceptable **outage length** before the operations team must be notified vs. credited? (RTO — recovery time objective.)
- Does the platform need to survive a **full cloud-region outage** in v1, or is single-region acceptable initially?

> **Why it matters:** "Always available" vs. "best effort" implies a 5-10× cost difference in cloud infrastructure and on-call burden. Better to define this explicitly than over-engineer.

---

## E. Client Portal

### E1. What do clients need to see?
- Beyond usage summary and invoice history, what else does the client portal need to show?
  - Live generation (PV output right now)?
  - Battery state (SOC, charging/discharging)?
  - Savings vs. grid-only baseline?
  - CO₂ offset / environmental metrics?
- Is the portal for the client's **finance team** (billing focus), their **facilities manager** (operational focus), or both?

### E2. Client onboarding
- How does a new client get access? Does Johan's team create accounts manually, or should clients be able to self-register?
- Should clients be able to see **historical data from before** they got portal access? (i.e., data back-dated to site commissioning date?)

### E3. Branding
- Should the client portal be **white-labelled** under Johan's company brand, or a neutral "Solar Monitor" brand?
- Do individual clients get a branded subdomain (e.g., `clientname.johanssystem.co.za`)?

---

## F. Existing Systems & References

### F1. Current state
- Is there any existing monitoring system in place at any sites — even a basic one? What is it and what does it do?
- Are there any current pain points or incidents that this platform must specifically address? (Data gaps, manual meter reading, billing disputes?)

### F2. Reference points
- Are there any competitor platforms or dashboards Johan has seen that he likes the look/feel of?
- Are there any that he specifically wants to avoid resembling?

---

## Answered (for reference)

| Question | Answer | Date |
|----------|--------|------|
| How many sites will there be? | 1-N; multi-site from day one | 2026-03-31 |
| Do clients get a portal? | Yes — two tiers: Operations (full) and Client (aggregated read-only + billing) | 2026-03-31 |
| Dashboard data refresh rate? | 5 min default; configurable; minimum floor ~30 s | 2026-03-31 |
