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
solamon-profile-loader = { workspace = true }
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

## 7. Implementation execution rules (lessons from SOL-20)

These apply to **every plan execution**, not just the conventions a plan should be written to. Use the `superpowers:subagent-driven-development` skill against any plan in this directory; layer these rules on top.

### 7.1 Pre-flight: lint the plan against committed artifacts

**Before dispatching Task 1**, re-read every artifact the plan references (YAML schemas, JSON schemas, OpenAPI specs, migration SQL, etc.) and check for drift between what the plan assumes and what's currently committed. SOL-20 had three plan bugs caught only after Task 5 BLOCKED — they could have been caught here in a single pre-flight pass at zero cost.

Concretely, for each plan, run through:

- For every test fixture YAML/JSON inline in the plan: does it conform to the actual committed schema? (SOL-20 caught: empty `fingerprint.reads` lists violated `minItems: 1`.)
- For every dataclass field declared in the plan: is it consistent with the actual committed YAML? (SOL-20 caught: `expected_range` typed as required but 5 catalog metrics legitimately lack it.)
- For every cross-task dependency: does the order satisfy it? (SOL-20 caught: Task 5's integration test required Task 8's decoder.)
- For every spec citation in the plan (file paths, line numbers, section refs): does it still resolve?

This is one Read pass per artifact. It saves 1+ implementer cycles per bug.

### 7.2 Plan bugs → fix the plan FIRST, then dispatch

When the pre-flight in §7.1 (or a mid-execution discovery) finds a plan bug, **fix the plan in a `docs(plans)` commit BEFORE dispatching the corrected task**. Do NOT bundle the deviation into the implementation commit and chase the plan retroactively. Retroactive plan fixes clutter git history and obscure the "what shipped vs what was intended" trail.

Pattern:

```bash
# Step 1: edit the plan to reflect the corrected approach
git commit -m "docs(plans): retroactive Task N fix — <reason>"

# Step 2: dispatch the implementer against the now-correct plan
# (no deviation in the implementation commit needed)
```

### 7.3 Implementer prompt: "STOP on plan bugs"

Every implementer subagent prompt MUST include this rule explicitly:

> **If you encounter a bug in the plan, in upstream files, or in test infrastructure, STOP and report BLOCKED with the specific bug. Do NOT silently work around it by deviating from the plan.**

SOL-20's Task 5 implementer silently fixed three plan bugs without flagging them. The fixes happened to be correct, but silent deviation breaks the "what shipped vs what was intended" trail. Surface bugs upward; the controller decides how to fix them.

### 7.4 End-to-end smoke task at the END of every plan

Task-level tests only verify what the test fixtures exercise. They cannot catch the gap between what committed YAML actually contains and what the runtime production path expects. SOL-20's `meter_clock` runtime crash was hidden by all 53 task-level tests because the conftest fixture stubbed the clock decoder.

**Every plan adds a final task: "End-to-end smoke against committed artifacts"** — exercises the real production code path with no fixtures, no stubs, against the committed YAML / database / config. Discovers bugs the unit tests cannot reach.

### 7.5 Reviewer dispatch: cost-tier the model

- **Spec compliance reviewer** — haiku is sufficient. Just text-level diff against the plan.
- **Code quality reviewer** — haiku for plan-verbatim code (most tasks); sonnet for tasks that introduced novel logic; **sonnet for the final whole-implementation review** (this is where architectural surprises surface).
- The code-quality margin is low when the plan was prescribed verbatim and spec compliance ✓. Don't escalate model size to feel thorough.

### 7.6 Reviewer prompt: spec full text vs diff only

- **Spec compliance reviewer:** gets the FULL task text from the plan (so it can compare line-by-line).
- **Code quality reviewer:** gets only the diff + the spec citation (file path + section). Saves ~30% reviewer tokens with no quality loss — code reviewers don't need to re-derive the spec; they evaluate the diff against it.

### 7.7 Track deferred items explicitly

If a finding is genuinely deferred (needs external input, hardware verification, future scope), note the SPECIFIC reason in the response doc. **"Deferred because lazy" is not acceptable.** A finding deferred without a real reason is a slop debt that compounds.

Format:

> **#13 — DoW cross-check.** DEFERRED. Needs hardware verification of weekday convention (ISO Mon=1 vs US Sun=1). Tracked as bench Day 1 verification with Johan.

### 7.8 If a finding is rejected, document why

If a reviewer raises a finding that's not actually a problem, REJECT it explicitly with the reason. Don't silently ignore. Future readers / re-reviews benefit from seeing the prior judgment.

Format:

> **#20 — `tuple[float, float]` annotation.** REJECTED. Reviewer's own framing: "fine in modern type-checkers". Python 3.12 + ruff handles correctly. Not a real finding.

### 7.9 Tests directories: NO `__init__.py`

When using pytest's `--import-mode=importlib` (which we set workspace-wide for multi-package monorepo support), `tests/` and `tests/<subdir>/` MUST NOT contain `__init__.py` files. With `__init__.py` present, pytest treats them as regular packages and namespaces collide — both `packages/profile_loader/tests/conftest.py` and `packages/cloud_app/tests/conftest.py` get registered as `tests.conftest` and pytest crashes with `ValueError: Plugin already registered under a different name`.

The correct pattern for monorepo test layouts:

```
packages/X/tests/
├── conftest.py              # ✓ no __init__.py at sibling level
├── unit/
│   └── test_foo.py          # ✓ no __init__.py
└── integration/
    └── test_bar.py          # ✓ no __init__.py
```

Caught during cloud Task 3 — the cloud_app conftest.py collided with profile_loader's at `pytest packages/` time. Removing all 4 `__init__.py` files under `tests/` resolved it. Going forward, no plan should include `Create: packages/X/tests/__init__.py` steps.

### 7.10 Token budget reality

A 12-task plan executed via subagent-driven-development costs ~2M tokens (SOL-20 actual). Plan accordingly:

- Tasks: ~80-150K tokens each (implementer + 2 reviews + verification)
- Final whole-implementation review: ~100K tokens
- Fix subagents (when needed): ~80-150K tokens each

For SOL-8 (cloud, 18 tasks + integration tests via testcontainers), expect ~3-4M tokens. Pace accordingly across sessions.

---

## 8. Out of scope across all plans

- Continuous-aggregate downsampling (Timescale)
- Site-add API endpoint (post-MVP — bench bootstraps the single site directly)
- Profile linting tool (SOL-14)
- Profile auto-detection (SOL-11)
- Hot reload (SOL-17)
- Schema versioning + migration (SOL-15)
- mTLS for MQTT (post-MVP — moves to AWS IoT Core)
- AWS SSM hybrid for Pi management (SOL-10)
- Multi-tenant isolation
