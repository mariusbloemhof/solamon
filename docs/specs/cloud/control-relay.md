# Cloud — control relay

**Spec group:** [cloud](README.md)
**Linear:** [SOL-8](https://linear.app/solamon/issue/SOL-8)

The control command lifecycle — REST POST → DB persistence → MQTT publish → ack subscription → state machine progression → WebSocket push to operators. Implements the state machine in main spec §10 in concrete code.

---

## 1. State machine recap

Reproduced from main spec §10 for self-containment:

```
        ┌─ pending ──── operator clicks "Apply"
        │              FastAPI: validate, persist, MQTT publish
        ▼
   ┌─ sent ──────── MQTT publish accepted by broker
   │              (cloud sets sent_at)
   ▼
┌─ acknowledged ─ Pi received and validated; about to write Modbus
│
▼
┌─ confirmed ─── Modbus write + read-back succeeded
│
└─ failed ───── Modbus write or read-back failed; ack with error
   ─ expired ─── TTL exceeded without confirmation; cloud reaper
```

Every transition writes an `app.audit_entry` row. The control panel UI subscribes to `/api/v1/ws/commands/{id}/live` and re-renders on each transition.

## 2. Components

The control relay is conceptually three things, all running in the same FastAPI process for MVP:

| Component | Trigger | Does |
|-----------|---------|------|
| **Issuer** (HTTP handler) | `POST /api/v1/sites/{slug}/devices/{id}/commands` | Persist `pending` row, MQTT publish, mark `sent`, return 202 |
| **Ack handler** (MQTT subscriber) | `solamon/+/commands/+/ack` message | Update row to `confirmed`/`failed`, emit WS message |
| **TTL reaper** (background task) | Every 30 s | Find rows still in pending/sent/acknowledged past `expires_at`, mark `expired`, emit WS message |

## 3. Issuer (HTTP handler)

### 3.1 Request validation

```python
# Pseudo-code
async def issue_command(slug: str, device_id: UUID, body: CommandIssue, user: User):
    site = await get_site_by_slug(slug)              # 404 if missing
    device = await get_device(device_id, site.id)    # 404 if missing
    require_access(user, site, level="operate")      # 403 if insufficient

    profile = device.device_type.profile_yaml
    metric = body.logical_metric                     # e.g., "demand_window_minutes"

    # Profile must declare this metric as writable
    if metric not in profile["control"]:
        raise ProblemDetails(422, "metric_not_controllable", metric)

    control_spec = profile["control"][metric]
    # Validate parameter against allowed_values
    value = body.parameters["value"]
    if "allowed_values" in control_spec and value not in control_spec["allowed_values"]:
        raise ProblemDetails(422, "value_not_allowed", value)
```

### 3.2 Persist + publish (transactional)

```python
async with db.transaction():
    cmd = await db.create_control_command(
        device_id=device.id,
        logical_metric_key=metric,
        issued_by=user.id,
        parameters=body.parameters,
        status="pending",
        expires_at=now() + timedelta(minutes=5),
    )
    await db.create_audit_entry(
        actor_id=user.id,
        action="command.issue",
        entity_type="control_command",
        entity_id=cmd.id,
        after=cmd.dict(),
    )

# MQTT publish OUTSIDE the DB transaction — if MQTT publish fails after commit,
# the TTL reaper will mark the command expired in 5 min. We don't roll back the DB
# row because we want the audit trail of "we tried to issue this".
try:
    await mqtt.publish(
        topic=f"solamon/{slug}/commands/{device.id}",
        payload=command_to_mqtt_payload(cmd),
        qos=1,
    )
    await db.update_control_command(cmd.id, status="sent", sent_at=now())
    await db.create_audit_entry(
        actor_id=None,  # system
        action="command.sent",
        entity_type="control_command",
        entity_id=cmd.id,
    )
except MqttError as e:
    # Stay in 'pending' — the publish failed; cloud can retry on next operator request
    # or operator can re-issue. TTL reaper covers the worst case.
    log.error("mqtt publish failed", cmd_id=cmd.id, error=e)

# 202 + Location header
return Response(status_code=202, headers={"Location": f"/api/v1/commands/{cmd.id}"}, body=cmd)
```

### 3.3 Why 202 not 201

The command isn't *complete* when the HTTP response goes out — it's `pending` or at best `sent`. 202 Accepted communicates "we got your request, it's being processed; check the resource for the final state." The web UI's command panel polls (or subscribes via WebSocket) for status.

## 4. Ack handler (MQTT subscriber)

The ack handler is registered as part of the ingestion worker's MQTT subscriptions (single MQTT client across the cloud process). When a message arrives on `solamon/+/commands/+/ack`:

```python
async def handle_command_ack(topic: str, payload: bytes):
    site_slug, device_id = parse_ack_topic(topic)
    msg = parse_ack_payload(payload)                # validates schema

    cmd = await db.get_control_command(msg.id)
    if cmd is None:
        log.warn("ack for unknown command", id=msg.id)
        return                                       # late ack for an expired-then-deleted cmd
    if cmd.status in ("confirmed", "failed", "expired"):
        log.warn("ack for terminal command", id=msg.id, status=cmd.status)
        return                                       # ignore late dupes / replays

    async with db.transaction():
        await db.update_control_command(
            id=cmd.id,
            status=msg.status,                       # 'confirmed' or 'failed'
            acknowledged_at=msg.received_at,
            confirmed_value=msg.confirmed_value,
            error_message=msg.error_message,
        )
        await db.create_audit_entry(
            actor_id=None,
            action=f"command.{msg.status}",
            entity_type="control_command",
            entity_id=cmd.id,
            before={"status": cmd.status},
            after={"status": msg.status, "confirmed_value": msg.confirmed_value},
        )

    await broadcast_command_update(cmd.id, status=msg.status, confirmed_value=msg.confirmed_value)
```

`broadcast_command_update` walks the in-process map of WebSocket subscribers for the command and pushes the `transition` message.

## 5. TTL reaper

A simple asyncio task started at app startup:

```python
async def ttl_reaper():
    while True:
        await asyncio.sleep(30)
        try:
            expired = await db.expire_stale_commands(now())
            for cmd in expired:
                await db.create_audit_entry(
                    actor_id=None,
                    action="command.expired",
                    entity_type="control_command",
                    entity_id=cmd.id,
                )
                await broadcast_command_update(cmd.id, status="expired")
        except Exception as e:
            log.error("ttl reaper failed", error=e)
            # Continue — next iteration will retry
```

`expire_stale_commands(now)` SQL:

```sql
UPDATE app.control_command
   SET status = 'expired'
 WHERE status IN ('pending', 'sent', 'acknowledged')
   AND expires_at < $1
RETURNING *;
```

The partial index on `expires_at WHERE status IN ('pending', 'sent', 'acknowledged')` (created in `0001_initial.sql`) makes this query fast — it only scans active commands.

## 6. WebSocket subscription contract

Per `api-surface.md` §5.2: `/api/v1/ws/commands/{id}/live` streams transitions for one command. Implementation:

```python
@app.websocket("/api/v1/ws/commands/{id}/live")
async def command_live(ws: WebSocket, id: UUID, user: User = ws_auth):
    await ws.accept()

    # Send current state immediately
    cmd = await db.get_control_command(id)
    await ws.send_json({"type": "current", "data": cmd.dict()})

    if cmd.status in ("confirmed", "failed", "expired"):
        # Already terminal — close after sending current state
        await ws.close()
        return

    # Subscribe to transitions
    queue = asyncio.Queue()
    command_subscribers[id].add(queue)
    try:
        while True:
            transition = await queue.get()
            await ws.send_json({"type": "transition", "data": transition})
            if transition["status"] in ("confirmed", "failed", "expired"):
                break
    finally:
        command_subscribers[id].discard(queue)
        await ws.close()
```

## 7. Idempotency

The MQTT publish is QoS 1 — duplicates possible. The Pi's command subscriber is responsible for treating duplicate command messages as no-ops: it tracks recently-seen command IDs, and a second arrival of the same `cmd.id` is acked with the same status as the first. This is specified in [`../edge-agent/command-subscriber.md`](../edge-agent/command-subscriber.md), not here.

The cloud is naturally idempotent for ack handling: §4 above checks `cmd.status` before updating; transitioning from a terminal state is rejected.

## 8. Audit trail

Every state transition writes an `app.audit_entry`. Per command, the typical sequence:

```
command.issue       (actor: user;          before: null;            after: cmd@pending)
command.sent        (actor: system;        before: status=pending;  after: status=sent)
command.confirmed   (actor: system;        before: status=sent;     after: status=confirmed, confirmed_value=...)
```

Or in a failure scenario:

```
command.issue
command.sent
command.failed      (actor: system;        before: status=sent;     after: status=failed, error_message=...)
```

The control panel UI's "audit list" pane shows these as the timeline under each command.

## 9. Acceptance criteria

- HTTP 202 returned within 200 ms p95 of `POST /commands` (most of the time is the MQTT publish round-trip; if MQTT is up this is fast).
- WebSocket `/commands/{id}/live` shows the `current` state within 50 ms of connect, and `transition` messages within 100 ms of the underlying state change.
- TTL reaper marks expired commands within 30 s of their `expires_at`.
- Audit entries written for every state transition; visible via `GET /commands/{id}` (which includes `audit_entries[]`).
- Idempotency: ack message for a `confirmed` command is dropped (logged but not applied).
- Validation: command for a non-controllable metric returns 422 with clear `detail`.
- Authorisation: command issued by a user without `operate` access on the site returns 403.

## 10. Cross-references

- [`mqtt-contracts.md`](mqtt-contracts.md) §6, §7 — command and ack payload schemas
- [`data-model.md`](data-model.md) — `app.control_command` and `app.audit_entry` tables
- [`api-surface.md`](api-surface.md) §4.4, §5.2 — REST and WS endpoints
- [`ingestion-worker.md`](ingestion-worker.md) — co-located ack handler shares the MQTT client
- [`../edge-agent/command-subscriber.md`](../edge-agent/command-subscriber.md) — the Pi side
