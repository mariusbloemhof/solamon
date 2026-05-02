# Cloud — ingestion worker

**Spec group:** [cloud](README.md)
**Linear:** [SOL-8](https://linear.app/solamon/issue/SOL-8)

The MQTT-subscriber, validation, and write path that turns telemetry messages from the Pi into rows in the `timeseries.reading` hypertable and updates `app.device_snapshot`. Runs as background asyncio tasks inside the same FastAPI process for MVP; movable to a Lambda or a separate ECS task later without changing the contract.

---

## 1. Subscriptions

The cloud connects as the `solamon-cloud` Mosquitto user (full ACL) with a single MQTT client. Three subscription filters cover all incoming traffic:

| Filter | Handler | Notes |
|--------|---------|-------|
| `solamon/+/telemetry/+` | `handle_telemetry` | Most volume — every reading from every device. |
| `solamon/+/heartbeat` | `handle_heartbeat` | Every 60 s per Pi + LWT messages. |
| `solamon/+/commands/+/ack` | `handle_command_ack` | Logically part of [`control-relay.md`](control-relay.md), but received here because the MQTT client is shared. |

Connection options match `mqtt-contracts.md` §10: keepalive 60 s, clean session false, client ID `solamon-cloud`. Reconnects are automatic with exponential backoff (1 s, 2 s, 4 s, ..., capped at 60 s).

## 2. Pipeline (per telemetry message)

```
   MQTT message arrives on solamon/{site}/telemetry/{device_id}
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 1. Parse JSON                       │
   │    fail → log + dead-letter         │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 2. Validate envelope                │
   │    - JSON Schema match              │
   │    - site_slug matches topic        │
   │    - device_id matches topic        │
   │    - device exists in app.device    │
   │    fail → log + dead-letter         │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 3. Validate readings                │
   │    For each (metric, value) pair:   │
   │    - metric in catalog?             │
   │    - value type matches data_type?  │
   │    - value in expected_range?       │
   │    fail per-metric → quality=bad/   │
   │    uncertain; readings still accept │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 4. Batch INSERT into                │
   │    timeseries.reading               │
   │    ON CONFLICT DO NOTHING           │
   │    (dedup on (time, device_id,      │
   │     logical_metric_key))            │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 5. Upsert app.device_snapshot       │
   │    metrics jsonb |= readings        │
   │    snapshot_time = msg.timestamp    │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 6. Forward to active WebSocket      │
   │    subscribers for this device      │
   │    (in-process pub/sub)             │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │ 7. Update site_health metrics       │
   │    (last_message_at, msg_count)     │
   └─────────────────────────────────────┘
```

## 3. Validation rules

### 3.1 Envelope validation

- JSON parses cleanly. Failures land in dead-letter (`solamon/_deadletter/parse-fail`) with the original payload + parse error.
- Payload matches the JSON Schema in `mqtt-contracts.md` §4.3 (or §5 / §7 for heartbeat / ack).
- `site_slug` in payload === site_slug derived from topic. Mismatch → reject (likely a misconfigured Pi or a malicious client).
- `device_id` in payload === device_id derived from topic. Same.
- The `(site_slug, device_id)` pair exists in `app.site` joined to `app.device`. Unknown → reject + log to `solamon/_deadletter/unknown-device` (operator alert: device might have been deleted while a Pi is still publishing).

### 3.2 Per-reading validation

For each `(logical_metric_key, value)` in `readings`:

- `logical_metric_key` exists in `app.logical_metric`. Unknown → drop the reading (don't fail the whole message); log warning.
- For numeric metrics: `value` is a JSON number. Type mismatch → drop reading; log warning.
- For enum metrics: `value` is the string symbolic form OR the integer code; coerce to the canonical form (string).
- For datetime metrics: `value` is an RFC 3339 string; parse → store as datetime.
- Value falls in the catalog's `expected_range`. Outside → still insert, but flag `quality=uncertain` for that reading. Hard `bad` quality only when decoding failed (which the edge agent handles before publishing).

### 3.3 Dead-letter strategy

Failed messages are republished to `solamon/_deadletter/<reason>/<original-topic>` with the original payload + a metadata header explaining the rejection. A separate diagnostic process can subscribe to `solamon/_deadletter/#` to surface them in the operator UI. For MVP we just write them to a `dead_letter` Postgres table and review periodically.

## 4. Insert path

### 4.1 Batched inserts

Per-message: one batch INSERT for all readings in the message (typically 5-30 readings per message). Use Postgres `INSERT ... VALUES (...), (...), (...) ON CONFLICT DO NOTHING`.

```sql
INSERT INTO timeseries.reading
  (time, device_id, logical_metric_key, value, raw_value, quality, block_name)
VALUES
  ($1, $2, 'frequency_hz',         50.02, NULL, 'good', 'realtime'),
  ($1, $2, 'voltage_l1_n',        231.40, NULL, 'good', 'realtime'),
  ($1, $2, 'active_power_total',   12.35, NULL, 'good', 'realtime')
  -- ...
ON CONFLICT (time, device_id, logical_metric_key) DO NOTHING;
```

### 4.2 Idempotency / dedup

QoS 1 means we get at-least-once delivery. Duplicates can arrive when:

- The Pi reconnects and replays a buffered reading that the cloud already received.
- The cloud's MQTT client reconnects mid-message and the broker re-delivers.

The unique constraint on `(time, device_id, logical_metric_key)` ensures duplicates are silently dropped at insert. No application-level dedup needed.

### 4.3 Snapshot upsert

In the same DB transaction as the readings insert:

```sql
INSERT INTO app.device_snapshot (device_id, snapshot_time, metrics)
VALUES ($1, $2, $3)
ON CONFLICT (device_id) DO UPDATE
  SET snapshot_time = EXCLUDED.snapshot_time,
      metrics = app.device_snapshot.metrics || EXCLUDED.metrics
  WHERE EXCLUDED.snapshot_time > app.device_snapshot.snapshot_time;
```

The `WHERE` clause on the conflict is important: out-of-order replay (Pi pushes a buffered older reading after an already-received newer one) must not regress the snapshot to old data. The hypertable still gets the older row (history is preserved) but the snapshot only ever moves forward.

## 5. Heartbeat handler

Simpler than telemetry. On a heartbeat message:

```sql
UPDATE app.site SET last_seen_at = $timestamp WHERE slug = $slug;
UPDATE app.device SET status = $status WHERE site_id = (SELECT id FROM app.site WHERE slug = $slug);
```

(`status = 'online' | 'offline'` based on the heartbeat's status field.)

A periodic background task (every 5 min) marks sites with `last_seen_at < now() - 90 seconds` as offline — covers the case where the LWT didn't fire (e.g., the Pi's network silently dies without notifying the broker).

## 6. WebSocket fan-out

For each `WebSocket` connection currently subscribed to a device's live stream, the ingestion worker pushes:

- A `reading` message per reading
- A `snapshot` message after the snapshot upsert

In-process pub/sub for MVP: a `dict[device_id, set[WebSocket]]` map maintained by the FastAPI side; the ingestion worker calls `await broadcast(device_id, message)` which iterates the set and `await ws.send_json(...)` for each.

For MVP single-process: zero coordination overhead. When we split ingestion to a separate process post-MVP, replace this with Redis pub/sub or an MQTT subscription on the WebSocket side.

## 7. Performance targets

| Metric | Target | Notes |
|--------|--------|-------|
| Ingest end-to-end latency (MQTT receive → DB committed) | < 100 ms p95 | Single-host single-process; no network hop except DB |
| Throughput | 1000 readings/sec | Wildly more than MVP needs (one device producing ~3/sec); adequate for early scale-out |
| Memory | < 200 MB resident | Mostly Pydantic validators + asyncpg pool |

## 8. Failure modes

| Failure | Behaviour |
|---------|-----------|
| Postgres unreachable | MQTT messages buffered in-process (asyncio queue, max 10k); dropped beyond that with an error log. The Pi's local SQLite buffer is the real safety net — Pi will replay anything we drop once we recover. |
| MQTT broker disconnect | asyncio-mqtt auto-reconnects with backoff. clean_session=false means QoS 1 messages queue at the broker during the outage; we drain on reconnect. |
| Bad payload | Logged to `dead_letter` table; flagged in operator UI; never retried. |
| Unknown metric in catalog | Reading dropped with warning. Action: add the metric to `architecture/logical_metrics.yaml`, redeploy. |
| Postgres FK violation (unknown `device_id` despite envelope check) | Race condition — device deleted between envelope check and insert. Logged; reading dropped. |

## 9. Acceptance criteria

- Pipeline implemented per §2; integration test pushes a synthetic telemetry message via local MQTT and verifies the resulting `Reading` rows + snapshot update + WebSocket fan-out.
- Idempotency test: same message published twice, only one row in the DB.
- Out-of-order test: replay a 2-minute-old reading after a 1-minute-old; snapshot reflects the newer (1-min-old) values; both rows appear in the hypertable.
- Validation test: a payload with `frequency_hz: 200` is stored with `quality=uncertain` (out of catalog range).
- Dead-letter test: a malformed JSON payload lands in `dead_letter`; doesn't crash the worker.

## 10. Cross-references

- [`mqtt-contracts.md`](mqtt-contracts.md) — input format
- [`data-model.md`](data-model.md) — output destination
- [`api-surface.md`](api-surface.md) — the read endpoints whose data this populates
- [`control-relay.md`](control-relay.md) — the ack-handling code that lives in the same MQTT client
