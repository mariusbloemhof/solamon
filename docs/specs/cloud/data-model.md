# Cloud — data model

**Spec group:** [cloud](README.md)
**Linear:** [SOL-8](https://linear.app/solamon/issue/SOL-8)
**Machine artifact:** [`migrations/0001_initial.sql`](migrations/0001_initial.sql)

The Postgres + TimescaleDB schema for the MVP cloud. Two schemas: `app` (relational, source of truth for everything except telemetry) and `timeseries` (TimescaleDB hypertable for all device readings).

---

## 1. Tooling and versions

| Component | Version | Notes |
|-----------|---------|-------|
| Postgres | 16-alpine | Official Docker image |
| TimescaleDB extension | 2.14+ | Installed into the same DB |
| `pg_uuidv7` extension (optional) | latest | For sortable UUIDs; otherwise `gen_random_uuid()` from `pgcrypto` |
| Migration runner | Raw SQL files via `psql` for MVP; future migration to Alembic | One file per migration, numbered |

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- for gen_random_uuid()
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS timeseries;
```

## 2. Schema overview

```
app schema (relational, source of truth)
├── organisation
├── site                          (1:N from organisation)
├── device_type                   (catalogue, includes profile_yaml jsonb)
├── device                        (1:N from site)
├── logical_metric                (seeded from architecture/logical_metrics.yaml)
├── user                          (operations + future client tier)
├── site_access                   (M:N user × site)
├── control_command               (lifecycle: pending → sent → ... → confirmed/failed/expired)
├── audit_entry                   (append-only)
└── device_snapshot               (latest per device, jsonb keyed by logical_metric_key)

timeseries schema (TimescaleDB)
└── reading                       (hypertable, partition key = time)
```

## 3. Tables (overview)

Full DDL is in [`migrations/0001_initial.sql`](migrations/0001_initial.sql); this section covers the design choices.

### 3.1 `app.organisation`

The owner of one or more sites. MVP has exactly one row (Johan's company). Slug is URL-safe and used in API paths only if/when multi-tenancy comes online.

### 3.2 `app.site`

A physical installation. **`slug` drives the MQTT topic prefix** (`solamon/{slug}/...`) and the URL path — must be lowercase, alphanumeric + hyphens, unique across the system. **`timezone`** defaults to `Africa/Johannesburg` per main spec §15; critical for billing periods (post-MVP) but already correct for the load assessment KPIs that bucket on day boundaries. **Timezone is validated at the application layer** (Pydantic against `zoneinfo.available_timezones()`) — a Postgres `CHECK` against `pg_timezone_names` would require an immutable function which doesn't exist; an enforcement trigger is overkill for MVP.

**`last_seen_at`** is updated on every heartbeat arrival (per-Pi liveness signal). Per-device liveness comes from `app.device.last_seen_at` (updated on every telemetry message arrival).

`mqtt_username` and `mqtt_password` columns hold the MVP per-site credentials served to the Pi at `GET /edge/config/{site_slug}`. Plaintext password is acceptable in MVP — **but only because DB access is admin-only AND the same posture extends to backups**: S3 backup buckets MUST have SSE-S3 encryption-at-rest enabled and IAM-restricted access. See §7. Future migration to AWS IoT Core uses mTLS device certificates and these columns become unused.

### 3.3 `app.device_type`

Catalogue of device variants we support. **`profile_yaml`** is the parsed-from-YAML profile stored as JSONB — seeded from `architecture/profiles/<slug>.yaml` at deploy time. The `profile_slug` matches the YAML filename (without extension) so cross-referencing is obvious.

For MVP this table has exactly one row (`acuvim_l`). Adding a new device variant = add a YAML file + add a row.

**Hex-notation gotcha:** YAML hex addresses (`address: 0x0600`) parse to integers and are stored as integers in JSONB. The original `0x` notation is lost in the round-trip. The edge agent reads integers and works correctly, but the future profile editor UI ([SOL-12](https://linear.app/solamon/issue/SOL-12)) needs to render integers as hex strings on display to preserve the human-readable form.

### 3.4 `app.device`

A specific physical device at a site. References `device_type` for "what kind of device" and stores instance-specific things: `host`, `port`, `unit_id`, `serial_number`, `firmware_version`, `sub_variant` (e.g., `CL`/`DL`/`EL`/`KL` for Acuvim L — captured from device label at commissioning since it's not on the wire). `is_billing_source` flags revenue-grade meters (deferred to billing scope but the column exists). `is_controllable` allows / denies control writes as a defence-in-depth on top of the profile's `control:` block.

`status` is a denormalised view of recent edge-agent reports — `online | offline | unreachable | fault | unknown`. Updated by the heartbeat handler in the ingestion worker. The authoritative liveness signal is the timestamp of the most recent heartbeat.

### 3.5 `app.logical_metric`

Reference data — every metric the platform recognises. Seeded from `architecture/logical_metrics.yaml` at deploy time. The `Reading` hypertable's `logical_metric_key` column foreign-keys here, ensuring every stored reading references a known metric.

**Numeric vs non-numeric routing:** the catalog includes metrics with `data_type` of `enum`, `datetime`, `string`, `bool`, and `bitfield` — these CANNOT be stored in `timeseries.reading` (which has only a `value DOUBLE PRECISION` column). The ingestion worker routes them to `app.device_snapshot.metrics` (JSONB) only. They are config-like and low-volume (read at startup or hourly, not at the 10s telemetry cadence), so a hypertable is the wrong storage for them anyway. See [`ingestion-worker.md`](ingestion-worker.md) §4 for the routing rule.

**Enum keys as strings:** `enum_values JSONB` stores keys as strings (JSON requirement) even though the wire data is integers (e.g., Acuvim's `76 → "inductive"`). Code comparing integer Modbus reads against the JSONB map must coerce to string first.

### 3.6 `app.users`

Single shared admin in MVP. `tier` (`operations`/`client`) and `role` columns exist now even though only `operations`/`admin` are populated, so the multi-user path doesn't require a schema migration later. `password_hash` is bcrypt; salt is embedded in the hash.

**Naming:** the table is `app.users` (plural), not `app."user"`. Postgres reserves `user` as a SQL keyword — the quoted form works but every query needs the quotes. Plural form is idiomatic and quote-free.

### 3.7 `app.site_access`

M:N junction. Default `access_level=admin` for the MVP user. Exists for the inevitable moment we add multi-user RBAC.

### 3.8 `app.control_command`

The full state machine of every control command. **Status enum:** `pending → sent → confirmed | failed | expired`. Transitions are tracked with timestamps and an `audit_entry` row is written on every transition.

The intermediate `acknowledged` state from earlier drafts was dropped for MVP simplicity — the Pi publishes only terminal acks (`confirmed`/`failed`), and the operator UI shows `sent` until that arrives (typically within 1-2 s). If diagnostic visibility into the Pi-side validation step becomes useful later, `acknowledged` can be re-added without a schema change (the column already accommodates the value via the CHECK constraint update).

`logical_metric_key` references `app.logical_metric(key)`; the parameter values are stored as `parameters` JSONB; the read-back value as `confirmed_value` JSONB. `expires_at` defaults to `issued_at + 5 minutes` per main spec §10.

**`last_publish_error`** holds the most recent MQTT publish failure reason — populated when the issuer's bounded retry exhausts; cleared on a subsequent successful retry. Surfaced in the API response so the web UI can prompt re-issue immediately rather than wait 5 min for the TTL reaper.

**Late ack handling:** a Pi ack arriving after `status='expired'` writes an `audit_entry` with `action='command.late_ack'` (capturing the `confirmed_value` from the late ack) but does NOT change the command status. Operator manually reconciles via the audit trail.

Indexed on `(device_id, issued_at DESC)` for the operator's audit list query, and a partial index on `expires_at WHERE status IN ('pending', 'sent')` for the TTL-reaper background task.

**Cleanup:** retention policy of 3 years per [`DATA_MODEL.md`](../../../architecture/data-model/DATA_MODEL.md) §10. App-level periodic sweep deletes rows past retention; see §5 below.

### 3.9 `app.audit_entry`

Append-only audit log. Every meaningful action (login, command issue, command transition, config change) writes a row. `before` / `after` JSONB columns capture state for updates. Indexed on `(time DESC)` and `(entity_type, entity_id)` for "what happened to this device?" queries.

Never deleted (per [`DATA_MODEL.md`](../../../architecture/data-model/DATA_MODEL.md) §10 retention table).

### 3.10 `app.device_snapshot`

Latest values per device. `metrics` is a JSONB map keyed by logical metric name. Updated by the ingestion worker on every reading. Used by the dashboard's "current state" panels — fast key-lookup, no time-series scan needed.

```sql
-- typical query the dashboard issues
SELECT metrics, snapshot_time, operating_state
FROM app.device_snapshot WHERE device_id = $1;
```

**`snapshot_time` semantic:** the timestamp of the **most-recent message** that updated this row. Individual metrics inside `metrics` may be older — for example, an `import_active_energy_kwh` value (60 s cadence) may be 50 s older than the `snapshot_time` (set by a 10 s `realtime` message that arrived in between). This is acceptable for MVP — a per-metric `last_updated_at` timestamp inside the JSONB is post-MVP polish if anyone needs it.

**JSONB merge shape:** the upsert merges `metrics || EXCLUDED.metrics` (shallow merge). All current metric values are flat scalars (number / string / null) so this is correct. A future shape that nests values (e.g., `{ "value": 12.35, "quality": "good" }`) would require a deeper merge or an explicit per-key update — flag for awareness when SOL-23 (derived metrics) lands.

### 3.11 `timeseries.reading` (hypertable)

The hot path. **Every NUMERIC telemetry reading** lands here. Non-numeric metrics (`enum`, `datetime`, `string`, `bool`, `bitfield`) are NOT stored here — they go to `app.device_snapshot.metrics` only. See §3.5 for the routing rule.

Schema:

| Column | Type | Notes |
|--------|------|-------|
| `time` | timestamptz | Hypertable partition key. From the edge agent's reading timestamp (NOT the cloud receive time — see `received_at`). |
| `device_id` | uuid | FK to `app.device(id)`. |
| `logical_metric_key` | text | FK to `app.logical_metric(key)`. |
| `value` | double precision | Decoded value in the metric's catalog unit. NULL allowed for `bad`-quality readings. |
| `raw_value` | bigint | Pre-scaling Modbus register value. NULL for derived metrics. |
| `quality` | text | `good` / `uncertain` / `bad`. |
| `block_name` | text | Which read block this came from — useful for debugging missing-metric scenarios. |
| `received_at` | timestamptz | Cloud-receive timestamp. Defaults to `now()`; NULL allowed for backfilled / replayed rows from the Pi's local SQLite buffer. Useful for end-to-end-latency dashboards and clock-skew debugging. |

**Hypertable config:**

```sql
SELECT create_hypertable('timeseries.reading', 'time', chunk_time_interval => INTERVAL '1 day');
```

One chunk per day. At ~1.7M rows/week per device that's roughly 240k rows/chunk — well within Timescale's "1M rows per chunk" sweet spot.

**Primary index:**

```sql
CREATE INDEX idx_reading_device_metric_time ON timeseries.reading (device_id, logical_metric_key, time DESC);
```

This covers the dashboard's "give me the last N hours of `active_power_total` for device X" pattern. The natural ordering is per-(device, metric) descending time.

**No primary key** on the table — Timescale supports unique constraints on hypertables but only when including the partition column (`time`). For idempotency we use the index above as a uniqueness reference and `ON CONFLICT DO NOTHING` handles dedup at insert time. (Actual `(time, device_id, logical_metric_key)` UNIQUE constraint is added in 0001 — see SQL migration.)

**FK considerations:** `device_id` and `logical_metric_key` are real FKs. They impose a per-insert validation cost. At MVP throughput (one device, ~3 readings/sec average) this is negligible. If we hit throughput problems later we drop the FK and validate at the ingestion worker — but not before measuring.

## 4. Retention & compression

| Data | MVP retention | Mechanism |
|------|--------------|-----------|
| Raw readings (`timeseries.reading`) | **90 days** | Drop chunks older than 90 days via Timescale `add_retention_policy` (configured in 0001) |
| Audit log (`app.audit_entry`) | indefinite | No retention — append-only |
| Control commands (`app.control_command`) | 3 years | App-level periodic sweep — see §5 |
| Dead letter (`app.dead_letter`) | 30 days | App-level periodic sweep — see §5 |
| Snapshots (`app.device_snapshot`) | latest only | Upsert; no growth |

**No compression in MVP.** Timescale compression is a follow-on for when the raw `Reading` table approaches a few hundred GB. At our cadence on one device, 90 days of raw readings is ~1 GB — irrelevant.

**No continuous aggregates in MVP.** 1-min / 15-min / 1-hour rollups become essential when the billing engine queries 7-year-old energy intervals — that's post-MVP. For now, dashboard queries against raw readings are fine.

## 5. App-level retention sweeps

For tables that need cleanup beyond Timescale's chunk-drop, a **single periodic task in the FastAPI process** runs daily at 03:00 site-local:

```python
# Runs daily; see ingestion-worker.md §11 for the implementation.
async def retention_sweep():
    await db.execute("DELETE FROM app.dead_letter WHERE received_at < now() - INTERVAL '30 days'")
    await db.execute("DELETE FROM app.control_command WHERE issued_at < now() - INTERVAL '3 years'")
```

`pg_cron` was considered and rejected for MVP — it requires the extension and an additional operational moving piece. App-level cron is sufficient at single-tenant scale. Move to `pg_cron` (or AWS EventBridge) when we go multi-tenant.

## 6. Migration strategy

- **MVP**: raw SQL files in `migrations/`, numbered `0001_`, `0002_`, etc. Applied in order by `psql -f` from the cloud bootstrap script. State tracked in a `app.schema_migrations` table (file name + applied_at).
- **Production migration to Alembic** (post-MVP): Alembic-managed migrations in the implementation directory; first Alembic migration imports the SQL files and stamps the head; subsequent changes use Alembic's autogenerate.

The 0001 migration is **idempotent** — `CREATE EXTENSION IF NOT EXISTS`, `CREATE SCHEMA IF NOT EXISTS`, etc. — so re-running it on an existing DB is safe.

## 7. Seed data

After 0001 runs, a separate seed step (Python script `seed_reference_data.py`) runs:

1. Parse `architecture/logical_metrics.yaml` → insert all rows into `app.logical_metric`.
2. Parse every `architecture/profiles/*.yaml` → insert one `app.device_type` row per profile, with the YAML stored as `profile_yaml` JSONB.
3. Insert one `app.organisation` (Johan's company), one `app.site` (the bench), one `app.device` (the Acuvim L), one `app.users` row (admin), one `app.site_access`.

The seed script is idempotent (uses `ON CONFLICT DO NOTHING` everywhere) so re-running it is safe.

## 8. Backups

Daily `pg_dump -Fc` to S3 in `af-south-1` via cron in a backup sidecar container.

**TimescaleDB-specific care:**

- Use the custom format (`-Fc`) — required for Timescale's `pg_restore` recipe.
- After restoring on a fresh DB: `CREATE EXTENSION timescaledb;` first, then `SELECT timescaledb_pre_restore();`, then run `pg_restore`, then `SELECT timescaledb_post_restore();`. The pre/post wrappers handle hypertable chunk re-registration that vanilla `pg_restore` doesn't know about.
- See [TimescaleDB backup-and-restore docs](https://docs.timescale.com/self-hosted/latest/backup-and-restore/) for the full procedure.

**S3 bucket security (mandatory):**

- **SSE-S3** (Amazon-managed encryption-at-rest) enabled — default for new buckets in `af-south-1` since 2023.
- **Bucket policy restricted** to the cloud's IAM role + Marius's admin user only.
- **Public access block** enabled at the account level.

This is essential because `app.site.mqtt_password` is plaintext and lands in `pg_dump` output. Without these controls, the S3 bucket leak vector is identical to a DB compromise.

Retention: 30 days. **Restore tested** at least once during bench rehearsal Day 11-12 polish using the procedure above on a fresh container.

Logical replication / streaming replication / multi-AZ — all post-MVP.

## 9. Acceptance criteria

- `migrations/0001_initial.sql` runs cleanly on a fresh Postgres 16 + Timescale 2.14 container; produces all tables described above.
- `seed_reference_data.py` runs cleanly after the migration; populates `logical_metric`, `device_type`, and the MVP rows.
- Re-running both is idempotent.
- Cross-schema FKs from `timeseries.reading` to `app.device` and `app.logical_metric` are honoured (test: insert a Reading with bogus device_id should fail).
- Dashboard query `SELECT * FROM timeseries.reading WHERE device_id = $1 AND logical_metric_key = $2 ORDER BY time DESC LIMIT 100` runs in <50 ms on a 7-day data set.

## 10. Cross-references

- [`mqtt-contracts.md`](mqtt-contracts.md) — telemetry payloads that get unpacked into `Reading` rows
- [`ingestion-worker.md`](ingestion-worker.md) — the write-path code spec
- [`api-surface.md`](api-surface.md) — read-path queries
- [`../device-library/logical-metric-catalog.md`](../device-library/logical-metric-catalog.md) — definition of `logical_metric_key` values
- Main spec [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §6
- Original eventual-state data model: [`architecture/data-model/DATA_MODEL.md`](../../../architecture/data-model/DATA_MODEL.md) — the MVP subset implements §2-§3 + §5 + §7-§8 of that doc
