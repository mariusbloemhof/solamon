# Cloud spec review — response

**Reviewed:** [`review-2026-05-02.md`](review-2026-05-02.md) — 33 findings (5 critical, 14 major, 14 minor)
**Author:** Marius (with Claude)
**Date:** 2026-05-02
**Status:** All findings addressed in this commit. Five judgment calls flagged.

Each finding was validated independently before applying a fix.

---

## Critical

### #1 — `value DOUBLE PRECISION` can't store enum/datetime/string metrics

**Validity:** Confirmed. `app.logical_metric.data_type` enumerates `bool, enum, bitfield, datetime, string`; the catalog has metrics in those types (`meter_clock`, `voltage_wiring_type`); the MQTT contract permits string values; the worker spec promised to handle them; the SQL had nowhere to put them.

**Resolution chosen — judgment call: route non-numeric to snapshot only, not widen Reading.** Reasoning:
- Non-numeric metrics are config-like and low-volume (read at startup or hourly, not at the 10 s telemetry cadence). A hypertable is the wrong storage shape for them.
- Widening `timeseries.reading` with nullable `value_text` / `value_time` columns adds row bloat to a high-volume table.
- A separate `timeseries.reading_event` table doubles the query surface for ~zero benefit.
- `app.device_snapshot.metrics` (JSONB) handles every type natively.

**Changes:**
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — added comment block on `timeseries.reading` documenting the policy.
- [`ingestion-worker.md`](ingestion-worker.md) §3.2 — explicit routing rule: numeric → hypertable + snapshot; non-numeric → snapshot only.
- [`data-model.md`](data-model.md) §3.5, §3.11 — same.

### #2 — Cloud → Pi command publish has no retry

**Validity:** Confirmed. Original flow caught `MqttError`, logged, and continued — the row stayed `pending` for 5 minutes until TTL.

**Resolution:**
- **Inside the request budget**: bounded retry (5 attempts, 100 ms-1 s backoff, 2 s total) before responding. If publish succeeds, `status='sent'` and 202.
- **Background retry task**: a 15-second-tick task picks up `status='pending'` rows and retries until `expires_at`.
- **`last_publish_error` column added** to `app.control_command` so the API surfaces the failure reason; web UI renders the error and lets the operator re-issue.
- **Response code semantics**:
  - 202 + `status='sent'` → publish succeeded
  - 202 + `status='pending'` + `last_publish_error` → transient publish failure; background retry running
  - 503 + `status='pending'` + `last_publish_error` → broker hard down

**Changes:**
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — added `last_publish_error` column.
- [`control-relay.md`](control-relay.md) §3.2 / §3.3 / §3.4 — full retry strategy + response semantics table.
- [`api-surface.md`](api-surface.md) §4.4 — documented response codes.
- [`openapi.yaml`](openapi.yaml) — added `last_publish_error` to `ControlCommand` schema.

### #3 — `mqtt_push` source enum value misrepresents AXM-WEB2

**Validity:** Confirmed. The current `solamon/{site}/telemetry/{device_id}` envelope assumes our payload shape; AXM-WEB2 has its own native shape (`{gateway, device, readings: [{name, value, unit}]}`). The `source: "mqtt_push"` placeholder couldn't actually be reached on the topic it was reserved for.

**Resolution:** removed `mqtt_push` from the `source` enum. AXM-WEB2 push gets its own topic + payload schema as part of [SOL-22](https://linear.app/solamon/issue/SOL-22) (push profile schema work).

**Changes:**
- [`mqtt-contracts.md`](mqtt-contracts.md) §4.2 + JSON Schema in §4.3 — enum reduced to `["modbus_poll", "replay_buffer"]`.

### #4 — Per-site heartbeat updates ALL devices to one status

**Validity:** Confirmed. The original SQL `UPDATE app.device SET status = $status WHERE site_id = (...)` would mass-update at multi-device-per-Pi time ([SOL-16](https://linear.app/solamon/issue/SOL-16)).

**Resolution:**
- Heartbeat handler now updates **`app.site.last_seen_at` ONLY**. No device update from heartbeats.
- Per-device `app.device.status` is updated by **telemetry arrival** (in the snapshot upsert): `status = 'online', last_seen_at = msg.timestamp`.
- Stale-device detector background task (every 60 s) marks devices `offline` when their `last_seen_at < now() - 5 min`.

This separation is correct for both single-device-per-Pi (today) and multi-device-per-Pi (SOL-16) — the heartbeat speaks for the Pi; per-device telemetry speaks for each device.

**Changes:**
- [`ingestion-worker.md`](ingestion-worker.md) §4.3 (snapshot upsert now also sets device status), §5 (heartbeat handler simplified), §5.1 (stale-device detector).
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `device.status` clarifies the two write paths.

### #5 — `/health` path mismatch

**Validity:** Confirmed. OpenAPI server URL is `/api/v1`, so `paths: /health` resolves to `/api/v1/health`. The spec text saying "/health" was inaccurate.

**Resolution:** standardised on `/api/v1/health`. Caddy doesn't need special routing.

**Changes:**
- [`api-surface.md`](api-surface.md) §4.7.
- [`openapi.yaml`](openapi.yaml) — `/health` (resolves to `/api/v1/health`) marked unauthenticated, comment added.

---

## Major

### #6 — WebSocket endpoints absent from OpenAPI artifact

**Validity:** Confirmed. OpenAPI 3.1 doesn't natively spec WS.

**Resolution chosen — judgment call: skip AsyncAPI; declare WS message envelopes in OpenAPI components for documentation.** Reasoning:
- AsyncAPI as a parallel doc means two contracts to keep in sync — overhead disproportionate to MVP value.
- Declaring `WSDeviceLiveMessage` and `WSCommandLiveMessage` in `components.schemas` gives the SDK reusable types even though the WS connections themselves are hand-wired.

**Changes:**
- [`openapi.yaml`](openapi.yaml) — added `WSDeviceLiveMessage` and `WSCommandLiveMessage` schemas with discriminators.
- [`api-surface.md`](api-surface.md) §8 — documented the OpenAPI ↔ WS gap and the schema-only approach.

### #7 — Snapshot upsert WHERE clause loses same-millisecond writes

**Validity:** Confirmed. `>` excludes equal timestamps; two messages from different blocks arriving in the same millisecond would lose the second.

**Resolution:** changed to `>=`. The JSONB merge handles overlap correctly.

**Changes:**
- [`ingestion-worker.md`](ingestion-worker.md) §4.3.

### #8 — JWT in WebSocket query string leaks to access logs

**Validity:** Confirmed. URLs end up in Caddy logs, browser history, proxy logs.

**Resolution:** removed the `?token=` option. JWT in `Sec-WebSocket-Protocol` header only.

**Changes:**
- [`api-surface.md`](api-surface.md) §5.1.

### #9 — Edge bootstrap chicken-egg on `site_slug`

**Validity:** Confirmed. The Pi needs `site_slug` and bearer token before the first `/edge/config/{slug}` call. They come from `bootstrap.yaml`, written at install time by `solamon-edge-install.sh`.

**Resolution:** added a "Bootstrap inputs to the Pi" paragraph at the top of api-surface.md §4.6 explaining the install-time provisioning and cross-referencing the (still-to-be-written) infrastructure spec.

**Changes:**
- [`api-surface.md`](api-surface.md) §4.6.

### #10 — Snapshot timestamp ambiguity

**Validity:** Confirmed. `snapshot_time` tracks the latest message; older-block values inside `metrics` get the newer timestamp.

**Resolution:** documented that `snapshot_time` means "last message received, not last value sampled". Per-metric `last_updated_at` is post-MVP polish.

**Changes:**
- [`data-model.md`](data-model.md) §3.10 — explicit semantic note.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `device_snapshot.snapshot_time`.

### #11 — pg_dump of TimescaleDB hypertables

**Validity:** Confirmed. Standard `pg_dump` doesn't handle Timescale chunks correctly without the recommended pre/post wrappers.

**Resolution chosen — judgment call: document `pg_dump -Fc` + `timescaledb_pre_restore()` / `timescaledb_post_restore()` recipe.** Did not adopt `timescaledb-backup-tool` (a separate Timescale-published utility) — it's an extra dependency for marginal MVP benefit.

**Changes:**
- [`data-model.md`](data-model.md) §8 — full backup procedure with the Timescale pre/post wrappers.

### #12 — No retention/cleanup for `dead_letter`, `audit_entry`, `control_command`

**Validity:** Confirmed for `dead_letter` (30-day retention claim with no enforcement) and `control_command` (3-year retention with no enforcement). `audit_entry` is intentionally indefinite.

**Resolution:** app-level periodic sweep (daily at 03:00 UTC) deletes rows past retention. `pg_cron` rejected for MVP — extension overhead.

**Changes:**
- [`data-model.md`](data-model.md) §5 — new section documenting the sweep.
- [`ingestion-worker.md`](ingestion-worker.md) §11 — concrete task implementation.

### #13 — Stored MQTT password lands in `pg_dump` plaintext

**Validity:** Confirmed.

**Resolution chosen — judgment call: extend access-control posture to S3 backups, don't encrypt the column.** Reasoning:
- Encrypting one column with `pgcrypto` adds operational complexity (key management, restore-time decryption) for one piece of data.
- AWS S3 in af-south-1 supports SSE-S3 (default since 2023) + bucket policies — same effective protection at the storage tier.
- Future migration to AWS IoT Core eliminates the password entirely (mTLS device certs).

**Changes:**
- [`data-model.md`](data-model.md) §3.2 + §8 — explicit S3 SSE-S3 + IAM-restricted bucket access requirement.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `app.site.mqtt_password`.

### #14 — `profile_yaml` JSONB silently loses hex-address notation

**Validity:** Confirmed. YAML `0x0600` → integer in JSONB; round-trip produces `1536` instead.

**Resolution:** documented. Edge agent works fine reading integers; the future profile editor UI ([SOL-12](https://linear.app/solamon/issue/SOL-12)) will need to render integers as hex strings.

**Changes:**
- [`data-model.md`](data-model.md) §3.3 — explicit note.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `device_type.profile_yaml`.

### #15 — `enum_values` integer keys

**Validity:** Confirmed but already addressed in the device-library review.

**Resolution:** noted in cloud spec for awareness.

**Changes:**
- [`data-model.md`](data-model.md) §3.5.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `logical_metric`.

### #16 — Timezone column has no validation

**Validity:** Confirmed.

**Resolution chosen — judgment call: app-layer Pydantic validation; no Postgres CHECK or trigger.** Reasoning:
- A `CHECK` against `pg_timezone_names` requires an immutable function — `pg_timezone_names` is volatile, so the CHECK won't compile.
- A trigger is the technically correct path but adds an enforcement layer for one column of one table.
- Pydantic validation against `zoneinfo.available_timezones()` covers the same surface at write time.

**Changes:**
- [`data-model.md`](data-model.md) §3.2 + [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — explicit documentation.

### #17 — Late ack arriving after `expired`

**Validity:** Confirmed.

**Resolution:** late ack writes an `audit_entry` with `action='command.late_ack'` capturing the late `confirmed_value` but does NOT change `control_command.status`. Operator manually reconciles via the audit trail.

**Changes:**
- [`control-relay.md`](control-relay.md) §1.1 + §4 (the ack handler).
- [`mqtt-contracts.md`](mqtt-contracts.md) §7.2 — referenced.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — comment on `control_command`.

### #18 — Mosquitto LWT retain flag

**Validity:** Confirmed real bug. Without `will_retain: true`, after a Pi crash the retained "online" heartbeat persists forever to fresh subscribers.

**Resolution:** added `will_retain: true` to the connection-parameters table.

**Changes:**
- [`mqtt-contracts.md`](mqtt-contracts.md) §10.

### #19 — `POST /commands` 202 before publish state known

**Validity:** Confirmed. Combined with #2 — same root.

**Resolution:** see #2. Response status field discriminates publish outcome; HTTP 202 vs 503 discriminates broker reachability.

**Changes:** see #2.

---

## Minor

### #20 — `app."user"` reserved word

Renamed to `app.users` (plural, idiomatic, no quoting).

**Changes:** migration + data-model.md + every internal reference (FKs).

### #21 — No `received_at` on Reading

Added nullable `received_at TIMESTAMPTZ DEFAULT now()`. Useful for end-to-end-latency dashboards and clock-skew debugging. NULL allowed for backfilled / replayed rows.

### #22 — WS envelope inconsistency

Both endpoints use `{type, data}` shape — schemas added to `openapi.yaml` `components.schemas` with discriminators (per #6).

### #23 — 30-day query range vs 90-day retention

Documented the rationale (response size / latency budget for raw queries; aggregated views handle longer windows).

**Changes:** [`api-surface.md`](api-surface.md) §4.3.

### #24 — `mqtt.password` not annotated as sensitive

Added `format: password` and `description: "Sensitive — never log"` in `openapi.yaml`.

### #25 — gzip compression note

Added one-line note that Caddy compresses `application/json` by default.

**Changes:** [`api-surface.md`](api-surface.md) §8.

### #26 — Mosquitto ACL regeneration unspecified

Added cross-reference to the (still-to-be-written) infrastructure spec.

**Changes:** [`mqtt-contracts.md`](mqtt-contracts.md) §9.

### #27 — Migration tracking has no checksum

Comment in the migration table noting "TODO post-MVP: checksum column when we move to Alembic".

**Changes:** [`migrations/0001_initial.sql`](migrations/0001_initial.sql).

### #28 — State-machine inconsistency

**Resolution chosen — judgment call: drop `acknowledged` from the state machine.** Reasoning:
- Two specs (main spec § 10 vs control-relay.md) said different things about whether the state was deliberate.
- The simpler 4-state machine (pending → sent → confirmed | failed | expired) is easier to render in the UI and the value of the `acknowledged` intermediate state was marginal (~1-2 s of visibility into Pi-side validation).
- Easy to add back later if a real diagnostic need surfaces.

**Changes:**
- Main spec §10 — diagram simplified.
- [`control-relay.md`](control-relay.md) §1, §4, §5.
- [`mqtt-contracts.md`](mqtt-contracts.md) §7.2 — Pi only emits terminal acks.
- [`edge-agent/command-subscriber.md`](../edge-agent/command-subscriber.md) §4 — pre-emit step removed.
- [`migrations/0001_initial.sql`](migrations/0001_initial.sql) — `status` CHECK constraint and partial index updated.
- [`openapi.yaml`](openapi.yaml) — `ControlCommand.status` enum reduced.

### #29 — JSONB merge shape note

Added documentation that the shallow merge assumes flat key:value structure; a future nested shape needs explicit handling.

**Changes:** [`data-model.md`](data-model.md) §3.10.

### #30 — `billing_contact_email` unused

Acceptable column-for-future. Comment added.

**Changes:** [`migrations/0001_initial.sql`](migrations/0001_initial.sql).

### #31 — Future audit-browser index

Added a TODO comment in the migration: when the audit-browser UI ships, add `(actor_id, time DESC)` index.

**Changes:** [`migrations/0001_initial.sql`](migrations/0001_initial.sql).

### #32 — `/auth/logout` 401 vs 204

Made logout `security: []` (no auth required); always returns 204.

**Changes:**
- [`api-surface.md`](api-surface.md) §3.2.
- [`openapi.yaml`](openapi.yaml) — `security: []` on the endpoint.

### #33 — Edge auth scheme reuses MQTT password (clarification)

Documented in api-surface.md §3.4 — the bearer token IS the MQTT password; the response containing the same value back is deliberate (atomic config-write on the Pi).

---

## Summary

- **33 findings, 33 addressed.**
- **Five judgment calls** flagged (#1 routing, #6 skip AsyncAPI, #11 backup tooling, #13 backup encryption, #16 timezone validation, #28 drop acknowledged).
- **Two architectural deferrals** caught: AXM-WEB2 push profile work ([SOL-22](https://linear.app/solamon/issue/SOL-22), already filed); per-metric snapshot timestamp granularity (no separate issue — minor enough to handle when needed).
- **Schema changes:** `users` table rename, `received_at` column added to Reading, `last_publish_error` column added to ControlCommand, status CHECK + partial index updated to drop `acknowledged`. All in 0001 (greenfield migration; no separate "fix" migration needed).
- **Doc changes:** every cloud spec (6 files), the main MVP spec §10, the edge-agent command-subscriber spec.

The biggest single risk identified — **#1 (value column type mismatch)** — now has an explicit routing rule. The first end-to-end test on bench Day 4-5 won't produce missing-data or crash scenarios.

The control-flow improvements (**#2 + #19**) materially improve the operator UX for the marquee MVP demo: the operator can now distinguish "publish failed but we're retrying" from "publish failed because broker is down" within the request response, instead of staring at `pending` for 5 minutes.
