# Web UI spec — review response

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)
**Review:** [`review-2026-05-02.md`](review-2026-05-02.md)
**Status:** addressed 2026-05-03

Per the standing rule (validate first, apply second), every finding was cross-checked against the actual current state of the cloud, edge-agent, and device-library specs before any change was made. Three findings were rejected as wrong, two were applied with adjusted scope; the rest were applied as written.

---

## Validation table

| # | Verdict | Notes |
|---|---------|-------|
| 1 — WS message shape | **VALID** | Real bug. `live-data.md` example accessed `msg.metric` / `msg.value` / `msg.time`; the dispatcher passes the whole envelope, so fields live under `msg.data`. Fixed. |
| 2 — Two contradictory `useDeviceLiveStream` impls | **VALID** | §4 was per-call `new WebSocket`; §4.3 was singleton-per-`device_id`. Acceptance criterion locks multiplexing. §4 collapsed into a single multiplexing implementation; §4.3 reduced to a pointer. |
| 3 — `halted_blocks` not in cloud heartbeat schema | **PARTIALLY VALID** | Edge agent already publishes the field ([`../edge-agent/mqtt-publisher.md` §7](../edge-agent/mqtt-publisher.md)) but `mqtt-contracts.md §5.1` didn't document it. Added to the contract — no edge-agent change needed. |
| 4 — `<DemandTile>` peak timestamp blocked by cloud schema | **INVALID (rejected)** | Reviewer claimed `active_power_demand_max_timestamp` is unreachable because `timeseries.reading.value` is `DOUBLE PRECISION`. But [`../cloud/ingestion-worker.md` §4.1 lines 100-101](../cloud/ingestion-worker.md) explicitly routes non-numeric metrics (datetime, enum, string, bool, bitfield) to `app.device_snapshot.metrics` JSONB **only**. The snapshot is the authoritative store for datetimes; `<DemandTile>` reads from the snapshot. No fix needed. |
| 5 — `last_publish_error` and 503 are inventions | **PARTIALLY INVALID** | Reviewer was wrong about `last_publish_error`: it IS a column in [`../cloud/migrations/0001_initial.sql:197`](../cloud/migrations/0001_initial.sql) and a field on the OpenAPI `ControlCommand` schema. 503 IS documented in [`../cloud/api-surface.md §4.4`](../cloud/api-surface.md). The valid sub-finding: web-ui's "see cloud spec §3.4" cross-reference was broken — fixed (now points to `cloud/control-relay.md §3` and `api-surface.md §4.4`). |
| 6 — Power-units gap | **VALID (note only)** | Catalog scale fix already landed in [`../../architecture/profiles/acuvim_l.yaml`](../../architecture/profiles/acuvim_l.yaml) per device-library review #1. Added a comment in `live-data.md` documenting the dependency: `formatKw(value)` assumes pre-scaled kW arriving from cloud. |
| 7 — WS auth mechanism not in cloud spec | **INVALID (rejected)** | Reviewer's quote ("After authentication (JWT in Sec-WebSocket-Protocol header **or `?token=` query string**)") doesn't exist in current `api-surface.md`. Line 223 of api-surface.md already says **"only" — the `?token=` query string variant is explicitly disallowed**. Reviewer was reading an older version. No fix needed. |
| 8 — `apiServer` signature mismatch | **VALID** | `auth.md §3.1` had a generic `apiServer<T>(path, init)` fetch wrapper; `live-data.md §2` had `apiServer(session).getSite(slug)` SDK-style. Aligned to the SDK shape (`openapi-fetch`-backed) since OpenAPI codegen produces named methods. |
| 9 — Pagination component vs cursor API | **VALID** | shadcn `<Pagination>` assumes page numbers; cloud uses `?cursor=`. Replaced with `<LoadMoreButton>` in `components.md`; removed `<Pagination>`. Updated pages.md references. |
| 10 — Snapshot replace vs merge | **VALID** | `api-surface.md §5.1` didn't pin "full state, always". Pinned: cloud sends the full post-merge snapshot on every `snapshot` WS message; web-ui replace handler is correct. Documented in both specs. |
| 11 — Caddy log redaction for `Sec-WebSocket-Protocol` | **VALID** | Added redaction note in both `live-data.md §4.2` and `api-surface.md §5.1`; will land as concrete Caddyfile directive in `infrastructure/caddy-and-dns.md` §3. |
| 12 — Multi-tab control race | **VALID (documented bound)** | Documented in `pages.md §6` (control panel): "Pi processes commands serially; concurrent issuance from multiple sessions results in last-write-wins on the device". Not a UI fix. |
| 13 — XSS exposes `session.accessToken` | **VALID** | Added §7 paragraph in `auth.md` flagging the XSS-as-token-exfil exposure and the mitigations short of a full HttpOnly migration (strict CSP, sanitiser-by-default, audit before adding any unsanitised-render path). |
| 14 — Server-side `Sec-WebSocket-Protocol` parsing rules | **VALID** | Pinned in `api-surface.md §5.1`: 7-rule parse procedure including which close codes map to which failure mode. |
| 15 — `react-syntax-highlighter` bundle | **VALID** | Lazy-load via `next/dynamic` documented in `pages.md §9` and `live-data.md §7` (code-splitting requirements). Verified Next.js route-level splitting moves it to a separate chunk. |
| 16 — `<RelativeTime>` per-instance interval churn | **VALID** | Replaced with single broadcast tick + `RelativeTimeTickContext` in `components.md §4`. |
| 17 — Enum integer rendering | **VALID** | Pinned: cloud snapshot endpoint resolves enums to symbolic strings; web-ui renders directly. Documented in both `components.md §5` and `api-surface.md §5.1`. |
| 18 — Status pill colour mapping | **VALID** | Added explicit five-row mapping table to `components.md §5`. |
| 19 — `<PowerFactorCard>` mixed-sign warning | **VALID** | Reworded — "check load characteristics or CT polarity" + cross-check with per-phase active-power signs. |
| 20 — NextAuth v5 GA | **TRIVIAL** | Added "pin a GA release" note in `auth.md §1`. |
| 21 — No login rate limiting | **VALID** | Flagged in `auth.md §8` with the Caddy `rate_limit` mitigation path. |
| 22 — WS close codes | **VALID** | Added the close-code table in `live-data.md §4.1`. |
| 23 — SDK method naming | **VALID** | Set explicit `operationId` on every path in `openapi.yaml`. |
| 24 — Dup `<DataFreshness>` description | **VALID** | Cross-referenced from `components.md §4` to `live-data.md §6.1` and vice versa. |
| 25 — 200 ms first-paint target | **VALID** | Softened to "first values visible at first paint when same-region" in `live-data.md §8`; documented the bench-context measurement. |
| 26 — `API_BASE` / `WS_BASE` env vars | **VALID** | Added §9 Configuration table in `live-data.md`. |
| 27 — Bundle budget | **VALID** | Revised: dashboard route < 350 kB, login + admin < 150 kB. Documented mandatory code-splitting strategy in `live-data.md §7`. |
| 28 — Token rotation reconnect | **VALID** | Added explicit §4.4 "Token rotation across reconnects" in `live-data.md`. |
| 29 — Clock-skew check | **TRIVIAL** | Documented as UX-only in `auth.md §7`. |
| 30 — Empty state for fresh site | **VALID** | Added "fresh site, never-seen-telemetry" empty state in `pages.md §12.3`. |
| 31 — `<SiteSelector>` tone | **VALID** | Consolidated in `components.md §4` — explicit MVP-vs-eventual split. |
| 32 — `<Pagination>` unused | **VALID (follow-on of #9)** | Removed from `components.md §4`. |
| 33 — `react-window` for metric grid | **VALID** | Committed upfront in `pages.md §7` rather than "if Tremor falls over". |
| 34 — Hex render allowlist | **VALID** | Added explicit field allowlist table in `pages.md §9`. |
| 35 — SDK build pipeline | **VALID** | Added §10 "SDK build pipeline" in `live-data.md` (prebuild step, named `operationId`s). |

---

## What changed

### Web-ui specs

- **[`live-data.md`](live-data.md)**: §3 fixed message-shape example; §4 collapsed to multiplexing-singleton implementation; §4.1 added close-code table; §4.2 added log-redaction note; §4.4 added token-rotation paragraph; §5 fixed cross-references; §6.1 cross-linked to `<DataFreshness>`; §7 revised bundle budget + mandatory splitting; §8 softened first-paint; §9 added Configuration; §10 added SDK build pipeline; §11 expanded cross-references.
- **[`components.md`](components.md)**: `<DemandTile>` and `<EdgeHealthCard>` rows clarified data sources; `<PowerFactorCard>` mixed-sign reworded; `<RelativeTime>` updated to single broadcast tick; `<SiteSelector>` consolidated; replaced `<Pagination>` with `<LoadMoreButton>`; status pill mapping table; enum rendering pin; `<DataFreshness>` cross-link.
- **[`pages.md`](pages.md)**: `/sites/{slug}/control` "load more" wording; `/sites/{slug}/devices/{id}` Commands tab cursor-paginated; metric grid commits to `react-window`; profile detail page hex allowlist + `next/dynamic` for syntax highlighter; §12.3 fresh-site empty state.
- **[`auth.md`](auth.md)**: §1 pin GA NextAuth; §3 SDK-shaped `apiServer` / `useApiClient` (`openapi-fetch` backed); §7 XSS posture + clock skew; §8 login rate-limit gap.

### Cloud-side propagation

- **[`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md)**: §5.1 heartbeat schema adds `halted_blocks`.
- **[`../cloud/api-surface.md`](../cloud/api-surface.md)**: §5.1 pins `Sec-WebSocket-Protocol` parse rules + close-code semantics + log redaction; pins snapshot full-state contract; pins enum-as-symbolic-string in snapshot.
- **[`../cloud/openapi.yaml`](../cloud/openapi.yaml)**: every path gets an explicit `operationId`; commands POST adds 503 response; commands list adds `cursor` query param.

### Not changed (deliberately)

- `<DemandTile>` — datetime metrics are servable via the snapshot path (#4 reviewer error).
- `Sec-WebSocket-Protocol` "only" claim in web-ui — already in cloud spec (#7 reviewer error).
- `last_publish_error` column / OpenAPI field / 503 response — all already exist (#5 partial).
