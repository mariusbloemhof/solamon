# Edge agent — command subscriber

**Spec group:** [edge-agent](README.md)
**Linear:** [SOL-7](https://linear.app/solamon/issue/SOL-7)

The Pi side of the control flow. Receives commands from `solamon/{slug}/commands/{device_id}`, validates against the device profile, executes the Modbus write, verifies via read-back, and publishes the ack.

---

## 1. Subscription

Established as part of the MQTT loop in [`mqtt-publisher.md`](mqtt-publisher.md) §2. The subscription filter is **device-specific**:

```python
await client.subscribe(f"solamon/{site.slug}/commands/{device.id}", qos=1)
```

Only the local device's commands arrive on this Pi — no cross-device leakage even if a misconfigured cloud publishes to a wrong topic.

QoS 1 means we get at-least-once delivery; the subscriber must be idempotent (§5).

> **Multi-device note:** the hardcoded single `device.id` in the topic filter is correct for MVP (one device per Pi). When [SOL-16](https://linear.app/solamon/issue/SOL-16) lands multi-device-per-Pi, this becomes a wildcard subscription `solamon/{slug}/commands/+` with per-message dispatch by `device_id` extracted from the topic.

## 2. Per-message handler

The subscription set up in [`mqtt-publisher.md`](mqtt-publisher.md) §2 uses `client.messages_for_topic(...)` so this loop receives only commands for our device — no second-pass topic filter needed.

```python
# Pseudo-code
async def command_loop(client, messages):
    async for message in messages:
        try:
            # Pydantic-validated against the cloud's command schema
            # (mqtt-contracts.md §6).
            cmd = CommandPayload.model_validate_json(message.payload)
            cmd.received_at = now_utc()                  # injected at receive time
        except (ValueError, ValidationError) as e:
            log.error("command_parse_failed", error=str(e), payload=message.payload[:200])
            continue                                      # malformed; drop silently
                                                          # (cloud will time out and mark expired)

        await handle_command(client, cmd)
```

`handle_command` is the heart of the path. It executes synchronously per command — we do NOT process commands in parallel because (a) Modbus writes are serialised on the bus anyway (pymodbus serialises operations on the shared TCP connection — a poll cycle in flight when a command arrives delays the write by up to ~5 s for the longest-timeout block, which is the worst-case latency operators should expect), and (b) writes followed by read-backs need to happen in order to be meaningful.

## 3. Validation

```python
async def handle_command(client, cmd: CommandPayload):
    log.info("command_received", id=cmd.id, metric=cmd.logical_metric)

    # 3.1 Idempotency check
    if cmd.id in recent_commands:
        prior = recent_commands[cmd.id]
        log.warn("command_duplicate", id=cmd.id, prior_status=prior.status)
        await publish_ack(client, prior)                  # re-emit the same ack
        return

    # 3.2 TTL check
    if cmd.expires_at < now():
        ack = build_failed_ack(cmd, status="failed", error="received_after_expiry")
        await publish_ack(client, ack)
        return

    # 3.3 Profile validation
    metric = cmd.logical_metric
    if metric not in profile.control:
        ack = build_failed_ack(cmd, status="failed", error=f"metric_not_controllable: {metric}")
        await publish_ack(client, ack)
        return

    control_spec = profile.control[metric]
    value = cmd.parameters.get("value")
    try:
        profile.validate_control(metric, value)           # raises ValidationError on bad input
    except ValidationError as e:
        ack = build_failed_ack(cmd, status="failed", error=str(e))
        await publish_ack(client, ack)
        return

    # 3.4 Execute the write + read-back
    await execute_command(client, cmd, control_spec, value)
```

## 4. Execute the write

```python
async def execute_command(client, cmd, control_spec, value):
    # Encode the value per profile format
    encoded = encode_value(value, control_spec.format)

    # MVP: the agent only publishes terminal acks (confirmed / failed).
    # The intermediate `acknowledged` state was dropped at the cloud level —
    # the operator UI shows `sent` for the ~1-2 s of Modbus + read-back, then
    # transitions directly to confirmed/failed.

    try:
        # FC06 (write single register) or FC16 (write multiple)
        if control_spec.fc == 6:
            result = await modbus.write_register(
                address=control_spec.address,
                value=encoded,
                slave=site_config.device.unit_id,
            )
        elif control_spec.fc == 16:
            result = await modbus.write_registers(
                address=control_spec.address,
                values=encoded if isinstance(encoded, list) else [encoded],
                slave=site_config.device.unit_id,
            )
        else:
            raise ValueError(f"unsupported control fc: {control_spec.fc}")

        if result.isError():
            ack = build_failed_ack(cmd, status="failed",
                                    error=f"modbus_exception: {result.exception_code}")
            await publish_ack(client, ack)
            recent_commands[cmd.id] = ack
            return

        write_at = now()

        # Wait for the device to settle
        await asyncio.sleep(control_spec.readback_delay_ms / 1000.0)

        # Read back
        readback_addr = control_spec.readback_register.address
        # readback_register.fc defaults to 3 (read holding registers) when absent;
        # see profile schema. For MVP we only have FC03-readable control registers
        # (Acuvim L demand window is at 0x010C, holding-register space).
        readback_fc = getattr(control_spec.readback_register, "fc", 3)
        readback_format = control_spec.readback_register.format
        if readback_fc == 3:
            rb_result = await modbus.read_holding_registers(
                address=readback_addr,
                count=register_count(readback_format),
                slave=site_config.device.unit_id,
            )
        elif readback_fc == 4:
            rb_result = await modbus.read_input_registers(
                address=readback_addr,
                count=register_count(readback_format),
                slave=site_config.device.unit_id,
            )
        else:
            raise ValueError(f"unsupported readback fc: {readback_fc}")

        if rb_result.isError():
            ack = build_failed_ack(cmd, status="failed",
                                    error=f"readback_modbus_exception: {rb_result.exception_code}",
                                    write_at=write_at)
            await publish_ack(client, ack)
            recent_commands[cmd.id] = ack
            return

        rb_bytes = registers_to_bytes(rb_result.registers)
        rb_value = decode_value(rb_bytes, readback_format)

        # Tolerance is hardcoded in values_equal — float-eps relative for floats,
        # exact comparison for ints. NOT a profile field (the profile schema
        # has no `format_tolerance`).
        if values_equal(rb_value, value):
            ack = build_confirmed_ack(cmd, confirmed_value={"value": rb_value},
                                       write_at=write_at, readback_at=now_utc())
        else:
            ack = build_failed_ack(cmd, status="failed",
                                    error=f"readback_mismatch: expected={value}, got={rb_value}",
                                    confirmed_value={"value": rb_value},
                                    write_at=write_at, readback_at=now_utc())

        await publish_ack(client, ack)
        recent_commands[cmd.id] = ack

    except (ConnectionException, asyncio.TimeoutError) as e:
        ack = build_failed_ack(cmd, status="failed", error=f"modbus_connection_error: {e}")
        await publish_ack(client, ack)
        recent_commands[cmd.id] = ack
```

`values_equal` handles type coercion (int vs float comparison) and tolerance for floats (default `1e-6`; integers are exact).

## 5. Idempotency

`recent_commands` is an in-memory LRU cache (1000 entries, 5-minute TTL):

```python
from cachetools import TTLCache
recent_commands: TTLCache[UUID, AckPayload] = TTLCache(maxsize=1000, ttl=300)
```

The 5-minute TTL is matched to the cloud's command TTL so duplicate deliveries within the meaningful window are guaranteed to dedup. Past 5 min, the command would be `expired` cloud-side and re-processing is moot. The 1000-entry cap is wildly more than MVP scale needs (~3.3 cmd/s sustained); no risk of capacity issues.

Re-receipt of a command we've already processed:

- If the command is still in the cache → re-emit the original ack with the original status.
- If it's evicted → process as new.

> ### ⚠️ MVP-only safety: in-memory cache + idempotent commands
>
> The cache is **in-memory only — restart loses it**. Combined with QoS-1 broker redelivery (`clean_session=False`), the broker's persistent session can replay an unacknowledged command after the Pi reconnects post-restart, and the Pi will re-execute the Modbus write.
>
> **For MVP this is safe** because the only command type is `set_value` of `demand_window_minutes`, which is idempotent (writing 30 twice = the meter is at 30). When non-idempotent command types arrive (`start`, `stop`, `clear_fault`, `reset_counter`), this cache must be persisted to SQLite first — see [SOL-24](https://linear.app/solamon/issue/SOL-24).

## 6. Ack publish

```python
def build_ack(cmd, status, **fields):
    return {
        "version": "1.0",
        "id": cmd.id,
        "site_slug": site.slug,
        "device_id": device.id,
        "status": status,
        "received_at": cmd.received_at_iso(),
        **fields,
    }

async def publish_ack(client, ack):
    topic = f"solamon/{site.slug}/commands/{device.id}/ack"
    await client.publish(topic, json.dumps(ack), qos=1)
    log.info("ack_published", id=ack["id"], status=ack["status"])
```

QoS 1; not retained (acks are point-in-time per command).

## 7. Failure modes

| Failure | Behaviour |
|---------|-----------|
| Malformed payload | Logged ERROR; dropped (no ack). Cloud TTL reaper marks `expired` after 5 min. |
| Unknown command type (e.g., `start` when only `set_value` is supported in MVP) | Validation error → `failed` ack with `error=command_type_not_supported`. |
| Disallowed value (not in `allowed_values`) | Validation error → `failed` ack with `error=value_not_allowed`. |
| Modbus exception on write | `failed` ack with the exception code in `error_message`. |
| Modbus disconnect during write | `failed` ack with `error=modbus_connection_error`. |
| Read-back mismatch | `failed` ack including `confirmed_value` (the actual read-back) so the operator can see what happened. |
| MQTT publish-ack fails | Caught by outer MQTT loop; reconnect; ack will be retried automatically (asyncio-mqtt's QoS 1 redelivery). |

## 8. Race conditions and ordering

- **Multiple commands in quick succession**: handled sequentially by `command_loop` (single async iterator). The Modbus bus is serialised; this matches reality.
- **Command arrives during a Modbus poll**: the poll completes; then the command runs; then the next poll runs. Pollers and the command subscriber share the Modbus client, which serialises on the wire.
- **Command arrives during agent shutdown**: the message is dropped on the floor (the asyncio iterator is cancelled); the cloud TTL reaper marks `expired` 5 min later. The Pi could publish a `failed` ack on shutdown but that complicates the shutdown path; we accept the wait.

## 9. Security

- The command payload includes `issued_by` (user UUID) — the Pi logs it for traceability but does NOT use it for authorisation. **Authorisation is the cloud's responsibility**: only authorised users get to `POST /commands` in the first place. The Pi trusts that any command on its topic was authorised.
- ACL on the broker prevents cross-site command delivery (only the cloud user can publish to commands topics).

## 10. Acceptance criteria

- Bench end-to-end: operator clicks "Apply 30 min" in the web UI; Pi receives within 1 s; Modbus FC06 writes `0x010C = 30`; reads back `30`; publishes `confirmed` ack; cloud updates `app.control_command.status = 'confirmed'`; web UI re-renders.
- Validation test: send a command with `value=42` (not in allowed_values for demand window) → `failed` ack with clear error; no Modbus write attempted.
- Idempotency test: simulate a duplicate command delivery (same `id` twice within 5 min) → second delivery emits the cached ack; only one Modbus write.
- Read-back mismatch test: simulate a meter that doesn't accept the write (or returns a different value on read-back) → `failed` ack with `confirmed_value` populated; operator UI shows the actual value.
- TTL test: simulate a command whose `expires_at` is already past at receive time → `failed` ack with `error=received_after_expiry`; no Modbus operation.
- Disconnect test: kill the Modbus connection mid-write → `failed` ack within a few seconds; agent recovers; subsequent commands work.

## 11. Cross-references

- [`architecture.md`](architecture.md) — task topology
- [`mqtt-publisher.md`](mqtt-publisher.md) — shares the MQTT client and connection lifecycle
- [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §6, §7 — command and ack payload formats
- [`../cloud/control-relay.md`](../cloud/control-relay.md) — the cloud side of the same flow
- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §5, §7 — control specs and validation
- [`../device-library/acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §6 — the demand-window control register
