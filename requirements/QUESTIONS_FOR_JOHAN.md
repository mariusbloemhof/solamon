# Questions for Johan — Pre-Requirements Session

**Prepared by:** Marius Bloemhof  
**Date:** 2026-03-31  
**Purpose:** Close remaining unknowns before writing formal product requirements (PRD). Suggested as a structured 60-minute session.

Questions are grouped by topic and ordered by architectural impact — the first two sections have the highest downstream consequences and should be covered first.

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
- What is the **Sinexcel PWS1-500K firmware version** on installed units? (Visible on the HMI touch screen under Settings > About.)
- Can we get **remote or physical access to one EPC Power CAB1000** to run a tool against it and download the register definitions?
- Are the **Sungrow MBB units** (from SLD2) deployed at multiple sites or just one? What is the exact Sungrow model?
- Are there **Schneider PM3255 or PM5000** variants deployed at any sites, or is it exclusively PM5110?

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
