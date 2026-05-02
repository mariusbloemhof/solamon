# Edge agent — detail specs

**Spec group owner:** [SOL-7 — MVP — Edge agent](https://linear.app/solamon/issue/SOL-7)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §4
**Status:** Working spec.

---

## What this spec group covers

The Python daemon that runs on the Raspberry Pi 5 at every site. It polls the Acuvim L over Modbus TCP, buffers locally, publishes telemetry to the cloud over MQTT, and executes control commands with read-back verification. Single process, single Docker container, one deployment per Pi.

**Decoupled from contract specs:** this group implements consumers of contracts defined elsewhere — it does not redefine them. Specifically:
- Profile YAML / logical metric catalog → see [`../device-library/`](../device-library/)
- MQTT topics + payloads → see [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md)
- Cloud `/edge/config/{slug}` endpoint → see [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.6

If a contract changes, the change happens in one of those specs and the edge agent specs follow.

## Files in this folder

| File | What it specifies |
|------|-------------------|
| [`README.md`](README.md) | This index. |
| [`architecture.md`](architecture.md) | Process model, asyncio task topology, lifecycle (startup → steady → shutdown), error / crash-loop strategy, heartbeat. |
| [`config-loader.md`](config-loader.md) | Bootstrap config, cloud config fetch, local cache, fallback behaviour, periodic refresh. |
| [`modbus-poller.md`](modbus-poller.md) | Per-block poller task, FC03 batched read, decoding via profile loader, SQLite buffer write, error handling. |
| [`mqtt-publisher.md`](mqtt-publisher.md) | MQTT connection lifecycle, telemetry publish, ack-on-broker semantics, replay sweeper, LWT registration. |
| [`command-subscriber.md`](command-subscriber.md) | Command receive, profile-side validation, FC06 write, read-back, ack publish, idempotency. |

## Stack summary (recap of main spec §3)

| Concern | Choice |
|---------|--------|
| Language | **Python 3.12+** |
| Modbus library | **pymodbus** (async) |
| MQTT library | **asyncio-mqtt** (paho-mqtt asyncio wrapper) |
| Local persistence | **SQLite** (WAL mode) — 7-day ring buffer |
| Process supervision | Docker `restart: always` + systemd-supervised Docker |
| Logging | structured JSON via `python-json-logger` to stdout (collected by Docker → journald) |
| Config validation | Same profile-loader Python module as cloud + probe CLI (shared library `lib/profile_loader/`) |
| Container OS | Distroless or Debian slim — final pick by infrastructure spec |

## Acceptance for SOL-7

- All five sub-specs in this folder committed and internally consistent.
- Edge agent built, containerised, image pushed to ECR.
- Bench Day 4-5 deliverable: telemetry from a real Acuvim L on the bench arrives in cloud Postgres; visible via `SELECT * FROM timeseries.reading` query.
- Bench Day 9-10 deliverable: control command issued from web UI lands at the Pi, executes the FC06 write, verifies via read-back, acks back to cloud — all within the state machine semantics in main spec §10.

## Out of MVP scope

- Multi-device-per-Pi → [SOL-16](https://linear.app/solamon/issue/SOL-16)
- Hot config reload → [SOL-17](https://linear.app/solamon/issue/SOL-17)
- Profile auto-detection on first connect → [SOL-11](https://linear.app/solamon/issue/SOL-11)
- mTLS auth (replaces username/password when we move to AWS IoT Core) → [SOL-10](https://linear.app/solamon/issue/SOL-10)
- Encrypted local SQLite buffer
- OTA firmware updates beyond `docker compose pull && up -d` over SSH
- Go port → [SOL-10](https://linear.app/solamon/issue/SOL-10)
