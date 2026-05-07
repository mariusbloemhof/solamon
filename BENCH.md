# Bench bring-up — Saturday Acuvim L test

End-to-end bring-up for the bench-test MVP. Runs the entire cloud stack on
your laptop; the Acuvim L on Johan's bench pushes telemetry over MQTT to
this laptop's IP. No edge agent is involved — the AXM-WEB2 module talks
directly to the cloud broker, as architected.

> Hard deadline: **Saturday 2026-05-09**.

---

## What you'll demo

1. Acuvim L pushes a JSON payload every N seconds to the broker on this laptop.
2. The cloud app subscribes, translates it via the Acuvim adapter, ingests
   readings into TimescaleDB.
3. You hit `GET /api/v1/sites/bench/devices/{id}/snapshot` and see live values.
4. You hit `GET /api/v1/sites/bench/devices/{id}/readings?metric=frequency_hz&from=...&to=...`
   and see a series.

---

## Prerequisites

- Docker Desktop running
- The repo's `.venv` activated (`.venv/Scripts/python.exe`)
- Cloud app dependencies installed: `uv pip install -e "packages/cloud_app[dev]"`
- LAN connectivity: the Acuvim's AXM-WEB2 must be able to reach this laptop's
  LAN IP on port 1883. Find your laptop IP with `ipconfig` (Windows) — pick
  the active adapter the Acuvim shares a subnet with.

---

## Step 1 — start Postgres + Mosquitto

In one terminal:

```pwsh
docker run --name solamon-pg -d `
  -e POSTGRES_PASSWORD=solamon -e POSTGRES_USER=solamon -e POSTGRES_DB=solamon `
  -p 5432:5432 timescale/timescaledb:2.26.4-pg16
```

In another:

```pwsh
docker run --name solamon-mqtt -d -p 1883:1883 `
  -v "${PWD}/bench/mosquitto.conf:/mosquitto/config/mosquitto.conf" `
  eclipse-mosquitto:2
```

> See [bench/mosquitto.conf](bench/mosquitto.conf) for the broker config —
> anonymous access on 1883, no TLS. Bench-only.

Wait ~5s for Postgres to be ready (`docker logs solamon-pg | tail`).

---

## Step 2 — set env vars

```pwsh
$env:DATABASE_URL  = "postgres://solamon:solamon@localhost:5432/solamon"
$env:JWT_SECRET    = "bench-jwt-secret-32-chars-or-more-please"
$env:MQTT_HOST     = "localhost"
$env:MQTT_PORT     = "1883"
$env:HTTP_PORT     = "8000"
$env:LOG_LEVEL     = "INFO"
$env:ACUVIM_TOPIC  = "solamon/+/acuvim/+/data"
$env:BENCH_SITE_SLUG = "bench"
# BENCH_DEVICE_ID is set after running the seed (Step 3).
```

---

## Step 3 — seed the database

```pwsh
.venv\Scripts\python.exe -m cloud_app.seed
```

The seed prints the device UUID at the end. Capture it:

```pwsh
$env:BENCH_DEVICE_ID = "<paste UUID from seed output>"
```

The seed is idempotent — re-running it after schema changes is safe.

---

## Step 4 — start the cloud app

```pwsh
.venv\Scripts\python.exe -m cloud_app
```

You should see structured-log lines:
```
startup.migrations.done
mqtt.subscribed host=localhost port=1883 topic=solamon/+/acuvim/+/data
INFO: Uvicorn running on http://0.0.0.0:8000
```

Leave this terminal running.

---

## Step 5 — configure the Acuvim AXM-WEB2

In the AXM-WEB2 web UI (Section 6.16 — MQTT Push Configuration):

| Field | Value |
|-------|-------|
| Broker address | your laptop LAN IP (`ipconfig` to find it) |
| Broker port | `1883` |
| Username / Password | leave empty (anonymous) |
| TLS | off |
| Topic | `solamon/bench/acuvim/<meter-serial>/data` (anything matching `solamon/+/acuvim/+/data` works) |
| QoS | 1 |
| Retained | off |
| Interval | 10 seconds |
| Parameter Type | Real-Time |
| Parameter Selection | V1, V2, V3, I1, I2, I3, Psum, Qsum, Ssum, PF, Freq_Hz, Ep_imp, Ep_exp |

Save and reboot the AXM-WEB2 module. After ~30s it should start publishing.

---

## Step 6 — verify ingestion

### Via API

Get a JWT:
```pwsh
$body = '{"email":"admin@bench.example.com","password":"hunter2"}'
$resp = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/auth/login `
  -ContentType application/json -Body $body
$token = $resp.access_token
```

Snapshot:
```pwsh
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sites/bench/devices/$env:BENCH_DEVICE_ID/snapshot" `
  -Headers @{ Authorization = "Bearer $token" }
```

Should return the latest metrics dict with `frequency_hz`, `voltage_l1_n`, etc.

Readings (last 10 minutes):
```pwsh
$to  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$frm = (Get-Date).AddMinutes(-10).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sites/bench/devices/$env:BENCH_DEVICE_ID/readings?metric=frequency_hz&from=$frm&to=$to" `
  -Headers @{ Authorization = "Bearer $token" }
```

### Via psql (sanity)

```pwsh
docker exec -it solamon-pg psql -U solamon -d solamon -c `
  "SELECT logical_metric_key, value, time FROM timeseries.reading ORDER BY time DESC LIMIT 20;"
```

---

## Step 7 — clean up after the bench

```pwsh
docker stop solamon-pg solamon-mqtt
docker rm   solamon-pg solamon-mqtt
```

Or keep them running and re-run from Step 4.

---

## Troubleshooting

| Symptom | Diagnosis |
|---------|-----------|
| `mqtt.disconnected` log line | Mosquitto isn't running, or the AXM-WEB2 can't reach this laptop. Confirm with `docker logs solamon-mqtt`. |
| `mqtt.adapter.fail` log line | Acuvim payload shape changed or has unexpected param names. Inspect `docker exec solamon-mqtt mosquitto_sub -t '#' -v` to see the raw message. |
| Snapshot returns empty `metrics: {}` | Ingestion hasn't happened yet, or `BENCH_DEVICE_ID` doesn't match what the seed printed. Re-check env. |
| `ingestion.unknown_metric` warning | The Acuvim adapter mapped a param to a logical metric key that isn't seeded. Re-run `python -m cloud_app.seed` (it loads all metrics from `architecture/logical_metrics.yaml`). |
| Login returns 401 | `BENCH_ADMIN_EMAIL` / `BENCH_ADMIN_PASSWORD` differ between the seed run and your login. The seed defaults to `admin@bench.example.com` / `hunter2`. |
