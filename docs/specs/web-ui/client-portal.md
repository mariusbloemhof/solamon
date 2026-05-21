# Web UI - Client Portal

**Spec group:** [web-ui](README.md)  
**Status:** Proposed MVP extension for the first client-facing review  
**Audience:** client stakeholders, site owners, non-technical decision makers  
**Primary route:** `/client/sites/{slug}`  
**Auth:** required; read-only client role or scoped client credentials

---

## 1. Product Intent

The client portal is not the operator dashboard with fewer buttons. It is a clean, read-only evidence view that answers:

1. Is Solamon receiving real data from my site right now?
2. What is my load profile doing over the last 24 hours?
3. Are voltage, current, and power quality inside acceptable operating ranges?
4. What should I care about from this measurement window?
5. Can I trust the numbers I am seeing?

The page should feel like an engineering-grade assessment report that happens to be live. It must be calm, precise, and confident. It should avoid internal implementation language such as MQTT, edge agent, fixture, command endpoint, BENCH_DEVICE_ID, or seeded device.

## 2. User Model

### 2.1 Client User

The first client-facing user is Johan or Johan's customer contact.

They are expected to know:

- site name and physical context;
- that a meter is installed;
- basic electrical concepts like kW, voltage, current, and peak demand.

They are not expected to know:

- Modbus register names;
- MQTT topic structure;
- device UUIDs;
- Solamon internal architecture;
- operator control workflows.

### 2.2 Permissions

Client users are read-only.

They can:

- view assigned sites;
- view live and historical readings;
- see data freshness and measurement status;
- export or print a one-page summary once that exists.

They cannot:

- issue control commands;
- view admin pages;
- see raw credentials, MQTT topics, device UUIDs, or internal logs;
- change device selection unless multiple client-visible meters are explicitly assigned to the same site.

## 3. Route Inventory

| Route | Purpose |
|---|---|
| `/client/login` | Client-specific sign-in screen. Uses the same backend auth endpoint, but with client-facing copy and redirect target. |
| `/client` | Redirect to the first assigned client site. |
| `/client/sites/{slug}` | Client assessment dashboard. Primary view. |
| `/client/sites/{slug}/print` | Later: printable/exportable summary. Not required for first MVP unless cheap. |

The existing operator routes remain:

- `/sites/{slug}` for Solamon/Johan operations;
- `/sites/{slug}/control` for commands;
- `/admin/*` for internal administration.

## 4. Information Architecture

The client page is a single scrollable page with four sections.

### 4.1 First Viewport - Live Assessment

The first viewport must answer "is this live, and what is happening?"

Layout:

```
Top bar
  Solamon mark / Client site name / Live status / Last received time

Assessment header
  Site name
  Measurement window: last 24 hours
  Meter label: human-readable serial or "Main incomer"
  Data status: Live / Delayed / No recent readings

KPI strip
  Current load
  Peak load today
  Average load
  Energy measured
  Power factor

Primary visual
  24h active power trace
```

Required first-viewport content on desktop:

- site name;
- live indicator;
- last reading timestamp, relative and absolute on hover;
- current active power in kW;
- 24h peak kW and time;
- 24h average kW;
- 24h active energy kWh;
- main 24h load chart with current point and peak marker.

On mobile:

- site name;
- live indicator;
- current load;
- peak load;
- chart visible after one short scroll.

### 4.2 Summary - What This Means

A plain-language summary sits directly below the chart.

Cards:

1. Load pattern
   - "Load was mostly idle overnight, then rose sharply from 06:45."
   - Computed from 24h series shape where possible.
2. Peak event
   - "Peak reached 592 kW at 08:14."
   - Always data-derived.
3. Operating quality
   - "Voltage is balanced and within expected range."
   - Uses voltage/current unbalance, frequency, and power factor.
4. Data confidence
   - "Live readings received 8 seconds ago. 8,526 samples in this 24h window."
   - Shows sample count, freshness, and missing-data gaps.

No card should invent a recommendation if the data is insufficient. Use "Not enough data yet" rather than filling space.

### 4.3 Electrical Detail

This section is for the client who wants proof.

Cards:

- Voltage per phase;
- Current per phase;
- Power factor;
- Frequency;
- Voltage unbalance;
- Current unbalance;
- Data freshness and sample completeness.

Each card must use client-readable labels:

- "L1", "L2", "L3" are acceptable;
- avoid "V1", "I1", "Psum_kW", "logical metric", "snapshot".

### 4.4 Site Context

This section explains what is being measured.

Fields:

- site name;
- meter label;
- meter model;
- serial number if available;
- measurement point, for example "Main incomer";
- reporting period;
- timezone;
- Solamon contact or support note.

Internal identifiers stay hidden by default. A support-only reveal can be added later behind an operator/admin role.

## 5. Visual Direction

The client portal should feel closer to a live engineering report than an operations console.

Use:

- white or very light neutral background;
- restrained borders;
- dense but breathable card layout;
- tabular numeric typography;
- strong chart legibility;
- small, precise labels;
- green only for good/live states;
- amber only for stale/warning states;
- red only for data loss or critical electrical state.

Avoid:

- marketing hero sections;
- decorative gradients;
- oversized slogans;
- internal side navigation;
- command/control affordances;
- excessive cards before the chart;
- showing UUIDs or topics.

Card radius should stay at 6px or less to match the current app direction.

## 6. Chart Contract

The load profile chart is the centrepiece.

### 6.1 Data

Default range:

- last 24 hours;
- metric: `active_power_total`;
- unit: kW;
- timezone: site timezone.

Data shown:

- active power trace;
- current/live point;
- 24h peak marker;
- 24h average line;
- optional expected/contracted threshold line if configured.

### 6.2 Interaction

Required for first client MVP:

- hover/tap tooltip with time and kW;
- current point labelled "Live now";
- peak point labelled "Peak";
- sample count displayed in chart chrome;
- empty/stale states handled in-chart.

Nice to have:

- 6h / 24h / 7d segmented range control;
- export PNG;
- print summary.

### 6.3 Tooltip Copy

Tooltip format:

```
10:45
525.0 kW
```

No raw metric names.

## 7. Client Login

Route: `/client/login`

The login page should be simpler and more polished than the current operator login.

Content:

- brand: "Solamon";
- heading: "Live Energy Assessment";
- subcopy: "Sign in to view your site assessment.";
- email field;
- password field;
- sign-in button;
- small trust line: "Read-only access. Measurement data updates as it arrives from site."

Do not show:

- demo login;
- fixture mode;
- API base override;
- admin/operator language.

After successful login:

- redirect to `/client` or `callbackUrl`;
- `/client` redirects to first assigned site.

## 8. Data Truth Rules

Client-facing data must be correct before it is pretty.

Rules:

1. Never render missing values as zero.
2. Always distinguish real zero load from missing data.
3. Show stale data clearly when the latest reading is older than 60 seconds.
4. Show "No recent readings" when latest reading is older than 5 minutes.
5. Show site timezone on chart labels or page metadata.
6. Use one decimal place for kW by default.
7. Use no more precision than the source data supports.
8. If sample count is low, show "Partial data window".
9. If the meter reports all-zero voltage/current, label the measurement state rather than implying normal operation.
10. If the backend is unreachable, show a polished service-unavailable state, not fixture data.

## 9. Copy Rules

Use client-facing language.

Preferred:

- "Live readings";
- "Last received";
- "Measurement window";
- "Current load";
- "Peak load";
- "Average load";
- "Energy measured";
- "Meter";
- "Site".

Avoid:

- "snapshot";
- "fixture";
- "edge";
- "MQTT";
- "poller";
- "device UUID";
- "logical metric";
- "BENCH_DEVICE_ID";
- "cloud API session";
- "command endpoint".

## 10. Empty, Stale, and Error States

### 10.1 Waiting For Data

When the client has access but no readings exist:

Title: "Waiting for first readings"

Body: "The site is configured, but Solamon has not received measurement data yet. This page will update automatically when readings arrive."

Show:

- site name;
- meter label if known;
- current connection status if known;
- support contact line.

### 10.2 Stale Data

When latest reading is older than 60 seconds:

- keep last values visible;
- add amber "Delayed" pill;
- show "Last received 2 min ago";
- chart remains visible.

When latest reading is older than 5 minutes:

- switch pill to "No recent readings";
- show short explanation above chart;
- do not hide the last known chart.

### 10.3 API Error

Show:

Title: "We could not load this assessment"

Body: "Please refresh. If the issue persists, contact Solamon support."

Include a small "Technical details" disclosure for support, collapsed by default.

## 11. API Needs

The client page can initially use existing endpoints:

- `POST /api/v1/auth/login`;
- `GET /api/v1/sites/{slug}`;
- `GET /api/v1/sites/{slug}/devices/{device_id}/snapshot`;
- `GET /api/v1/sites/{slug}/devices/{device_id}/readings?metric=active_power_total&from=...&to=...`.

Recommended near-term API additions:

1. Include client-safe meter identity:
   - display name;
   - serial number;
   - measurement point label.
2. Include site timezone consistently.
3. Add sample count and gap summary for readings responses.
4. Add optional configured demand/contract threshold for chart line.
5. Add role/scoping so a client account only sees assigned sites.

## 12. Implementation Shape

Recommended components:

| Component | Purpose |
|---|---|
| `ClientShell` | Minimal top bar, no side nav, no admin/control links. |
| `ClientLoginPage` | Client-specific sign-in page. |
| `ClientSitePage` | Data-loading route wrapper. |
| `ClientKpiStrip` | Current, peak, average, kWh, power factor. |
| `ClientLoadProfileChart` | 24h chart with live, peak, average, sample count. |
| `ClientInsightCards` | Plain-language assessment summary. |
| `ClientElectricalDetailGrid` | Voltage/current/power-quality cards. |
| `ClientDataConfidenceCard` | Freshness, sample count, gaps, data status. |

Route layout:

```
app/client/login/page.tsx
app/client/page.tsx
app/client/sites/[slug]/page.tsx
app/client/sites/[slug]/ClientSitePage.tsx
components/client/ClientShell.tsx
components/client/ClientLoadProfileChart.tsx
components/client/ClientKpiStrip.tsx
components/client/ClientInsightCards.tsx
components/client/ClientElectricalDetailGrid.tsx
```

## 13. Acceptance Criteria

The client portal is ready for Johan to show when:

1. A client can sign in without seeing operator/demo controls.
2. `/client/sites/bench` shows real cloud readings for the bench device.
3. The first viewport shows current load, peak load, average load, energy, live status, and a 24h chart.
4. The page never displays fixture data in production.
5. No internal IDs, MQTT topics, API base controls, or command controls are visible.
6. The chart clearly marks live, peak, and average values.
7. Stale data is obvious within 60 seconds of no readings.
8. The page looks polished at 1440x900, 1366x768, and a mobile viewport.
9. The page can be understood by a non-technical stakeholder in under 30 seconds.
10. Values match the operator dashboard/API for the same site and time window.

## 14. First Implementation Slice

Build this first:

1. `/client/login`;
2. `/client/sites/{slug}`;
3. read-only `ClientShell`;
4. KPI strip;
5. 24h load profile chart using existing readings endpoint;
6. electrical detail grid using existing snapshot endpoint;
7. stale/no-data states;
8. hide all operator/demo/internal affordances.

Leave print/export and multi-site client management for the next slice.

