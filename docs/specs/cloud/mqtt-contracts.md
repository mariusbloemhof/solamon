# Cloud — MQTT contracts

**Spec group:** [cloud](README.md)
**Linear:** [SOL-8](https://linear.app/solamon/issue/SOL-8)

**Single source of truth** for the MQTT topics, payloads, QoS, retain flags, and ACL strategy. Both the edge-agent specs and the cloud ingestion worker spec reference this document — there is no second place where MQTT shapes are defined. Changes here cascade to both sides.

---

## 1. Topic structure

All topics are site-scoped under a `solamon/{site_slug}/...` prefix. ACLs partition by site so a site's edge agent cannot read or write any other site's topics.

```
solamon/{site_slug}/telemetry/{device_id}              ← Pi → cloud
solamon/{site_slug}/heartbeat                          ← Pi → cloud (LWT)
solamon/{site_slug}/commands/{device_id}               ← cloud → Pi
solamon/{site_slug}/commands/{device_id}/ack           ← Pi → cloud
solamon/{site_slug}/config_changed                     ← cloud → Pi (post-MVP — SOL-17)
```

| Field | Constraint |
|-------|-----------|
| `site_slug` | URL-safe, lowercase, alphanumeric + hyphens, matches `app.site.slug`. |
| `device_id` | UUID, matches `app.device.id`. UUIDv4 string with dashes. |

**No wildcards in published topics.** Publishers always publish to a fully-resolved topic. Subscribers (the cloud) use `+` and `#` wildcards in subscription filters.

## 2. QoS, retain, LWT

| Topic | QoS | Retain | LWT? |
|-------|-----|--------|------|
| `telemetry/{device_id}` | **1** | false | no |
| `heartbeat` | 1 | **true** | **yes** |
| `commands/{device_id}` | 1 | false | no |
| `commands/{device_id}/ack` | 1 | false | no |
| `config_changed` (post-MVP) | 1 | true | no |

**Why QoS 1 everywhere:** at-least-once delivery is what we want — duplicates are tolerable (deduplication is cheap server-side; see §6). QoS 2 is more expensive on bandwidth and reduces throughput more than dedup costs.

**Why retain `heartbeat`:** new dashboard subscribers immediately see the last-known liveness state without waiting up to 60 s for the next heartbeat publish.

**Why LWT on heartbeat:** if the Pi disconnects unexpectedly (LTE drops, process crash), Mosquitto publishes the last-will message on the heartbeat topic with `status: offline`. The cloud sees the transition immediately rather than waiting for a heartbeat timeout to elapse.

## 3. Payload format conventions

- All payloads are **UTF-8 JSON**, no BOM.
- All timestamps are **RFC 3339 / ISO 8601** with millisecond precision and explicit UTC offset (`Z`).
- All metric values are **JSON numbers** (never strings); strings reserved for enums, IDs, and free-text.
- All payloads include a `site_slug` and (where applicable) `device_id` field for self-description — useful when payloads are forwarded to debug logs.
- All payloads include the **schema version** of the payload format: `"version": "1.0"` at the top level. Bumped via the same minor/major rules as the device profile schema (see [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §9 — same rules apply here).

## 4. Telemetry — `solamon/{site_slug}/telemetry/{device_id}`

Direction: Pi → cloud. One MQTT message per Modbus read block (so a `realtime`-block read at 10 s emits one message every 10 s with all metrics from that block).

### 4.1 Payload

```json
{
  "version": "1.0",
  "site_slug": "johansworkbench",
  "device_id": "01952b7c-3a14-7000-8000-000000000001",
  "timestamp": "2026-05-02T12:34:56.789Z",
  "block": "realtime",
  "source": "modbus_poll",
  "quality": "good",
  "readings": {
    "frequency_hz": 50.02,
    "voltage_l1_n": 231.4,
    "active_power_total": 12.350,
    "current_neutral": 1.7
  }
}
```

### 4.2 Field semantics

| Field | Type | Notes |
|-------|------|-------|
| `version` | string | Payload version (`1.0` for MVP). |
| `site_slug` | string | Matches `app.site.slug`. Cloud rejects mismatch with topic. |
| `device_id` | string (UUID) | Matches `app.device.id`. Cloud rejects mismatch with topic. |
| `timestamp` | string (RFC 3339) | Edge-agent reading timestamp (NOT publish time). Reading the meter takes ~50 ms; this is approximately the midpoint. |
| `block` | string | The read block name from the device profile. Used to debug missing metrics. |
| `source` | string | `modbus_poll` (regular cycle) or `replay_buffer` (drained from local SQLite after reconnect). The AXM-WEB2 push path uses an entirely different topic + payload schema and will arrive as part of [SOL-22](https://linear.app/solamon/issue/SOL-22); the placeholder enum value previously here was misleading and has been removed. |
| `quality` | string | `good` / `uncertain` / `bad` for the entire block. Per-metric quality is computed cloud-side from `expected_range`. |
| `readings` | object | Map of logical metric name → numeric value. Values are post-scaling, in the metric's catalog unit. |

### 4.3 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://solamon.example/schemas/telemetry-1.0.json",
  "type": "object",
  "required": ["version", "site_slug", "device_id", "timestamp", "block", "source", "quality", "readings"],
  "additionalProperties": false,
  "properties": {
    "version": { "type": "string", "const": "1.0" },
    "site_slug": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*[a-z0-9]$" },
    "device_id": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" },
    "block": { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
    "source": { "type": "string", "enum": ["modbus_poll", "replay_buffer"] },
    "quality": { "type": "string", "enum": ["good", "uncertain", "bad"] },
    "readings": {
      "type": "object",
      "patternProperties": {
        "^[a-z][a-z0-9_]*$": { "type": ["number", "string", "null"] }
      },
      "additionalProperties": false
    }
  }
}
```

The `string` allowance in `readings` is for `datetime` and `enum` metric types (e.g., `meter_clock`, `load_type`). Most readings will be numbers. `null` indicates a metric that decoded as bad (e.g., a NaN Float32).

## 5. Heartbeat — `solamon/{site_slug}/heartbeat`

Direction: Pi → cloud. Published every 60 s on a healthy connection. Retain flag set so a fresh subscriber gets the last-known state immediately. LWT registered on connect: if the Pi disconnects, Mosquitto publishes a synthetic offline message.

### 5.1 Payload (online)

```json
{
  "version": "1.0",
  "site_slug": "johansworkbench",
  "timestamp": "2026-05-02T12:35:00.000Z",
  "status": "online",
  "edge_version": "0.1.0",
  "buffer_depth_seconds": 0,
  "last_modbus_success": "2026-05-02T12:34:55.123Z",
  "modbus_errors_per_minute": 0,
  "halted_blocks": []
}
```

`halted_blocks` is the list of read-block names the edge agent has stopped polling because they hit the consecutive-failure threshold defined in `../edge-agent/modbus-poller.md §5` (e.g., `["energy"]` after 10 straight bad reads on the energy block; empty when nothing is halted). The edge always publishes the field per `../edge-agent/mqtt-publisher.md §7`. The `EdgeHealthCard` in `../web-ui/components.md` renders it as the "halted blocks" line.

There is no `"fault"` heartbeat status in MVP — when fingerprint mismatch or block-halt happens, the agent stays online and signals the issue via `halted_blocks`. See `../edge-agent/mqtt-publisher.md §7.2`.

### 5.2 Payload (LWT, published by broker on disconnect)

```json
{
  "version": "1.0",
  "site_slug": "johansworkbench",
  "timestamp": "2026-05-02T12:36:00.000Z",
  "status": "offline"
}
```

The `timestamp` in the LWT is set when the broker decides the client is gone (after `keepalive` × 1.5, default ~90 s). Cloud uses this to set `app.site.last_seen_at`.

## 6. Control command — `solamon/{site_slug}/commands/{device_id}`

Direction: cloud → Pi. Published when an operator issues a control command via the REST API.

### 6.1 Payload

```json
{
  "version": "1.0",
  "id": "01952b7c-3a14-7000-8000-000000000042",
  "site_slug": "johansworkbench",
  "device_id": "01952b7c-3a14-7000-8000-000000000001",
  "logical_metric": "demand_window_minutes",
  "type": "set_value",
  "parameters": {
    "value": 30
  },
  "issued_at": "2026-05-02T14:32:01.000Z",
  "issued_by": "01952b7c-3a14-7000-8000-aaaaaaaaaaaa",
  "expires_at": "2026-05-02T14:37:01.000Z"
}
```

### 6.2 Field semantics

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID) | Matches `app.control_command.id`. |
| `logical_metric` | string | Must reference a writable metric in the catalog AND in the device profile's `control:` block. |
| `type` | string | `set_value` is the only MVP command type. Future: `start`, `stop`, `clear_fault`, `reset_counter`. |
| `parameters` | object | Free-form per command type. For `set_value`: `{ "value": <int|float|string> }`. Validated against `allowed_values` from profile + catalog. |
| `issued_by` | string (UUID) | Matches `app.user.id`. |
| `expires_at` | string (RFC 3339) | TTL — Pi must publish ack before this or cloud reaps the command as `expired`. |

## 7. Command ack — `solamon/{site_slug}/commands/{device_id}/ack`

Direction: Pi → cloud. Published by the Pi after attempting the Modbus write + read-back.

### 7.1 Payload

```json
{
  "version": "1.0",
  "id": "01952b7c-3a14-7000-8000-000000000042",
  "site_slug": "johansworkbench",
  "device_id": "01952b7c-3a14-7000-8000-000000000001",
  "status": "confirmed",
  "received_at": "2026-05-02T14:32:02.100Z",
  "modbus_write_at": "2026-05-02T14:32:02.250Z",
  "readback_at": "2026-05-02T14:32:02.760Z",
  "confirmed_value": { "value": 30 },
  "error_message": null
}
```

### 7.2 Status values

| Status | Means | When emitted |
|--------|-------|--------------|
| `confirmed` | Modbus write succeeded; read-back value matches intended. | Happy path. |
| `failed` | Modbus write failed OR read-back value doesn't match. `error_message` populated. | Problem path. |

The Pi only publishes terminal statuses (`confirmed` / `failed`). Earlier drafts had an intermediate `acknowledged` state — dropped for MVP simplicity (the operator UI sees `sent` until the terminal ack arrives, typically within 1-2 s; the visibility into Pi-side validation that `acknowledged` provided wasn't worth the extra state).

The `expired` state is set cloud-side only (the cloud TTL reaper sets it; the Pi never publishes it). **Late ack handling:** if a Pi ack arrives after the cloud has already marked the command `expired`, the cloud writes an `audit_entry` with `action='command.late_ack'` capturing the late `confirmed_value`, but does NOT change the command status. Operator manually reconciles via the audit trail. See [`control-relay.md`](control-relay.md) §4.

## 8. Config-changed (post-MVP signal — `solamon/{site_slug}/config_changed`)

Direction: cloud → Pi. Triggered when an admin saves an updated device profile via the (post-MVP) profile editor UI ([SOL-12](https://linear.app/solamon/issue/SOL-12)). Payload signals the Pi to re-fetch its config.

```json
{
  "version": "1.0",
  "site_slug": "johansworkbench",
  "timestamp": "2026-05-02T15:00:00.000Z",
  "profile_version": 7,
  "reason": "demand_register_address_corrected"
}
```

In MVP this topic exists in the ACL but no publisher writes to it. Hot reload is [SOL-17](https://linear.app/solamon/issue/SOL-17).

## 9. ACL

Per-site ACL entries, configured in `mosquitto/acls`. **The ACL file is regenerated by the cloud's deploy script** (or admin operation) from the active list of `app.site` rows; Mosquitto is reloaded via `SIGHUP`. The exact regeneration mechanism — script name, trigger event, failure mode — is specified in [`docs/specs/infrastructure/`](../infrastructure/) ([SOL-21](https://linear.app/solamon/issue/SOL-21)). The site-add flow in the API surface specifies that adding a site triggers an ACL regeneration before the site is considered ready.

```
# Each Pi gets its own user with site-scoped permissions.
user solamon-johansworkbench
  topic write  solamon/johansworkbench/telemetry/#
  topic write  solamon/johansworkbench/heartbeat
  topic write  solamon/johansworkbench/commands/+/ack
  topic read   solamon/johansworkbench/commands/#
  topic read   solamon/johansworkbench/config_changed

# Cloud subscribes everywhere; publishes commands.
user solamon-cloud
  topic readwrite solamon/#
```

Generated and rewritten by the cloud at deploy time from the active list of `app.site` rows. Mosquitto reloads the ACL file on `SIGHUP`.

## 10. Connection parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Host | (per site DNS, e.g., `cloud.solamon.example`) | TLS-terminated by Mosquitto directly on port 8883; no Caddy intercept |
| Port | 8883 | TLS only — port 1883 is **not** exposed |
| Username / password | per `app.site.mqtt_username`, `app.site.mqtt_password` | Configured at site provisioning; served via `GET /edge/config/{slug}` |
| Keepalive | 60 s | Broker disconnects after `keepalive × 1.5` of silence |
| Clean session | false | Restored subscriptions across reconnect; QoS 1 messages queued during disconnect |
| Client ID | `solamon-edge-{site_slug}` | Persistent across reconnect; used by broker for queue identity |
| Will retain | **true** | LWT message published as a retained message — fresh subscribers see the offline state immediately rather than the stale "online" retained heartbeat. Without this flag, after a Pi crashes the dashboard would show "online" forever to any new browser session. |

## 11. Versioning

Adding a new field to a payload → **minor bump** (`1.0` → `1.1`). Deserialisers must ignore unknown fields. Cloud accepts payloads at `version <= current_supported_minor`.

Removing a field, renaming a field, changing a field's type, or changing the topic structure → **major bump** (`1.0` → `2.0`). Requires coordinated cloud + edge upgrade.

In MVP we ship `version: "1.0"` and assume forward compat is moot.

## 12. Acceptance criteria

- All five topics (one of which is reserved for post-MVP) are documented above with payload, QoS, retain, LWT.
- Cloud's MQTT subscription filter is `solamon/+/telemetry/+`, `solamon/+/heartbeat`, `solamon/+/commands/+/ack` (three filters total).
- Mosquitto ACL file generated at deploy time from `app.site` rows; matches the §9 template.
- Each payload has a JSON Schema; the ingestion worker validates before insert; bad payloads land on a dead-letter topic (`solamon/_deadletter/...` — system-only) for diagnostic review.
- Edge-agent specs reference this document for all topic / payload definitions; do not redefine.

## 13. Cross-references

- [`data-model.md`](data-model.md) — the receiving end of telemetry messages
- [`ingestion-worker.md`](ingestion-worker.md) — the consumer
- [`control-relay.md`](control-relay.md) — the publisher of commands and consumer of acks
- [`../edge-agent/`](../edge-agent/) — the other side
- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) — the `block` field references the profile's read block names
