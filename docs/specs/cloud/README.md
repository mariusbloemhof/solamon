# Cloud — detail specs

**Spec group owner:** [SOL-8 — MVP — Cloud stack](https://linear.app/solamon/issue/SOL-8)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §3, §5, §6, §10, §11
**Status:** Working spec. Implementation against this spec produces real Postgres migrations, a real FastAPI app, real Mosquitto config, and real OpenAPI artifacts.

---

## Architecture summary

For MVP the cloud is **a single Python process** (FastAPI + ingestion subscriber + control relay all in-process) plus three sidecar containers (Postgres+Timescale, Mosquitto, Caddy). All on one EC2 in `af-south-1`. This is "knowingly throwaway scaffolding around foundation-grade data" — the database schema, the MQTT contracts, and the API surface are intended to live forever; the single-process and single-host topology is deliberately replaceable.

```
┌────────────────────────────────────────────────────────────────────┐
│  EC2 t4g.small, af-south-1, Docker compose                         │
│                                                                    │
│  ┌──────────┐   ┌──────────────────────────────────────────────┐  │
│  │  Caddy   │──▶│  FastAPI process (single)                    │  │
│  │  TLS 443 │   │  ┌────────────┐  ┌──────────┐  ┌─────────┐  │  │
│  │          │   │  │  REST API  │  │ Ingest   │  │ Control │  │  │
│  │          │   │  │  (HTTP)    │  │ worker   │  │ relay   │  │  │
│  │          │   │  │  + WS      │  │ (MQTT    │  │ (MQTT   │  │  │
│  │          │   │  │            │  │  sub)    │  │  pub)   │  │  │
│  │          │   │  └─────┬──────┘  └────┬─────┘  └────┬────┘  │  │
│  └──────────┘   │        │              │              │       │  │
│                 │        ▼              ▼              ▼       │  │
│                 └─────────────────┬──────────────────────────────┘
│                                   │                                │
│  ┌─────────────────┐    ┌─────────▼─────────┐    ┌──────────────┐│
│  │  Postgres 16 +  │◀───│  asyncpg pool      │    │  Mosquitto 2 ││
│  │  TimescaleDB 2  │    └────────────────────┘    │  TLS 8883    ││
│  └─────────────────┘                              └──────┬───────┘│
└─────────────────────────────────────────────────────────┼────────┘
                                                          │
                                            From Pi via LTE/MQTT
```

The future migration to AWS-native (IoT Core, ECS Fargate, Lambda) is tracked in [SOL-10](https://linear.app/solamon/issue/SOL-10). The contracts in this spec group are the migration boundary — what the future architecture must continue to honour.

---

## Files in this folder

| File | What it specifies |
|------|-------------------|
| [`README.md`](README.md) | This index. |
| [`data-model.md`](data-model.md) | Postgres + Timescale schema design — every table, every index, hypertable config, retention policy, migration approach. |
| [`mqtt-contracts.md`](mqtt-contracts.md) | **Single source of truth** for MQTT — topics, payloads, QoS, retain, LWT, ACL. Referenced verbatim by the edge-agent specs. |
| [`api-surface.md`](api-surface.md) | FastAPI endpoint catalogue — auth, REST routes, WebSocket contracts, error response convention, OpenAPI generation. |
| [`ingestion-worker.md`](ingestion-worker.md) | MQTT → Postgres write path — subscriber model, validation, idempotency, batched inserts, snapshot upsert, WS fan-out. |
| [`control-relay.md`](control-relay.md) | Control command lifecycle — REST → MQTT → ack tracking → WebSocket — and the audit trail it produces. |

## Machine-readable artifacts produced

| Path | What it is | Consumed by |
|------|------------|-------------|
| [`docs/specs/cloud/migrations/0001_initial.sql`](migrations/0001_initial.sql) | The agreed initial Postgres schema (raw SQL) — applied by `psql` or by an Alembic-equivalent runner. | The implementation phase copies this into `services/cloud/migrations/` and treats it as migration #1. |
| [`docs/specs/cloud/openapi.yaml`](openapi.yaml) | Skeletal OpenAPI 3.1 spec — every endpoint and major schema declared; details get filled in as routes are built. | Both server (FastAPI generates the actual spec from code) and client (Next.js generates a TypeScript SDK from this skeleton). |

## How the rest of the system relates

- **Edge agent** ([SOL-7](https://linear.app/solamon/issue/SOL-7)) — publishes telemetry per `mqtt-contracts.md`, fetches its config from `GET /api/v1/edge/config/{site_slug}` per `api-surface.md`, executes commands per `control-relay.md`.
- **Probe CLI** ([SOL-18](https://linear.app/solamon/issue/SOL-18)) — uses the same Python profile-loader as the cloud (validation logic shared); does not talk to the cloud directly.
- **Web UI** ([SOL-9](https://linear.app/solamon/issue/SOL-9)) — consumes `api-surface.md`'s endpoints via the OpenAPI-generated TypeScript SDK; subscribes to WebSockets for live data.
- **Infrastructure** ([SOL-21](https://linear.app/solamon/issue/SOL-21)) — provides the EC2, the Docker compose, the TLS certificates, the DNS, the secrets that this stack runs on top of.

## Acceptance for SOL-8

- All six `.md` specs in this folder committed and internally consistent.
- `migrations/0001_initial.sql` committed; runs cleanly on a fresh Postgres 16 + Timescale 2.x; produces all tables specified in `data-model.md`.
- `openapi.yaml` committed with every endpoint listed in `api-surface.md`.
- The MQTT contracts in `mqtt-contracts.md` are referenced (not duplicated) by edge-agent specs.
- No contradictions with [`2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §3, §5, §6.

## Out of scope (deferred)

- AWS-native rearchitecture (IoT Core / ECS / Lambda) → [SOL-10](https://linear.app/solamon/issue/SOL-10)
- Redis pub/sub for WebSocket fan-out (single-process can do it directly in MVP)
- Multi-tenant / multi-organisation auth (single shared admin in MVP)
- Encryption at rest beyond Postgres defaults
- Read replicas, multi-AZ, multi-region
- Audit log browser UI (covered in web-ui spec group as a follow-up)
- TimescaleDB compression policies (RAW reading retention is short enough in MVP that compression isn't needed)
- Continuous aggregates (1-min, 15-min, 1-hour rollups) — billing scope, not MVP
