# Edge agent — architecture

**Spec group:** [edge-agent](README.md)
**Linear:** [SOL-7](https://linear.app/solamon/issue/SOL-7)

The process model, asyncio task topology, lifecycle, and cross-cutting concerns (heartbeat, logging, crash-loop protection) of the Python edge agent.

---

## 1. Process model

**One Python process, one Docker container, one Pi.** The container runs `python -m solamon_edge` (or whatever the entry point is named at implementation). Process supervision is layered:

```
systemd (on Pi host)
  └── docker daemon
      └── solamon-edge container (restart: always)
          └── python process
              └── asyncio event loop
                  ├── Modbus poller tasks (one per read_block)
                  ├── MQTT publisher task
                  ├── MQTT command subscriber task
                  ├── Heartbeat task
                  ├── Replay sweeper task
                  └── Config refresh task
```

If the Python process crashes, Docker restarts it (with the configured `restart-policy`). If the Docker daemon stops, systemd restarts it. If the Pi reboots, systemd brings the daemon back up. There is no scenario where the agent stays dead without operator intervention.

## 2. Task topology

```
                    ┌─────────────────────────┐
                    │  Profile (immutable)    │
                    │  Site config (mutable   │
                    │   via config_refresh)   │
                    └────────────┬────────────┘
                                 │
       ┌─────────────────────────┼─────────────────────────────────┐
       │                         │                                  │
       ▼                         ▼                                  ▼
┌────────────────┐      ┌────────────────┐                  ┌────────────────┐
│ Modbus poller  │      │ MQTT publisher │                  │ MQTT subscriber│
│ (one per read  │ ───▶ │ (drains buffer)│                  │ (commands)     │
│  block)        │      └────────────────┘                  └────────────────┘
│                │              ▲                                   │
└───────┬────────┘              │                                   │
        │                       │                                   │
        ▼                       │                                   │
   SQLite buffer ───────────────┘                                   │
   (7-day ring)                                                     │
                                                                    ▼
┌────────────────┐      ┌────────────────┐                  ┌────────────────┐
│ Heartbeat      │      │ Replay sweeper │                  │ Modbus client  │
│ (every 60 s)   │      │ (every 30 s)   │                  │ (FC06 + FC03)  │
└────────────────┘      └────────────────┘                  └────────────────┘
```

### 2.1 Tasks at a glance

| Task | Cadence | Responsibility | Spec |
|------|---------|----------------|------|
| **Modbus poller** (N per N read blocks) | Per-block `cadence_s` from profile | Read FC03 batched block, decode, write to SQLite | [`modbus-poller.md`](modbus-poller.md) |
| **MQTT publisher** | Continuous (~0.5 s drain interval) | Pull unpublished rows from SQLite, build per-block telemetry messages, publish QoS 1 | [`mqtt-publisher.md`](mqtt-publisher.md) |
| **MQTT command subscriber** | On-message | Receive command, validate, FC06 write + read-back, publish ack | [`command-subscriber.md`](command-subscriber.md) |
| **Heartbeat** | 60 s | Publish status to `solamon/{slug}/heartbeat`. Implementation is **inside** the MQTT loop (see [`mqtt-publisher.md`](mqtt-publisher.md) §7) — runs alongside the publisher and command subscriber under the same `async with mqtt:` block, so when the broker disconnects, heartbeat is naturally suspended and LWT covers the offline transition. | [`mqtt-publisher.md`](mqtt-publisher.md) §7 |
| **Config refresh** | 5 min | GET `/edge/config/{slug}` from cloud; if changed, log + (post-MVP) signal hot-reload | [`config-loader.md`](config-loader.md) §4 |

### 2.2 Shared state

- **Profile object** — loaded once at startup, immutable until process restart (hot reload deferred to [SOL-17](https://linear.app/solamon/issue/SOL-17)).
- **Logical metrics catalog** — same.
- **Modbus client** — single `AsyncModbusTcpClient` instance; shared by pollers and command subscriber. pymodbus serializes operations on a TCP connection internally; no extra locking needed.
- **MQTT client** — single `asyncio-mqtt` Client; shared by publisher, subscriber, heartbeat.
- **SQLite connection pool** — small pool (4 connections) using `aiosqlite`; each task gets its own connection from the pool.
- **Health metrics** — atomic counters and gauges, kept both **per-block** (for diagnostics) and **globally aggregated**:
  - `modbus_errors[block_name]` (rolling 60-second window per block)
  - `modbus_errors_total` (rolling 60-second window summed across all blocks)
  - `modbus_successes[block_name]` (per-block) + `modbus_successes_total` (global)
  - `last_modbus_success_at` (timestamp; global)
  - `buffer_depth_seconds` (computed: `now() - oldest_unpublished_time`)
  - `halted_blocks: set[str]` — block names that have been disabled until restart per [`modbus-poller.md`](modbus-poller.md) §5
- The logical metric `edge_modbus_errors_per_minute` published as telemetry uses the **global** counter; per-block counters are exposed in heartbeat for diagnostics.

## 3. Lifecycle

### 3.1 Startup sequence

```
0. Verify the system clock is NTP-synced
   └─ Run `timedatectl show -p NTPSynchronized --value`
   └─ If "no" → log CRITICAL `clock_unsynchronised`, sleep 30s, retry
   └─ After 5 retries (2.5 min) → exit 1
   └─ Why: telemetry timestamps must be UTC-correct or hypertable
       ordering breaks and the cloud's snapshot_time semantics fail.

1. Read /etc/solamon/bootstrap.yaml
   └─ { site_slug, cloud_url, bearer_token }
   └─ If missing or invalid → exit 1 (operator misconfiguration)

2. Initialize logger (structured JSON to stdout)

3. Initialize SQLite buffer DB if not present (run schema migration)

4. Fetch site config from cloud (config-loader.md)
   └─ GET {cloud_url}/api/v1/edge/config/{site_slug}
   └─ Auth: Bearer {bearer_token}
   └─ Cache to /etc/solamon/site_config.yaml
   └─ On failure: load /etc/solamon/site_config.yaml (last good)
   └─ If both fail → exit 1 (cannot operate without config)

5. Validate profile against architecture/profiles/profile.schema.json
   └─ On failure → exit 1 (cannot trust the config)

6. Connect to MQTT broker
   └─ TLS:8883, username/password per site_config.mqtt
   └─ clean_session=false, client_id="solamon-edge-{slug}"
   └─ Register LWT on solamon/{slug}/heartbeat with offline payload
   └─ Reconnect with exponential backoff on failure (1s, 2s, 4s, 8s, 16s, 32s, 60s capped)
   └─ Connection failure does NOT block startup — agent runs and buffers locally

7. Connect to Modbus device
   └─ pymodbus AsyncModbusTcpClient(host, port)
   └─ On connect: run profile.fingerprint
       ├─ On match → log identifiers, store in app state, continue
       └─ On mismatch → log CRITICAL with details (which fingerprint reads failed),
                         halt poller tasks (no Modbus traffic).
                         Heartbeat continues with status="online" — the AGENT is
                         alive; only the device is wrong. The heartbeat's
                         `halted_blocks` field will contain all block names so
                         the operator UI can render the device as "fingerprint
                         mismatch" when it sees telemetry stop arriving despite
                         a healthy heartbeat. There is no `solamon/{slug}/alarms/...`
                         topic in MVP for this — operator notices via dashboard
                         + journalctl. Adding a real alarms topic is post-MVP.

   └─ Hot-swap caveat: re-fingerprint runs once at startup. Replacing the
       physical device with a different unit while the agent is running is
       NOT auto-detected — the agent will keep decoding 0x0600 against
       whatever's on the wire, producing nonsense telemetry. Device replacement
       requires `docker restart solamon-edge`. Re-fingerprint-on-Modbus-reconnect
       is post-MVP.

8. Subscribe to commands topic: solamon/{slug}/commands/{device_id}

9. Start asyncio tasks (per §2.1 table)

10. Log "edge agent ready" + transition status to running
```

### 3.2 Steady state

All tasks running. Pollers fill SQLite at their cadences. Publisher drains. Subscriber processes commands. Heartbeat every 60 s. Replay sweeper recovers stuck publishes. Config refresh quietly checks for updates.

The agent is **stateful but recoverable** — if the process restarts, it picks up from the SQLite buffer (unpublished rows are retried) and the cached site config. No loss except for the in-flight Modbus read at the moment of crash.

### 3.3 Shutdown sequence

On `SIGTERM` (Docker stop, `systemctl stop`):

```
1. Set shutdown flag (visible to all task loops)
2. Cancel all polling tasks (asyncio.CancelledError to each)
3. Wait up to 5 s for the publisher task to drain pending messages
4. Disconnect MQTT cleanly (DISCONNECT packet — does NOT trigger LWT)
5. Close Modbus client
6. Close SQLite connection pool (commits any in-flight transaction)
7. Exit 0
```

**Hard timeout 30 s** for the whole shutdown. If we exceed it, exit 1 — Docker will kill the process anyway. The next startup picks up unpublished rows on next reconnect.

On `SIGKILL` (forced): no cleanup. SQLite WAL ensures transactions are atomic; on restart we recover.

## 4. Heartbeat

The heartbeat is **not a standalone task** — it runs inside the MQTT loop alongside the publisher and command subscriber, sharing the same MQTT client. Concrete implementation in [`mqtt-publisher.md`](mqtt-publisher.md) §7. Payload per [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §5.

The heartbeat enriches the basic `online`/`offline` status with diagnostic fields the cloud surfaces in the operator UI's edge-health card:

- `buffer_depth_seconds` — computed from SQLite (`now() - oldest_unpublished_time`)
- `last_modbus_success` — timestamp of the most recent successful read across all blocks
- `modbus_errors_per_minute` — global counter (sum across blocks)
- `halted_blocks: []` — names of blocks halted by the consecutive-failure rule (see [`modbus-poller.md`](modbus-poller.md) §5)

The retain flag (set at publish time) ensures new dashboard subscribers see the latest heartbeat immediately. The LWT (registered at MQTT connect with `will_retain: true`) replaces the retained "online" message with an "offline" message on unexpected disconnect.

**Timestamp semantics:** all heartbeat timestamps are UTC, RFC 3339 with millisecond precision. The Pi uses a `now_utc()` helper that returns `datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`. Naked `datetime.now()` (which yields a timezone-naive value in the host's local time) must NOT be used — see [`config-loader.md`](config-loader.md) §0 (NTP prerequisite) and the lib-level `now_utc()` helper.

## 5. Logging

Structured JSON to stdout via `python-json-logger`:

```json
{"timestamp": "2026-05-02T12:34:56.789Z", "level": "INFO", "task": "modbus_poller", "block": "realtime", "event": "poll_success", "metrics_count": 32, "elapsed_ms": 47}
```

Log levels:

| Level | Examples |
|-------|----------|
| `DEBUG` | Every Modbus read decoded, every MQTT publish |
| `INFO` | Task start/stop, successful config refresh, heartbeat, MQTT (re)connect |
| `WARN` | Single Modbus timeout (transient), MQTT publish retry, config refresh failed (cache used) |
| `ERROR` | Repeated Modbus failures (>3 in a row on same block), failed control command write, fingerprint mismatch |
| `CRITICAL` | Unable to load config (bootstrap or cache), cannot start MQTT or Modbus client at startup |

Docker captures stdout → host journald. Tailscale-SSH'd operators tail `journalctl -u docker.service -f` or `docker logs solamon-edge -f`.

## 6. Crash-loop protection

Restart frequency is rate-limited via **Docker compose's restart policy**, not systemd:

```yaml
edge-agent:
  restart: on-failure:5
  # Combined with a custom retry-delay wrapper or healthcheck-based restart,
  # this caps restarts at 5 per Docker daemon lifetime; subsequent failures
  # leave the container stopped until manual intervention.
```

systemd protects `dockerd` itself (the Docker daemon survives), but it does NOT manage individual containers — `restart: always` inside compose is what governs the agent. If we needed strict crash-loop limits at the systemd level, we'd move the agent out of compose into a systemd-managed unit; for MVP, Docker's policy is sufficient.

If the agent enters this state, the cloud sees:

- Heartbeat stops → `app.site.last_seen_at` ages out → site marked offline within 90 s
- Operator UI shows the site as offline; Tailscale SSH access still works (Tailscale runs separately via systemd, not in the agent container)

Operator triages: SSH in, `journalctl -u docker.service`, `docker logs solamon-edge --since 10m`. Fix and `systemctl restart docker.service` or `docker restart solamon-edge`.

## 7. Health metrics computation

The atomic counters are exposed as a `health` payload that's both:

- Published in heartbeat messages (cloud `app.site` + `app.device` rollup)
- Surfaced as logical metrics on the telemetry side: `edge_modbus_errors_per_minute`, `edge_buffer_depth_seconds`, `edge_last_successful_read`. These appear in the dashboard's "Edge health" card per the main spec §9.3.

Implementation: a small `Metrics` class with rolling-window counters. The poller calls `metrics.record_modbus_success()` or `metrics.record_modbus_error()` after each read. The buffer depth is computed on-demand by querying SQLite for `MIN(time) WHERE published = false`.

## 8. Acceptance criteria

- The startup sequence is implemented in code with each step logged at INFO; failures at any step produce a clear ERROR log + appropriate exit code.
- All six tasks listed in §2.1 are running on a healthy bench Pi (verified by `journalctl` showing periodic activity from each).
- Heartbeat appears on the cloud Mosquitto subscription within 60 s of agent start.
- LWT fires when the container is force-killed (verify by `docker kill solamon-edge` and watching the cloud receive an offline heartbeat within 90 s).
- A clean `docker stop solamon-edge` does NOT trigger the LWT (verified by no offline heartbeat appearing).
- Crash-loop protection kicks in after 5 rapid restarts (verified in test environment).

## 9. Cross-references

- [`config-loader.md`](config-loader.md) — startup step 4
- [`modbus-poller.md`](modbus-poller.md) — task implementation
- [`mqtt-publisher.md`](mqtt-publisher.md) — task implementation
- [`command-subscriber.md`](command-subscriber.md) — task implementation
- [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §5 — heartbeat payload
- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7 — profile loader API
