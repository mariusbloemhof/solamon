# Edge agent — Modbus poller

**Spec group:** [edge-agent](README.md)
**Linear:** [SOL-7](https://linear.app/solamon/issue/SOL-7)

The per-block Modbus poller task: how the agent talks to the Acuvim L over TCP, decodes the response via the device profile, and writes results to the SQLite buffer. One task per `read_block` defined in the profile, running concurrently in the asyncio loop.

---

## 1. Modbus client

A single `pymodbus.client.AsyncModbusTcpClient` instance for the connected device. pymodbus serialises operations on a single TCP connection internally, so multiple poller tasks safely share one client (no extra locking required).

```python
from pymodbus.client import AsyncModbusTcpClient

client = AsyncModbusTcpClient(
    host=site_config.device.host,
    port=site_config.device.port,
    timeout=5,                   # seconds; per-operation timeout
    retries=0,                   # we manage retries at task level
    reconnect_delay=2,           # seconds before pymodbus's own reconnect attempt
    reconnect_delay_max=30,
)
await client.connect()
```

Connection is established at agent startup (after fingerprint passes). If the connection drops mid-life, pymodbus auto-reconnects in the background; per-operation calls return a connection error which the poller task handles per §5.

## 2. Per-block poller task

One asyncio task per `read_block` in the profile. Tasks are launched at startup (per [`architecture.md`](architecture.md) §3.1 step 9) and run for the lifetime of the agent.

```python
# Pseudo-code
async def poll_block(profile: Profile, block: ReadBlock, client: AsyncModbusTcpClient,
                    buffer: SQLiteBuffer, metrics: Metrics):
    while not shutdown:
        cycle_start = time.monotonic()
        try:
            await poll_one_cycle(profile, block, client, buffer, metrics)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("poll_cycle_failed", block=block.name, error=str(e))
            metrics.record_modbus_error(block.name)
        # Sleep the remainder of the cadence
        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0, block.cadence_s - elapsed)
        await asyncio.sleep(sleep_for)
```

Each cycle:

```python
async def poll_one_cycle(profile, block, client, buffer, metrics):
    read_start = time.monotonic()

    # Issue FC03 (or FC04 if the profile says so) batched read.
    if block.fc == 3:
        result = await client.read_holding_registers(
            address=block.address,
            count=block.length,
            slave=site_config.device.unit_id,
        )
    elif block.fc == 4:
        result = await client.read_input_registers(...)
    else:
        raise ValueError(f"unsupported function code {block.fc}")

    if result.isError():
        # Modbus exception (illegal data address, slave failure, etc.)
        metrics.record_modbus_error(block.name)
        log.warn("modbus_exception",
                 block=block.name,
                 exception_code=result.exception_code,
                 address=block.address)
        return

    # Decode via profile loader — translates raw bytes to logical_metric → value
    raw_bytes = registers_to_bytes(result.registers)   # 2 bytes per register, big-endian
    timestamp = now()
    readings = profile.decode(block.name, raw_bytes)

    # Write all readings to SQLite in a single transaction
    rows = [
        BufferRow(
            time=timestamp,
            device_id=site_config.device.id,
            logical_metric_key=metric_key,
            value=reading.value,
            raw_value=reading.raw_value,
            quality=reading.quality,
            block_name=block.name,
            published=False,
        )
        for metric_key, reading in readings.items()
    ]
    await buffer.write_batch(rows)

    elapsed_ms = (time.monotonic() - read_start) * 1000
    metrics.record_modbus_success(block.name, elapsed_ms)
    log.debug("poll_success",
              block=block.name,
              metric_count=len(rows),
              elapsed_ms=int(elapsed_ms))
```

## 3. Decoding contract

The agent does NOT decode bytes itself. It calls `profile.decode(block_name, raw_bytes)` from the shared profile-loader module ([`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7). The loader knows how to interpret each registered format type (`float32_be`, `dword_high_first`, etc.) and applies per-metric scaling.

This means:

- Adding a new format type (e.g., `float64_be` for some future device) is a one-line change in the loader, instantly available to all profiles.
- Decoding bugs are caught once, in tests against the loader, not duplicated across device-specific code.
- The poller stays simple: read bytes → ask loader → write rows.

## 4. SQLite buffer write

The buffer schema:

```sql
CREATE TABLE IF NOT EXISTS reading_buffer (
    time          TEXT NOT NULL,            -- ISO 8601 with millisecond precision
    device_id     TEXT NOT NULL,
    logical_metric_key TEXT NOT NULL,
    value         REAL,
    raw_value     INTEGER,
    quality       TEXT NOT NULL DEFAULT 'good',
    block_name    TEXT NOT NULL,
    published     INTEGER NOT NULL DEFAULT 0,  -- 0 = unpublished, 1 = published
    PRIMARY KEY (time, device_id, logical_metric_key)
);

CREATE INDEX IF NOT EXISTS idx_buffer_unpublished
    ON reading_buffer (published, time)
    WHERE published = 0;
```

WAL mode enabled: `PRAGMA journal_mode=WAL`. Allows concurrent reads while a writer holds the write lock — the publisher reads while pollers write.

Writes use prepared statements with `INSERT OR IGNORE` for the natural primary key — duplicate inserts (e.g., from a power-outage retry) are silent no-ops.

```python
async def write_batch(self, rows: list[BufferRow]):
    async with self.pool.acquire() as conn:
        async with conn.executemany(
            """
            INSERT OR IGNORE INTO reading_buffer
                (time, device_id, logical_metric_key, value, raw_value,
                 quality, block_name, published)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [(r.time_iso, r.device_id, r.metric_key, r.value, r.raw_value,
              r.quality, r.block_name) for r in rows]
        ):
            pass
        await conn.commit()
```

## 5. Error handling

| Error | Detection | Handling |
|-------|-----------|----------|
| Modbus illegal data address (exception 0x02) | `result.isError()`, code 2 | Log WARN, increment error counter, **don't auto-disable the block** — the address might be temporarily illegal during firmware boot. After 10 consecutive failures, log ERROR and stop polling that block until restart. |
| Modbus slave device failure (exception 0x04) | code 4 | Same as above. |
| TCP connection refused / reset | `pymodbus.exceptions.ConnectionException` | Log WARN, increment error counter, sleep cadence, retry next cycle. pymodbus auto-reconnects. |
| Operation timeout | `asyncio.TimeoutError` from pymodbus's internal timeout | Same as connection error. |
| Decode error (impossible — profile validated at startup) | `DecodeError` from profile loader | Log ERROR (this is a bug); skip the cycle; carry on. |
| SQLite write fails (disk full, lock timeout) | `aiosqlite.Error` | Log ERROR, sleep cadence, retry next cycle. The Pi has 30 GB+ free typically; disk full is unlikely. |

## 6. Ring-buffer rotation

A separate background task (in the publisher module — see [`mqtt-publisher.md`](mqtt-publisher.md) §6) deletes rows older than 7 days every 10 minutes. The poller never deletes rows.

## 7. Reading the connection state

Pollers can query `client.connected` to detect a known-disconnected state and skip the cycle (saving the per-operation timeout). pymodbus exposes a `protocol_made_connection` event the poller can subscribe to for richer state tracking — for MVP we keep it simple: try, handle the exception, retry.

## 8. Performance considerations

- **Read latency:** an FC03 batched read of 74 registers over LAN is typically 30-80 ms. Over LTE (if the Acuvim L is somehow remote — not our case) it'd be 200-500 ms.
- **Cadence vs. read time:** if a cycle takes longer than its cadence (e.g., 10 s cadence, but the read takes 12 s due to retries), the next cycle starts immediately (no negative sleep). This is correct behaviour — we self-regulate.
- **Concurrent reads:** with multiple pollers sharing one Modbus client, pymodbus serialises them. Cycles overlap in scheduling but not on the wire. At MVP cadences (10 s / 30 s / 60 s / 300 s / 3600 s), serialisation is fine.
- **CPU on Pi 5:** Acuvim profile = 6 read blocks polling at various rates. Total ~10 reads/minute average. Negligible CPU.

## 9. Acceptance criteria

- One task spawned per `read_block` in the profile, verified by introspecting `asyncio.all_tasks()` after startup.
- Per-cycle log lines at DEBUG include block name, metric count, elapsed time.
- A simulated Modbus exception (e.g., bring up a fake server returning illegal data address) → cycle logs WARN; counter increments; subsequent cycles continue.
- A simulated TCP disconnect → poller stays alive; reconnect happens; cycles resume within 30 s without process restart.
- 7-day buffer test: run for 7+ days at the bench; verify oldest rows continue to be deleted by the rotation task; SQLite size stays under 200 MB.
- Idempotency: kill `-9` the agent mid-write; restart; SQLite is consistent (WAL replay handles in-flight transactions).

## 10. Cross-references

- [`architecture.md`](architecture.md) — task topology
- [`mqtt-publisher.md`](mqtt-publisher.md) — what consumes the buffer
- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7 — profile loader API
- [`../device-library/acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §5 — concrete read blocks for the bench device
