# STATUS — drop-in here

Single source of truth for **where we are right now**. Read this first if you're picking up work — everything else (CLAUDE.md, OVERVIEW.md, README.md) is project context that doesn't change frequently.

**Last updated:** 2026-05-07

---

## Phase

**Build phase.** All design / spec / plan work is committed. Implementation is in flight.

```
Phase 1 (done)   ─  Discovery + Architecture (drafts) + Glossary
Phase 2 (done)   ─  Detail specs (6 groups) + reviews + responses
Phase 3 (done)   ─  Implementation plans (6 + conventions doc)
Phase 4 (now)    ─  Implementation, plan-by-plan
Phase 5          ─  Bench rehearsal (Pi + cloud end-to-end against real Acuvim)
Phase 6          ─  First production site
```

## What's shipped (phase 4 progress)

| Linear | Plan | Package | Tests | Status |
|--------|------|---------|-------|--------|
| **SOL-20** Device library | [`docs/superpowers/plans/2026-05-03-device-library.md`](docs/superpowers/plans/2026-05-03-device-library.md) | `packages/profile_loader/` (8 src files, 11 test files) | **53 / 53** | ✅ Complete + post-implementation review fixes |
| **SOL-8** Cloud | [`docs/superpowers/plans/2026-05-03-cloud.md`](docs/superpowers/plans/2026-05-03-cloud.md) | `packages/cloud_app/` (11 src files, 5 test files) | **28 / 28** within cloud_app (81 / 81 across both packages) | 🔄 5 of 19 tasks done — **next is Task 6** |
| SOL-7 Edge agent | [`docs/superpowers/plans/2026-05-03-edge-agent.md`](docs/superpowers/plans/2026-05-03-edge-agent.md) | `packages/edge_agent/` | — | ⏸ Not started |
| SOL-18 Probe CLI | [`docs/superpowers/plans/2026-05-03-probe-cli.md`](docs/superpowers/plans/2026-05-03-probe-cli.md) | `packages/probe_cli/` | — | ⏸ Not started |
| SOL-9 Web UI | [`docs/superpowers/plans/2026-05-03-web-ui.md`](docs/superpowers/plans/2026-05-03-web-ui.md) | `packages/web_ui/` | — | ⏸ Not started |
| SOL-21 Infrastructure | [`docs/superpowers/plans/2026-05-03-infrastructure.md`](docs/superpowers/plans/2026-05-03-infrastructure.md) | `docs/specs/infrastructure/scripts/` (already authored) | — | ⏸ Bench rehearsal phase |

**Total tests:** 81 passing across both packages (`pytest packages/` from repo root). Run time ~90 s (most of that is testcontainers spinning up real Postgres for cloud_app integration tests).

## Cloud (SOL-8) — task progress

The plan has 19 tasks; 5 are committed to master.

| Task | Status | Commit |
|------|--------|--------|
| 1. Package skeleton + composition root stub | ✅ | `f950fb9` |
| 2. Bundle migrations + openapi.yaml | ✅ | `d68f376` |
| 3. DB pool + migration runner (testcontainers) | ✅ | `edbb337` |
| 4. bcrypt + JWT pure functions | ✅ | `e28dbcc` |
| 5. Pydantic models matching openapi.yaml | ✅ | `6a49317` |
| **6. FastAPI app skeleton + auth router + dependency** | **🔜 next** | — |
| 7. Sites + devices endpoints | pending | — |
| 8. Snapshot + readings endpoints | pending | — |
| 9. Health + catalog + edge config endpoints | pending | — |
| 10. MQTT client wrapper + payload validation | pending | — |
| 11. Telemetry ingestion worker | pending | — |
| 12. Control relay (REST POST → MQTT + ack handler) | pending | — |
| 13. Heartbeat handler | pending | — |
| 14. WebSocket fan-out | pending | — |
| 15. TTL reaper background task | pending | — |
| 16. Seed CLI | pending | — |
| 17. Composition root + Dockerfile | pending | — |
| 18. GitHub Actions CI | pending | — |
| 19. End-to-end smoke (real Postgres + Mosquitto) | pending | — |

## How to pick up work

### 0. Read these (in order)

1. **This file** — current state.
2. [`docs/superpowers/plans/2026-05-03-conventions.md`](docs/superpowers/plans/2026-05-03-conventions.md) — execution discipline. **§7 is non-negotiable** (pre-flight, plan bugs fixed in plan first, no `tests/__init__.py`, etc.).
3. [`CLAUDE.md`](CLAUDE.md) — project decisions + device facts. Auto-loaded; don't re-read each task.
4. The active plan file (currently [`docs/superpowers/plans/2026-05-03-cloud.md`](docs/superpowers/plans/2026-05-03-cloud.md)).

### 1. Verify the local environment

```bash
docker --version                                       # need Docker Desktop running for cloud testcontainers
.venv/Scripts/python.exe --version                     # 3.12.x expected
.venv/Scripts/python.exe -m pytest packages/ -q       # should report 81 passed
```

If any fail, see "Environment notes" below.

### 2. Continue task-by-task via subagent-driven-development

The execution skill is `superpowers:subagent-driven-development`. The pattern (per conventions §7):

1. Read the next task's full text from the plan.
2. **Pre-flight**: lint the plan against committed artifacts (catch drift before dispatching). For cloud, this was done at start; spot-check before each task.
3. Dispatch implementer with the FULL task text + the §7.3 STOP-on-plan-bugs rule explicit.
4. Verify the commit landed; run `pytest packages/`.
5. Spec compliance review (haiku).
6. Code quality review (haiku for plan-verbatim work; sonnet for novel logic).
7. If reviewers find real issues → dispatch fix subagent → re-review.
8. Mark complete in TodoWrite → next task.

### 3. Push at meaningful milestones

Push when a logical group is done — e.g., after Tasks 1-5 ship cleanly. Don't push every commit individually; don't sit on >10 unpushed commits.

## Environment notes

- **Python interpreter:** `.venv/Scripts/python.exe` (Windows path; the venv was created with uv). The venv does NOT have `pip` directly — use `uv pip install -e "packages/X[dev]"` to install/refresh.
- **Pytest mode:** `--import-mode=importlib` (configured in workspace `pyproject.toml`). `tests/` and `tests/<subdir>/` MUST NOT contain `__init__.py` — see conventions §7.9.
- **Docker Desktop required** for cloud_app integration + e2e tests. `timescale/timescaledb:2.26.4-pg16` and `eclipse-mosquitto:2` already pulled.
- **Workspace path deps**: `[tool.uv.sources] solamon-profile-loader = { workspace = true }` is the canonical pattern (see conventions §1).
- **Branch:** `master` directly. Marius authorised on-master execution for SOL-20 + SOL-8. Push when stable.

## Recent process learnings (post-SOL-20 retro, applied to SOL-8)

These are baked into [conventions §7](docs/superpowers/plans/2026-05-03-conventions.md#7-implementation-execution-rules-lessons-from-sol-20). Quick recap:

- **§7.1 Pre-flight** caught 6 cloud-plan bugs before Task 1 dispatched (catalog YAML wrapper shape, missing `expected_range` on enum/datetime metrics, `ControlCommand.type` required-vs-optional, TTL reaper SQL syntax, `CommandAckPayload.readback_at` missing, `Health.db/mqtt` Literal vs string drift). All fixed in `bee250f`.
- **§7.3 STOP rule** worked: cloud Task 5 implementer correctly halted on missing `pydantic[email]` dependency (real plan bug). Wrong fix would have been silent install. Right fix was reporting BLOCKED, controller updating plan + pyproject (`a8b4320`), then re-dispatching.
- **§7.9 No `tests/__init__.py`** — when cloud_app's tests/conftest.py landed, it collided with profile_loader's at `pytest packages/` time. Fix: remove all `tests/__init__.py` files (`0ad172e`).
- **Plan-bug-then-dispatch cadence**: every plan correction commits as `docs(plans):` or `fix(...):` BEFORE the next implementer is dispatched. Avoids retroactive cleanup.

## Outstanding plan-level concerns

| Concern | Action |
|---------|--------|
| Cloud plan Task 13 has the same title as Task 12's heartbeat handler | The duplicate is benign — both refer to the heartbeat work; Task 13 is fine to merge into Task 12 in practice |
| `[tool.uv.sources] testcontainers[postgresql,mqtt]` — uv warns no `postgresql` extra exists | testcontainers re-organised; functionality works (`from testcontainers.postgres import PostgresContainer` resolves). Drop the `[postgresql,mqtt]` extras at next refresh; track for clean-up. |
| End-to-end (Task 19) requires `MosquittoContainer` from `testcontainers.mqtt` | Verify import resolves before dispatching Task 19. May need `testcontainers[mqtt]` to be the installed extra. |

## Key file index for new agents

| Path | Purpose |
|------|---------|
| `STATUS.md` | This file. Current state. |
| `CLAUDE.md` | Auto-loaded project context. Decisions, device facts, conventions. |
| `OVERVIEW.md` | Project purpose + architecture summary (high-level). |
| `README.md` | Public repo front door. |
| `GLOSSARY.md` | Acronyms, vendors, protocols, in-house jargon. |
| `docs/superpowers/plans/2026-05-03-conventions.md` | Execution discipline §7 (mandatory). |
| `docs/superpowers/plans/2026-05-03-cloud.md` | Active plan. |
| `docs/specs/cloud/` | Cloud spec group (data-model, api-surface, mqtt-contracts, ingestion-worker, control-relay, openapi.yaml, migrations/0001_initial.sql). |
| `architecture/logical_metrics.yaml` + `profiles/acuvim_l.yaml` | Committed device library data. |
| `packages/profile_loader/` | Shipped (SOL-20). |
| `packages/cloud_app/` | In progress (SOL-8). |

## Memory

Long-lived per-agent memory is at `~/.claude/projects/d--Repositories-solamon/memory/`. Key file:

- `plan_execution_discipline.md` — the controller rules. Read on session start; matches conventions §7.
