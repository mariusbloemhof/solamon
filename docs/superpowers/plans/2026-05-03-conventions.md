# Solamon implementation plan conventions

**Applies to:** every plan under `docs/superpowers/plans/2026-05-03-*.md`.

A single source-of-truth for the discipline every plan follows. Each plan references this doc rather than restating the rules.

---

## 1. Repository structure (monorepo)

```
solamon/                                    repo root
├── pyproject.toml                          workspace dev-tooling root (ruff config; no runtime deps)
├── package.json + pnpm-workspace.yaml      node workspace root (web_ui only)
├── architecture/                           data: YAML + JSON schemas (single source of truth)
├── docs/specs/                             specs (already authored)
├── docs/superpowers/plans/                 these plans
├── packages/
│   ├── profile_loader/                     SOL-20 — shared Python lib
│   │   ├── pyproject.toml                  own dependency declaration
│   │   ├── src/profile_loader/             src-layout
│   │   └── tests/
│   ├── edge_agent/                         SOL-7
│   │   ├── pyproject.toml                  depends on ../profile_loader (path dep)
│   │   ├── Dockerfile                      ARM64; produces solamon-edge-agent image
│   │   ├── src/edge_agent/
│   │   └── tests/
│   ├── cloud_app/                          SOL-8
│   │   ├── pyproject.toml                  depends on ../profile_loader
│   │   ├── Dockerfile                      bundles web_ui dist; produces solamon-cloud-app image
│   │   ├── src/cloud_app/
│   │   ├── migrations/0001_initial.sql
│   │   └── tests/
│   ├── probe_cli/                          SOL-18
│   │   ├── pyproject.toml                  depends on ../profile_loader
│   │   ├── src/probe_cli/
│   │   └── tests/
│   └── web_ui/                             SOL-9
│       ├── package.json
│       ├── next.config.ts
│       ├── app/, components/, lib/
│       └── tests/
├── docs/specs/infrastructure/scripts/      SOL-21 (bash co-located with spec)
└── .github/workflows/                      one workflow per spec group, path-filtered
```

Each `packages/X/` is independently buildable, testable, and deployable. Cross-package consumers depend on `profile_loader` via path dep:

```toml
# packages/edge_agent/pyproject.toml
[project]
dependencies = [
    "solamon-profile-loader",
    "pymodbus>=3.6",
    # ...
]

[tool.uv.sources]
solamon-profile-loader = { path = "../profile_loader", editable = true }
```

For pip-only workflows (no uv): `pip install -e packages/profile_loader && pip install -e packages/edge_agent`. The Dockerfile does the same:

```dockerfile
COPY packages/profile_loader /build/profile_loader
COPY packages/edge_agent    /build/edge_agent
RUN pip install /build/profile_loader /build/edge_agent
```

---

## 2. TDD strict (non-negotiable)

Every task in every plan follows this loop:

1. **Red.** Write a failing test. The test name describes the behavior in past tense (`test_decode_returns_kw_after_scale_applied`). One observable behavior per test.
2. **Run red.** Confirm the test fails with the EXPECTED error (function not defined, assertion wrong, exception type, etc.). If it fails for the wrong reason, the test is buggy — fix the test before proceeding.
3. **Green.** Write the minimum code to make the test pass. No "while I'm here" extras. No anticipated-future-need code. YAGNI.
4. **Run green.** Confirm test passes. Re-run the full file's test suite to confirm nothing else broke.
5. **Refactor (optional).** Only when green. Re-run tests after every refactoring step.
6. **Commit.** Atomic commit with a message describing the BEHAVIOR added, not the file changed.

**Implications**:
- No production code without a failing test first.
- Tests verify behavior, not implementation. If you have to mock the thing you're testing, the test is at the wrong level.
- Mock at **system boundaries only** (database, MQTT broker, Modbus client, HTTP client). Inside the boundary, use real objects (real YAML loader, real catalog, real bytes).
- Tiny commits. The git log is the development narrative.

---

## 3. SOLID (concrete application)

### S — Single Responsibility

One file = one reason to change. If a class name needs an "and", split it.

- `profile_loader.catalog.Catalog` → holds metric metadata; that's it.
- `profile_loader.decoders.decode_format` → bytes + format → value; pure function.
- `cloud_app.ingestion.IngestionWorker` → MQTT message → DB row; doesn't validate auth, doesn't render WS.
- `edge_agent.modbus_poller.ModbusPoller` → polls; doesn't write MQTT, doesn't write SQLite.

### O — Open/Closed

Extension via composition, not modification.

- New device profile = new YAML file. Zero code changes in `profile_loader`.
- New custom decoder = new class + one `register_decoder()` call. Zero changes in `decoders.py` core.
- New WS message type = new entry in dispatch table, not a new `if` branch in a god-function.

### L — Liskov substitution

Use Python `Protocol` for boundary contracts. Tests pass fakes that satisfy the Protocol; production passes real adapters. No `class FakeFoo(Foo)` inheritance hacks.

```python
class ModbusClient(Protocol):
    async def read_holding_registers(self, address: int, count: int, slave: int = ...) -> Any: ...
    async def read_input_registers(self, address: int, count: int, slave: int = ...) -> Any: ...
```

### I — Interface segregation

A Protocol exposes only the methods its caller uses. The fingerprint code's `ModbusClient` Protocol has 2 methods, not the 30 of `pymodbus.client.AsyncModbusTcpClient`.

### D — Dependency inversion

High-level modules depend on Protocols, not concrete adapters. The composition root (`__main__.py` / `app.py`) is the ONLY place where concrete classes get instantiated and wired together.

```python
# In edge_agent/__main__.py — composition root
from pymodbus.client import AsyncModbusTcpClient
from edge_agent.poller import ModbusPoller

client = AsyncModbusTcpClient(host=cfg.device_host)
poller = ModbusPoller(client, profile, buffer)  # ModbusPoller depends on Protocol, gets concrete here
```

### Patterns the plans use

| Pattern | Where | Why |
|---------|-------|-----|
| Frozen dataclasses | All value objects (`LogicalMetric`, `Reading`, `FingerprintResult`) | Immutable; trivial equality; no behavior creep |
| Protocols | Module boundaries (Modbus, MQTT, DB, decoder) | Substitution + injection without inheritance |
| Registries | Custom decoders, command dispatchers | Open/Closed |
| Composition root | Each subsystem's `__main__.py` | Single place adapters get wired |
| Pure functions | Decoders, validators, format helpers | Trivial to test |

---

## 4. CI per spec group

Six workflows under `.github/workflows/`, each path-filtered:

| Workflow | Triggers on | Jobs |
|----------|-------------|------|
| `device-library.yml` | `architecture/**`, `packages/profile_loader/**` | ruff, pytest, validate-CLI on committed profile |
| `edge-agent.yml` | `packages/edge_agent/**`, `packages/profile_loader/**` | ruff, pytest, Dockerfile build |
| `cloud.yml` | `packages/cloud_app/**`, `packages/profile_loader/**`, `architecture/**` | ruff, pytest (with Postgres + Mosquitto containers), migration sql lint, Dockerfile build |
| `probe-cli.yml` | `packages/probe_cli/**`, `packages/profile_loader/**` | ruff, pytest, CLI smoke |
| `web-ui.yml` | `packages/web_ui/**` | tsc, eslint, vitest, next build |
| `infrastructure.yml` | `docs/specs/infrastructure/**` | bash -n, cross-reference checks |

A PR touching only `packages/web_ui/` skips Python jobs entirely.

---

## 5. Tech stack pin (per package)

| Package | Stack |
|---------|-------|
| profile_loader | Python 3.12, PyYAML, jsonschema, pytest, pytest-asyncio |
| edge_agent | Python 3.12, pymodbus 3.x, asyncio-mqtt, aiosqlite, structlog, pytest, pytest-asyncio |
| cloud_app | Python 3.12, FastAPI 0.110+, asyncpg, asyncio-mqtt, pydantic v2, bcrypt, PyJWT, pytest, pytest-asyncio, httpx (test client) |
| probe_cli | Python 3.12, pymodbus 3.x, typer, rich, pytest, pytest-asyncio |
| web_ui | Next.js 15, React 19, TypeScript 5.5, Tailwind 4, shadcn/ui, Tremor 3, NextAuth (Auth.js v5), TanStack Query 5, Vitest, Playwright |
| infrastructure | Bash 5, Docker 25+, Caddy 2, Mosquitto 2, Timescale 2.14-pg16, Tailscale, AWS CLI v2 |

Ruff config and pytest config live in the workspace-root `pyproject.toml`; per-package `pyproject.toml` only declares package-specific deps.

---

## 6. Commit message convention

```
<type>(<scope>): <subject>

<body — one or two sentences on the WHY>
```

- `<type>`: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `ci`, `spec`
- `<scope>`: spec-group name in lower-kebab (`device-library`, `cloud`, `edge-agent`, `probe-cli`, `web-ui`, `infrastructure`)

Example:
```
feat(cloud): WS auth via Sec-WebSocket-Protocol header

Echoes back solamon-bearer as the negotiated subprotocol per RFC 6455;
JWT validation reuses the same code path as Authorization-header bearer.
```

---

## 7. Out of scope across all plans

- Continuous-aggregate downsampling (Timescale)
- Site-add API endpoint (post-MVP — bench bootstraps the single site directly)
- Profile linting tool (SOL-14)
- Profile auto-detection (SOL-11)
- Hot reload (SOL-17)
- Schema versioning + migration (SOL-15)
- mTLS for MQTT (post-MVP — moves to AWS IoT Core)
- AWS SSM hybrid for Pi management (SOL-10)
- Multi-tenant isolation
