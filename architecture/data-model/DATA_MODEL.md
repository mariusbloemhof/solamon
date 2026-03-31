# Solar Monitor — Data Model

**Version:** 0.1 (draft — pre-PRD)  
**Author:** Marius Bloemhof  
**Date:** 2026-03-31  
**Status:** Working draft. Storage layer is TimescaleDB (PostgreSQL + time-series extension). Schema notation is conceptual — column types will be finalised during implementation.

---

## 1. Entity Overview

```
Organisation
    └── Site  (1:N)
         ├── Device  (1:N)
         │    └── Reading  (1:N timeseries)
         ├── BillingMeter  (1:1 or 1:N — Acuvim L)
         │    └── EnergyInterval  (1:N timeseries)
         └── Contract  (1:N)
              └── Invoice  (1:N)
                   └── InvoiceLine  (1:N)

User
    └── SiteAccess  (M:N via Site)

ControlCommand  (linked to Device + User)
Alert           (linked to Device + AlertRule)
AlertRule       (linked to Site or Device)
AuditEntry      (append-only log)
```

---

## 2. Core Entities

### Organisation

Represents Johan's business entity (or a client company in multi-tenancy).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `name` | text | — |
| `slug` | text unique | URL-safe identifier |
| `billing_contact_email` | text | — |
| `created_at` | timestamptz | — |

### Site

A physical installation location. One edge agent per site.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `organisation_id` | UUID FK | Owner organisation |
| `name` | text | Human-readable name (e.g. "Pretoria North Plant") |
| `slug` | text unique | Used in MQTT topic `solar/{slug}/...` |
| `location` | text | Address or GPS coordinates |
| `timezone` | text | IANA tz (e.g. "Africa/Johannesburg") — critical for billing periods |
| `grid_connection_kw` | numeric | Contracted grid capacity |
| `is_active` | boolean | Soft disable without deleting |
| `created_at` | timestamptz | — |

### DeviceType

Catalogue of known device types with protocol metadata.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `manufacturer` | text | e.g. "Huawei", "Sinexcel", "AccuEnergy" |
| `model` | text | e.g. "SmartLogger V300R024", "PWS1-500K" |
| `category` | enum | `pv_inverter`, `bess_inverter`, `bess_hub`, `meter`, `generator`, `ppc`, `gateway` |
| `protocol` | enum | `modbus_tcp`, `mqtt`, `http_push`, `modbus_rtu` |
| `default_port` | int | — |
| `default_unit_id` | int | Modbus unit/slave ID |
| `register_profile_id` | UUID FK | → RegisterProfile (see section 6) |
| `notes` | text | — |

### Device

A specific physical device installed at a site.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `site_id` | UUID FK | — |
| `device_type_id` | UUID FK | — |
| `name` | text | Human label (e.g. "SmartLogger Main", "Sinexcel PCS 1") |
| `host` | text | IP address or hostname on site LAN |
| `port` | int | Default from DeviceType, overridable |
| `unit_id` | int | Modbus unit/slave ID |
| `is_billing_source` | boolean | True only for revenue-grade meters (Acuvim L) |
| `is_controllable` | boolean | True for PCS, generator controller |
| `poll_interval_seconds` | int | Override per device; null = use DeviceType default |
| `last_seen_at` | timestamptz | Updated on every successful read |
| `status` | enum | `online`, `offline`, `unreachable`, `fault`, `unknown` |
| `firmware_version` | text | Populated from device identity registers at startup |
| `serial_number` | text | — |
| `commissioned_at` | date | — |
| `decommissioned_at` | date | Null = still active |

---

## 3. Telemetry

### Metric

Catalogue of all measurable quantities. Defines the semantic meaning of a reading.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `device_type_id` | UUID FK | Scope: this metric applies to this device type |
| `key` | text | Machine key, e.g. `ac_power_kw`, `soc_pct`, `grid_frequency_hz` |
| `label` | text | Human label, e.g. "AC Active Power" |
| `unit` | text | SI unit string, e.g. `kW`, `%`, `Hz`, `°C`, `kWh` |
| `data_type` | enum | `float`, `int`, `bool`, `enum`, `bitfield` |
| `is_cumulative` | boolean | True for energy counters (kWh); false for instantaneous values |
| `direction_convention` | text | e.g. "positive=discharge, negative=charge" (device-specific) |
| `register_address` | int | Source Modbus register (informational; actual mapping in RegisterProfile) |

### Reading *(time-series table)*

All telemetry values from all devices. Primary time-series table — high write volume, time-range queries.

| Column | Type | Notes |
|--------|------|-------|
| `time` | timestamptz | **Partition key** (TimescaleDB hypertable) |
| `device_id` | UUID | — |
| `metric_key` | text | Matches `Metric.key` |
| `value` | double precision | Normalised value in the metric's unit |
| `raw_value` | int | Raw Modbus register value before scaling |
| `quality` | enum | `good`, `uncertain`, `bad` — set by edge agent |

**Indices:** `(device_id, metric_key, time DESC)` — covers all standard dashboard and billing queries.

**Retention:** Raw readings retained 90 days. Downsampled aggregates (1-min, 15-min, 1-hour) retained 7 years for regulatory/billing. *(❓ confirm retention period with Johan / legal.)*

**TimescaleDB continuous aggregates (automatic):**
- `reading_1min` — per device per metric, 1-minute OHLC + avg
- `reading_15min` — 15-minute avg (feeds billing intervals)
- `reading_1hour` — hourly avg + min + max (feeds dashboard history)

### DeviceSnapshot

Latest state per device — updated on every successful poll. Used for dashboard "current status" without querying the time-series.

| Column | Type | Notes |
|--------|------|-------|
| `device_id` | UUID PK | — |
| `snapshot_time` | timestamptz | Time of last successful read |
| `metrics` | jsonb | `{metric_key: value, ...}` — all metrics from last poll cycle |
| `operating_state` | text | Device-specific state string |
| `active_faults` | jsonb | Array of active fault codes/descriptions |

---

## 4. Billing

### BillingMeter

Identifies which device is the revenue-grade billing source for a site. Deliberately separate from the Device table to make billing data lineage explicit.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `site_id` | UUID FK | — |
| `device_id` | UUID FK | Must be a device with `is_billing_source = true` |
| `meter_serial` | text | Acuvim L serial number (for audit trail) |
| `active_from` | date | Start of this meter's billing authority at this site |
| `active_to` | date | Null = currently active |
| `notes` | text | Reason for any meter change |

### EnergyInterval *(time-series table)*

15-minute energy buckets from the Acuvim L. Immutable once written — corrections via EnergyAdjustment (see below), never overwrite.

| Column | Type | Notes |
|--------|------|-------|
| `time` | timestamptz | Start of 15-minute interval (**partition key**) |
| `billing_meter_id` | UUID | — |
| `import_wh` | bigint | Energy imported from grid in this interval (Wh) |
| `export_wh` | bigint | Energy exported to grid in this interval (Wh) |
| `generation_wh` | bigint | PV generation (if available from meter) |
| `battery_charge_wh` | bigint | Battery charged in interval |
| `battery_discharge_wh` | bigint | Battery discharged in interval |
| `source` | enum | `mqtt_push`, `modbus_poll`, `replay_cache` — tracks data origin |
| `received_at` | timestamptz | When cloud received this record |

> **Design note:** Wh (watt-hours) at 15-min granularity gives billing-grade precision. Acuvim L reports at 0.1 Wh resolution. Store as bigint (tenths of Wh) to avoid floating-point rounding.

### EnergyAdjustment

Immutable correction record when an EnergyInterval value needs correction (e.g. meter replacement, communication gap).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `energy_interval_time` | timestamptz | References the interval being corrected |
| `billing_meter_id` | UUID | — |
| `field` | text | Which field is corrected (e.g. `import_wh`) |
| `original_value` | bigint | — |
| `corrected_value` | bigint | — |
| `reason` | text | Required — explains the correction |
| `adjusted_by` | UUID FK | User who made the adjustment |
| `adjusted_at` | timestamptz | — |

### Contract

Commercial arrangement between Johan's company and a client for a specific site.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `site_id` | UUID FK | — |
| `client_organisation_id` | UUID FK | — |
| `contract_ref` | text | External contract number |
| `billing_period` | enum | `monthly`, `quarterly` |
| `rate_structure` | enum | `flat`, `tou`, `demand` *(❓ confirm with Johan)* |
| `rate_config` | jsonb | Tariff parameters: flat rate per kWh, or TOU schedule |
| `currency` | char(3) | ISO 4217 (e.g. `ZAR`) |
| `valid_from` | date | — |
| `valid_to` | date | Null = open-ended |
| `notes` | text | — |

### Invoice

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `contract_id` | UUID FK | — |
| `period_start` | date | — |
| `period_end` | date | — |
| `status` | enum | `draft`, `issued`, `paid`, `disputed` |
| `total_amount` | numeric(12,2) | In contract currency |
| `issued_at` | timestamptz | — |
| `pdf_blob_key` | text | Path in blob store |
| `generated_by` | UUID FK | User or `system` for auto-generated |

### InvoiceLine

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `invoice_id` | UUID FK | — |
| `description` | text | e.g. "Energy import Jan 2026 — 08:00–20:00 (peak)" |
| `quantity_kwh` | numeric(12,3) | — |
| `rate` | numeric(10,4) | Per kWh |
| `amount` | numeric(12,2) | `quantity_kwh × rate` |
| `tariff_band` | text | `peak`, `off_peak`, `standard`, `flat` |

---

## 5. Control

### ControlCommand

Every command dispatched to a device, from any source, is recorded.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `device_id` | UUID FK | — |
| `issued_by` | UUID FK | User ID |
| `issued_at` | timestamptz | — |
| `command_type` | enum | `start`, `stop`, `set_power`, `set_mode`, `clear_fault`, `custom` |
| `parameters` | jsonb | e.g. `{"setpoint_kw": -200, "mode": "off_grid"}` |
| `status` | enum | `pending`, `sent`, `acknowledged`, `confirmed`, `failed`, `expired` |
| `sent_at` | timestamptz | When edge agent received command |
| `acknowledged_at` | timestamptz | When device responded |
| `confirmed_value` | jsonb | Read-back value from device after write |
| `error_message` | text | If status = failed |
| `expires_at` | timestamptz | Default: issued_at + 5 minutes |

### ControlPolicy *(future)*

Rules constraining what commands are permissible (e.g. never discharge below 20% SOC). Reserved for v2.

---

## 6. Alerting

### AlertRule

Configurable threshold rules evaluated against incoming telemetry.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `site_id` | UUID FK | Null = global rule |
| `device_type_id` | UUID FK | Null = all device types |
| `metric_key` | text | — |
| `condition` | enum | `above`, `below`, `equals`, `bit_set`, `device_offline` |
| `threshold` | double precision | — |
| `duration_seconds` | int | Condition must hold for this long before alert fires |
| `severity` | enum | `info`, `warning`, `critical` |
| `notification_channels` | jsonb | e.g. `["email:ops@company.com", "sms:+27..."]` |
| `is_active` | boolean | — |

### Alert

Fired alert instances.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `alert_rule_id` | UUID FK | — |
| `device_id` | UUID FK | — |
| `triggered_at` | timestamptz | — |
| `resolved_at` | timestamptz | Null = still active |
| `trigger_value` | double precision | The value that triggered the alert |
| `acknowledged_by` | UUID FK | User who ack'd |
| `acknowledged_at` | timestamptz | — |
| `notes` | text | Operator notes on resolution |

---

## 7. Users and Access

Two distinct user tiers exist with fundamentally different capabilities and data visibility.

### User

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `organisation_id` | UUID FK | — |
| `email` | text unique | — |
| `display_name` | text | — |
| `tier` | enum | `operations`, `client` — determines which API surface is accessible |
| `role` | enum | `admin`, `operator`, `viewer`, `billing` — applies within tier |
| `is_active` | boolean | — |
| `last_login_at` | timestamptz | — |

**Tier definitions:**

| Tier | Who | Data access | Control access |
|------|-----|-------------|---------------|
| `operations` | Johan's team | All raw readings, device state, billing detail, admin | Full — mode switching, setpoints, start/stop |
| `client` | Johan's customers | Aggregated usage summaries and invoice data for their contract only | None |

### SiteAccess

Grants a user access to a specific site. Operations users are typically granted via their organisation. Client users are granted via their contract.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK | — |
| `site_id` | UUID FK | — |
| `access_level` | enum | `view`, `operate`, `admin` — only meaningful for `operations` tier; clients are always `view` |
| `granted_by` | UUID FK | — |
| `granted_at` | timestamptz | — |

### ClientUsageSummary *(materialised view)*

Pre-aggregated view of energy usage per contract per period. This is what the client portal API serves — clients never query `Reading` directly.

| Column | Type | Notes |
|--------|------|-------|
| `contract_id` | UUID | — |
| `period_start` | date | — |
| `period_end` | date | — |
| `total_import_kwh` | numeric | Aggregated from EnergyInterval |
| `total_export_kwh` | numeric | — |
| `total_generation_kwh` | numeric | — |
| `peak_demand_kw` | numeric | Maximum 15-min demand in period |
| `refreshed_at` | timestamptz | When this summary was last recalculated |

This materialised view is recalculated nightly and on-demand when new EnergyInterval data arrives. The client portal reads only from this view — no joins to raw telemetry.

---

## 8. Audit Log

Append-only record of all significant actions. Never deleted, never updated.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `time` | timestamptz | — |
| `actor_id` | UUID | User ID or `system` |
| `action` | text | e.g. `invoice.issued`, `device.command.sent`, `contract.updated` |
| `entity_type` | text | Table/entity name |
| `entity_id` | UUID | — |
| `before` | jsonb | State before (for updates) |
| `after` | jsonb | State after |
| `ip_address` | inet | — |

---

## 9. Storage Strategy

| Data | Store | Rationale |
|------|-------|-----------|
| `Reading` (telemetry) | TimescaleDB hypertable | Time-partitioned, compressed, continuous aggregates |
| `EnergyInterval` (billing) | TimescaleDB hypertable | Same DB — enables SQL JOIN to contract data |
| `DeviceSnapshot` (latest state) | PostgreSQL (relational) | Small table, frequent upsert, simple key lookup |
| All other entities | PostgreSQL (relational) | Standard CRUD |
| Raw MQTT payloads | Blob store (S3) | Audit trail; cheap storage; accessed rarely |
| Invoice PDFs | Blob store (S3) | Generated on-demand; stored by invoice ID |
| `AuditLog` | PostgreSQL (append-only) | Co-located with relational data; needs JOIN to users/entities |

**Single database, two schemas:** `timeseries` schema (TimescaleDB hypertables) + `app` schema (relational tables). This keeps the operational footprint minimal while allowing full SQL across both.

---

## 10. Retention Policy

| Data | Hot Retention | Archive | Delete |
|------|--------------|---------|--------|
| Raw readings (10-second) | 90 days | Compress in place (TimescaleDB) | 1 year |
| 1-min aggregates | 1 year | — | 3 years |
| 15-min aggregates | 7 years | — | On contract termination + 7 years |
| EnergyInterval | 7 years | — | Contractual minimum |
| Invoices + PDFs | 7 years | Blob archive | Legal retention |
| ControlCommand | 3 years | — | — |
| AuditLog | Indefinite | — | Never |

*(❓ Confirm retention periods with Johan — may be driven by NERSA or accounting regulations.)*

---

## 11. Open Questions

### Closed

| # | Question | Answer |
|---|----------|--------|
| 6 | Is the client portal in scope for v1? | Yes — two tiers: Operations (full access) and Client (aggregated usage + billing summary only; no raw telemetry, no control) |

### Pending (for Johan)

| # | Question | Impact |
|---|----------|--------|
| 1 | What energy flows are billed? (import only, or import + battery discharge?) | Determines which `EnergyInterval` columns are mandatory vs optional |
| 2 | Is billing flat-rate per kWh, or TOU with peak/off-peak bands? | Determines `rate_structure` in Contract and `tariff_band` in InvoiceLine |
| 3 | Are clients invoiced per site or per organisation? (one client, multiple sites?) | Drives Contract → Site cardinality |
| 4 | What are the legal data retention requirements for billing records? | Drives retention policy — NERSA or accounting regulations may mandate 5-7 years |
| 5 | Is there a demand charge component? (maximum kW peak per billing period?) | Adds `peak_demand_kw` to InvoiceLine; Acuvim L already captures this |
