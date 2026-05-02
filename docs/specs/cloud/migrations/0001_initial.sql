-- Solamon — Cloud — Initial Postgres Schema
-- Spec: docs/specs/cloud/data-model.md
-- Linear: SOL-8
--
-- Idempotent: every CREATE uses IF NOT EXISTS where Postgres allows it.
-- Apply via:  psql -f 0001_initial.sql -d solamon
-- Reference data (logical_metric, device_type rows) is seeded by a
-- separate Python script (seed_reference_data.py) after this runs.

-- ─── Extensions and schemas ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;       -- gen_random_uuid()

CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS timeseries;

-- ─── Migration tracking ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.schema_migrations (
    filename     TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    -- TODO post-MVP: add `checksum TEXT` column when we move to Alembic
    -- so post-apply edits to migration files can be detected.
);

INSERT INTO app.schema_migrations (filename)
VALUES ('0001_initial.sql')
ON CONFLICT (filename) DO NOTHING;

-- ─── app.organisation ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.organisation (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  TEXT NOT NULL,
    slug                  TEXT NOT NULL UNIQUE,
    -- billing_contact_email reserved for the billing engine epic; unused in MVP.
    billing_contact_email TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── app.site ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.site (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id     UUID NOT NULL REFERENCES app.organisation(id),
    name                TEXT NOT NULL,
    slug                TEXT NOT NULL UNIQUE
                        CHECK (slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'),
    location            TEXT,
    -- timezone is validated at the application layer (Pydantic against
    -- pytz / zoneinfo). A CHECK against pg_timezone_names is not possible
    -- because pg_timezone_names is volatile.
    timezone            TEXT NOT NULL DEFAULT 'Africa/Johannesburg',
    grid_connection_kw  NUMERIC,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    last_seen_at        TIMESTAMPTZ,            -- updated by heartbeat handler

    -- MVP-only: per-site MQTT credentials served to the Pi at /edge/config.
    -- Plaintext password — DB-level access is admin-only in MVP.
    -- Backups (S3) MUST have SSE-S3 encryption-at-rest + restricted bucket
    -- access (see data-model.md §7).
    -- Migrates to mTLS device certificates when we move to AWS IoT Core.
    mqtt_username       TEXT NOT NULL UNIQUE,
    mqtt_password       TEXT NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_site_organisation ON app.site (organisation_id);

-- ─── app.device_type ───────────────────────────────────────────────────────
-- One row per supported device variant. profile_yaml is the parsed
-- architecture/profiles/<slug>.yaml file as JSONB.
--
-- Note: YAML hex addresses (0x0600) are stored as integers in JSONB. A future
-- profile editor UI (SOL-12) needs to render integer values as hex strings to
-- preserve the readable form humans use.
CREATE TABLE IF NOT EXISTS app.device_type (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    manufacturer    TEXT NOT NULL,
    model           TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN
                        ('meter', 'pv_inverter', 'bess_pcs', 'bess_hub',
                         'generator', 'ppc', 'gateway')),
    profile_slug    TEXT NOT NULL UNIQUE,            -- e.g. "acuvim_l"; matches YAML filename
    profile_yaml    JSONB NOT NULL,                  -- full parsed profile
    notes           TEXT,
    UNIQUE (manufacturer, model)
);

-- ─── app.device ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.device (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id              UUID NOT NULL REFERENCES app.site(id),
    device_type_id       UUID NOT NULL REFERENCES app.device_type(id),
    name                 TEXT NOT NULL,
    host                 TEXT NOT NULL,                -- IP or hostname on site LAN
    port                 INTEGER NOT NULL DEFAULT 502,
    unit_id              INTEGER NOT NULL DEFAULT 1,
    is_billing_source    BOOLEAN NOT NULL DEFAULT false,
    is_controllable      BOOLEAN NOT NULL DEFAULT true,
    -- last_seen_at is updated on every successful telemetry message arrival
    -- (not by heartbeats — heartbeats are per-Pi, not per-device).
    last_seen_at         TIMESTAMPTZ,
    -- status is updated by:
    --   - telemetry arrival → 'online' + last_seen_at = now()
    --   - stale-detector background task → 'offline' if no telemetry for >5min
    --   - explicit fault signals (TBD)
    status               TEXT NOT NULL DEFAULT 'unknown'
                          CHECK (status IN
                            ('online', 'offline', 'unreachable', 'fault', 'unknown')),
    firmware_version     TEXT,
    serial_number        TEXT,
    sub_variant          TEXT,                         -- e.g. "CL"/"DL"/"EL"/"KL" for Acuvim L
    commissioned_at      DATE,
    decommissioned_at    DATE,
    UNIQUE (site_id, name)
);

CREATE INDEX IF NOT EXISTS idx_device_site ON app.device (site_id);
CREATE INDEX IF NOT EXISTS idx_device_type ON app.device (device_type_id);

-- ─── app.logical_metric ────────────────────────────────────────────────────
-- Seeded from architecture/logical_metrics.yaml at deploy time.
--
-- Note: enum_values JSONB stores keys as strings (JSON requirement) even
-- though the wire data may be integers. The seed script and any code
-- comparing integer Modbus reads against the JSONB map must coerce to string.
CREATE TABLE IF NOT EXISTS app.logical_metric (
    key                    TEXT PRIMARY KEY
                            CHECK (key ~ '^[a-z][a-z0-9_]*$'),
    label                  TEXT NOT NULL,
    unit                   TEXT NOT NULL DEFAULT '',
    data_type              TEXT NOT NULL CHECK (data_type IN
                            ('float', 'int', 'bool', 'enum', 'bitfield', 'datetime', 'string')),
    category               TEXT NOT NULL,
    is_cumulative          BOOLEAN NOT NULL DEFAULT false,
    monotonic              BOOLEAN,
    direction_convention   TEXT,
    expected_range_min     DOUBLE PRECISION,
    expected_range_max     DOUBLE PRECISION,
    is_writable            BOOLEAN NOT NULL DEFAULT false,
    allowed_values         JSONB,
    enum_values            JSONB
);

-- ─── app.users ─────────────────────────────────────────────────────────────
-- Renamed from "user" to avoid the Postgres reserved-word quoting overhead.
CREATE TABLE IF NOT EXISTS app.users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id  UUID NOT NULL REFERENCES app.organisation(id),
    email            TEXT NOT NULL UNIQUE,
    display_name     TEXT NOT NULL,
    password_hash    TEXT NOT NULL,                    -- bcrypt
    tier             TEXT NOT NULL DEFAULT 'operations'
                      CHECK (tier IN ('operations', 'client')),
    role             TEXT NOT NULL DEFAULT 'operator'
                      CHECK (role IN ('admin', 'operator', 'viewer', 'billing')),
    is_active        BOOLEAN NOT NULL DEFAULT true,
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── app.site_access ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.site_access (
    user_id        UUID NOT NULL REFERENCES app.users(id),
    site_id        UUID NOT NULL REFERENCES app.site(id),
    access_level   TEXT NOT NULL DEFAULT 'view'
                    CHECK (access_level IN ('view', 'operate', 'admin')),
    granted_by     UUID REFERENCES app.users(id),
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_site_access_site ON app.site_access (site_id);

-- ─── app.control_command ───────────────────────────────────────────────────
-- State machine: pending → sent → confirmed | failed | expired
-- (The 'acknowledged' intermediate state was removed for MVP simplicity.
--  Pi publishes only confirmed/failed acks.)
--
-- Late-ack handling: if a Pi ack arrives after status='expired', the ack
-- is logged as an audit_entry with action='command.late_ack' but the
-- command status is NOT changed back. Operator manually reconciles via
-- the audit trail.
CREATE TABLE IF NOT EXISTS app.control_command (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id            UUID NOT NULL REFERENCES app.device(id),
    logical_metric_key   TEXT NOT NULL REFERENCES app.logical_metric(key),
    issued_by            UUID NOT NULL REFERENCES app.users(id),
    issued_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    parameters           JSONB NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN
                            ('pending', 'sent', 'confirmed', 'failed', 'expired')),
    sent_at              TIMESTAMPTZ,
    acknowledged_at      TIMESTAMPTZ,                -- preserved for back-compat; populated on terminal ack
    confirmed_value      JSONB,
    error_message        TEXT,
    last_publish_error   TEXT,                        -- populated when MQTT publish failed; cleared on retry success
    expires_at           TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_control_command_device_issued
    ON app.control_command (device_id, issued_at DESC);

-- Partial index for the TTL reaper background task — only scans active commands.
CREATE INDEX IF NOT EXISTS idx_control_command_pending_expires
    ON app.control_command (expires_at)
    WHERE status IN ('pending', 'sent');

-- ─── app.audit_entry ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app.audit_entry (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    time          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id      UUID REFERENCES app.users(id),     -- NULL for system actions
    action        TEXT NOT NULL,
    entity_type   TEXT NOT NULL,
    entity_id     UUID,
    before        JSONB,
    after         JSONB,
    ip_address    INET
);

CREATE INDEX IF NOT EXISTS idx_audit_entry_time ON app.audit_entry (time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entry_entity ON app.audit_entry (entity_type, entity_id);
-- TODO post-MVP: when audit-browser UI ships, add:
--   CREATE INDEX idx_audit_entry_actor_time ON app.audit_entry (actor_id, time DESC);

-- ─── app.device_snapshot ───────────────────────────────────────────────────
-- Latest values per device, keyed by logical metric name. Includes ALL
-- metrics — numeric AND non-numeric (datetime, enum, string, bool). The
-- snapshot is the authoritative store for non-numeric metrics; the
-- timeseries.reading hypertable holds numeric metrics only (see §3.11
-- in data-model.md).
--
-- snapshot_time is the timestamp of the most-recent message that updated
-- this row. Individual metrics inside `metrics` may be older — see
-- data-model.md §3.10 for the disambiguation note.
CREATE TABLE IF NOT EXISTS app.device_snapshot (
    device_id        UUID PRIMARY KEY REFERENCES app.device(id),
    snapshot_time    TIMESTAMPTZ NOT NULL,
    metrics          JSONB NOT NULL DEFAULT '{}',     -- { logical_metric_key: value }
    operating_state  TEXT,
    active_faults    JSONB
);

-- ─── app.dead_letter ───────────────────────────────────────────────────────
-- Failed MQTT messages (parse errors, schema violations, unknown devices).
-- Reviewed periodically by operators.
-- Cleanup: app-level periodic sweep deletes rows older than 30 days
-- (see ingestion-worker.md §11). pg_cron is not used in MVP.
CREATE TABLE IF NOT EXISTS app.dead_letter (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    payload      BYTEA NOT NULL,                      -- original payload, raw
    reason       TEXT NOT NULL,                       -- e.g. "parse-fail", "unknown-device"
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_received ON app.dead_letter (received_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- timeseries schema — TimescaleDB hypertables
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── timeseries.reading ────────────────────────────────────────────────────
-- Numeric metrics ONLY. Non-numeric metrics (datetime, enum, string, bool,
-- bitfield) are stored on app.device_snapshot.metrics and not duplicated
-- here — they're config-like, low volume, and the JSONB column is the
-- right home for them.
--
-- The ingestion worker enforces this routing; see ingestion-worker.md §4.
CREATE TABLE IF NOT EXISTS timeseries.reading (
    time                TIMESTAMPTZ NOT NULL,
    device_id           UUID NOT NULL REFERENCES app.device(id),
    logical_metric_key  TEXT NOT NULL REFERENCES app.logical_metric(key),
    value               DOUBLE PRECISION,
    raw_value           BIGINT,
    quality             TEXT NOT NULL DEFAULT 'good'
                         CHECK (quality IN ('good', 'uncertain', 'bad')),
    block_name          TEXT,
    received_at         TIMESTAMPTZ                  -- cloud-receive timestamp
                         DEFAULT now()                -- (NULL allowed for backfilled / replayed rows)
);

-- Convert to hypertable (idempotent — does nothing if already a hypertable).
SELECT create_hypertable(
    'timeseries.reading',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => true
);

-- Uniqueness for idempotent inserts. Timescale requires partition column in unique constraint.
-- block_name is included so that if a future profile ever maps the same logical
-- metric from two different read blocks (today's Acuvim L profile maps each metric
-- to exactly one block, but this isn't enforceable at the schema level), the two
-- streams don't dedup against each other. The Pi's local SQLite buffer uses the
-- same key for symmetry — see edge-agent/modbus-poller.md §4.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_unique
    ON timeseries.reading (time, device_id, logical_metric_key, block_name);

-- Primary access pattern: dashboard "give me the last N hours of metric X for device Y".
CREATE INDEX IF NOT EXISTS idx_reading_device_metric_time
    ON timeseries.reading (device_id, logical_metric_key, time DESC);

-- ─── Retention policy: drop chunks older than 90 days ──────────────────────
-- (Idempotent — TimescaleDB will reject a duplicate add_retention_policy with
-- if_not_exists.)
SELECT add_retention_policy(
    'timeseries.reading',
    INTERVAL '90 days',
    if_not_exists => true
);
