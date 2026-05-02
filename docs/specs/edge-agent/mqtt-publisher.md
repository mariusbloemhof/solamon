# Edge agent — MQTT publisher

**Spec group:** [edge-agent](README.md)
**Linear:** [SOL-7](https://linear.app/solamon/issue/SOL-7)

The MQTT connection lifecycle, publishing pipeline, and replay-on-reconnect mechanics. Drains the SQLite buffer to the cloud broker; survives transient network drops without losing data.

---

## 1. MQTT client

A single `asyncio_mqtt.Client` instance shared by the publisher, the command subscriber, and the heartbeat task. Connection options (per [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §10):

```python
from asyncio_mqtt import Client, Will
import ssl

ssl_ctx = ssl.create_default_context()
# Optional: pin the CA bundle if we own the cert chain. For Let's Encrypt
# the system trust store is sufficient.

mqtt = Client(
    hostname=mqtt_cfg.broker_host,
    port=mqtt_cfg.broker_port,                  # 8883
    username=mqtt_cfg.username,
    password=mqtt_cfg.password,
    client_id=mqtt_cfg.client_id,               # solamon-edge-{slug}
    keepalive=60,
    clean_session=False,
    tls_context=ssl_ctx,
    will=Will(
        topic=f"solamon/{site.slug}/heartbeat",
        payload=json.dumps({
            "version": "1.0",
            "site_slug": site.slug,
            "timestamp": "<broker-set on disconnect>",
            "status": "offline",
        }),
        qos=1,
        retain=True,
    ),
)
```

The LWT payload's `timestamp` is set by us at connect time but *the broker publishes it* only when the client disconnects unexpectedly — at that point the embedded timestamp is stale by however long the disconnect took to detect. Cloud-side handling (per [`../cloud/ingestion-worker.md`](../cloud/ingestion-worker.md) §5) uses the broker's reception time, not the embedded timestamp, for `last_seen_at`.

## 2. Connect lifecycle

```python
async def mqtt_loop():
    backoff = 1
    while not shutdown:
        try:
            async with mqtt as client:                    # context manager: connect on enter, disconnect on exit
                log.info("mqtt_connected", broker=mqtt_cfg.broker_host)
                backoff = 1                               # reset on successful connect

                # Subscribe to commands inside the same `async with` so subscription
                # is tied to the session.
                async with client.unfiltered_messages() as messages:
                    await client.subscribe(f"solamon/{site.slug}/commands/{device.id}", qos=1)
                    await asyncio.gather(
                        publish_loop(client),
                        command_loop(client, messages),
                        heartbeat_loop(client),
                    )
        except MqttError as e:
            log.warn("mqtt_disconnected", error=str(e), backoff=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)                # exponential, capped at 60 s
```

The `async with mqtt` block opens the connection, registers the LWT (already set in the Will object), and closes cleanly on shutdown. **Clean disconnect at shutdown does NOT trigger the LWT** — that's by MQTT spec.

When a transient drop happens (LTE blip, broker restart), the loop catches the exception and reconnects with exponential backoff. The SQLite buffer keeps growing in the meantime; once reconnected, the publish loop drains it.

## 3. Publish loop

```python
async def publish_loop(client):
    while not shutdown:
        try:
            await publish_pending_batch(client)
            await asyncio.sleep(0.5)                     # small idle gap; loop is otherwise tight
        except MqttError:
            raise                                         # bubble up; outer loop reconnects
        except Exception as e:
            log.error("publish_loop_failed", error=str(e))
            await asyncio.sleep(2)                        # gentler retry on unknown errors
```

`publish_pending_batch` does the actual work:

```python
async def publish_pending_batch(client):
    # Fetch up to 200 rows, oldest first
    rows = await buffer.fetch_unpublished(limit=200)
    if not rows:
        return

    # Group rows by (block_name, time-bucket) — typically all rows from the
    # same poll cycle share an exact timestamp, so the grouping is just
    # (block_name, time)
    for (block_name, timestamp), group in groupby(rows, key=lambda r: (r.block_name, r.time)):
        payload = build_telemetry_payload(block_name, timestamp, list(group))
        topic = f"solamon/{site.slug}/telemetry/{device.id}"
        await client.publish(topic, json.dumps(payload), qos=1)
        await buffer.mark_published([r.id for r in group])
```

`build_telemetry_payload` produces the JSON shape per [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §4:

```python
def build_telemetry_payload(block_name, timestamp, rows):
    return {
        "version": "1.0",
        "site_slug": site.slug,
        "device_id": device.id,
        "timestamp": timestamp.isoformat() + "Z",
        "block": block_name,
        "source": "modbus_poll" if rows[0].is_recent() else "replay_buffer",
        "quality": worst_quality(rows),                  # "bad" if any row is bad, etc.
        "readings": {row.logical_metric_key: row.value for row in rows},
    }
```

`is_recent()` returns true if the row's timestamp is within the last `block.cadence_s × 2` seconds — used to set the `source` field for cloud-side debug.

## 4. Idempotency at publish time

QoS 1 publishes are at-least-once. If the network drops between `client.publish()` returning and the broker actually receiving the PUBACK, the asyncio-mqtt client retransmits on reconnect — a duplicate may arrive at the cloud.

- **Per-message idempotency** is handled cloud-side by the unique constraint on `(time, device_id, logical_metric_key)` in `timeseries.reading`.
- **Per-buffer idempotency** is handled here: a row is marked `published=true` only after the publish call returns successfully. If the agent crashes after publish but before the SQLite UPDATE, the next startup re-publishes the row — the cloud dedups silently.

## 5. Replay sweeper

A periodic background task that runs every 30 s:

```python
async def replay_sweeper():
    while not shutdown:
        await asyncio.sleep(30)
        try:
            stuck_rows = await buffer.fetch_stuck(older_than=timedelta(seconds=60))
            if stuck_rows:
                log.info("replay_sweeper_kicking", row_count=len(stuck_rows))
                # Just unmark them — the publish loop picks them up next iteration.
                await buffer.unmark_in_flight([r.id for r in stuck_rows])
        except Exception as e:
            log.error("replay_sweeper_failed", error=str(e))
```

"Stuck" rows are unpublished rows older than 60 s — they shouldn't exist if the publish loop is healthy; if they do, something's wrong (publish call hung mid-flight, weird state from a partial commit). The sweeper is a safety net.

## 6. Buffer rotation (ring delete)

Same module owns the rotation task — it's logically about the buffer, and the publisher cares about buffer size.

```python
async def rotation_task():
    while not shutdown:
        await asyncio.sleep(600)                          # every 10 minutes
        try:
            cutoff = now() - timedelta(days=7)
            deleted = await buffer.delete_older_than(cutoff)
            if deleted:
                log.info("buffer_rotation", deleted_rows=deleted)
        except Exception as e:
            log.error("rotation_failed", error=str(e))
```

`delete_older_than` deletes regardless of `published` flag — once a reading is older than 7 days it's gone whether or not the cloud got it. In practice published=true rows accumulate during disconnects and we want to drop the oldest first to make room for new readings.

A safer ring would only delete `published=true` rows older than 7 days, and refuse to delete unpublished rows. **Tradeoff**: with this stricter policy, an extended cloud outage would fill the SD card. We choose the simpler policy for MVP — 7 days is generous; an outage that long requires operator intervention anyway.

## 7. Heartbeat publish

Heartbeat uses the same MQTT client. Implementation lives here for code locality:

```python
async def heartbeat_loop(client):
    while not shutdown:
        try:
            payload = {
                "version": "1.0",
                "site_slug": site.slug,
                "timestamp": now().isoformat() + "Z",
                "status": "online",
                "edge_version": __version__,
                "buffer_depth_seconds": await buffer.compute_buffer_depth_seconds(),
                "last_modbus_success": metrics.last_modbus_success_iso(),
                "modbus_errors_per_minute": metrics.modbus_errors_per_minute(),
            }
            await client.publish(
                f"solamon/{site.slug}/heartbeat",
                json.dumps(payload),
                qos=1,
                retain=True,
            )
        except MqttError:
            raise
        except Exception as e:
            log.warn("heartbeat_failed", error=str(e))
        await asyncio.sleep(60)
```

## 8. Failure modes

| Failure | Behaviour |
|---------|-----------|
| TLS handshake fails | Outer loop catches MqttError; backoff + retry. After ~5 min of failures, log CRITICAL `cloud_unreachable_5min`. |
| Auth rejected (bad password) | Backoff hits 60 s ceiling; log ERROR `mqtt_auth_failed`. Retries every 60 s — operator intervention needed (rotate password via cloud). |
| Broker publish ack timeout | asyncio-mqtt raises; outer loop reconnects. Row stays `published=false`; replay sweeper or next publish cycle handles. |
| SQLite buffer locked by another writer | aiosqlite waits; usually <100 ms. Hard timeout 5 s → log warn, retry. |
| Buffer disk full | INSERT fails; log CRITICAL; rotation task tries to free space; if it can't, agent continues but data is lost beyond the in-memory queue (which is small). Operator alerted via heartbeat-stops cascade. |

## 9. Acceptance criteria

- Happy path: bench Pi publishes telemetry; cloud `timeseries.reading` rows accumulate; `published` flag in SQLite updates correctly.
- Disconnect test: pull the LTE / kill the broker for 5 min, then restore. SQLite buffer accumulates rows; on reconnect, all rows drain within 60 s; no duplicates land cloud-side (by virtue of unique constraint).
- Force-kill test: `kill -9` the agent during a publish call; restart. The row that was being published is re-published on next startup; cloud has exactly one row.
- LWT test: `docker kill solamon-edge`; cloud receives an offline heartbeat within ~90 s.
- Buffer rotation test: backdate ten 8-day-old rows; rotation task deletes them within 10 min.
- Auth-rejected test: corrupt the MQTT password in `site_config.yaml`; agent retries with backoff but never crashes; ERROR log emitted.

## 10. Cross-references

- [`architecture.md`](architecture.md) — overall task topology
- [`modbus-poller.md`](modbus-poller.md) — fills the buffer that this drains
- [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) — payload shapes (telemetry §4, heartbeat §5, command/ack §6/7)
- [`../cloud/ingestion-worker.md`](../cloud/ingestion-worker.md) — the receiver
