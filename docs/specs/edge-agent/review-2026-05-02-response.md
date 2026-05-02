# Edge-agent spec review — response

**Reviewed:** [`review-2026-05-02.md`](review-2026-05-02.md) — 36 findings (7 critical, 13 major, 16 minor / positive notes)
**Author:** Marius (with Claude)
**Date:** 2026-05-02
**Status:** All findings addressed in this commit. Five judgment calls flagged.

Each finding validated independently before applying.

---

## Critical

### #1 — Units gap propagates straight through the poller

**Validity:** Confirmed (meta — already addressed via device-library #1). The edge agent has no units-fix path; it trusts the profile.

**Resolution:** Added a "Hard prerequisite — units correctness" callout to `modbus-poller.md` §3 explaining that the bench Day 3 multimeter cross-check is the only mechanism that catches missing-scale bugs. The actual fix (`scale: 0.001` in `acuvim_l.yaml`) lives in the device-library commit.

### #2 — In-memory `recent_commands` lost on restart

**Validity:** Confirmed.

**Resolution chosen — judgment call: defer + document.** Reasoning:
- MVP has exactly one command type — `set_value` of `demand_window_minutes` — and `set_value` is idempotent. Re-execution after restart writes the same value to the same register; no harm.
- Adding SQLite persistence now is non-trivial (transactional ack flow, sweeper, recovery semantics).
- Deferring with a tracked Linear issue ([SOL-24](https://linear.app/solamon/issue/SOL-24)) and an explicit "MVP-only safety" callout in `command-subscriber.md` §5 documents the constraint loudly so the next contributor doesn't accidentally add `start`/`stop`/`reset_counter` without persisting first.

**Changes:**
- `command-subscriber.md` §5 — explicit warning callout block.
- New Linear issue: [SOL-24 — Edge agent — persistent command idempotency cache](https://linear.app/solamon/issue/SOL-24).

### #3 — Replay sweeper references state that doesn't exist

**Validity:** Confirmed. The sweeper called `unmark_in_flight()` on a buffer schema that had no `in_flight` state to unmark.

**Resolution chosen — judgment call: delete §5 entirely.** Reasoning:
- The publish loop's natural fetch-publish-mark cycle re-fetches any unpublished row on every 0.5-second tick. A separate sweeper would have been a no-op against the existing schema.
- Adding an `in_flight_since` column to make the sweeper meaningful is solving a problem we don't have. If a future revision needs row-level in-flight tracking (e.g., very large publish batches), the sweeper can return.

**Changes:**
- `mqtt-publisher.md` §5 — replaced with a "(No replay sweeper)" section explaining why and what would trigger re-introduction.

### #4 — Heartbeat enum doesn't include `"fault"`

**Validity:** Confirmed inconsistency. Architecture said cloud sees site as `"fault"` on fingerprint mismatch; payload only emits `online`/`offline`.

**Resolution chosen — judgment call: heartbeat stays binary; expose `halted_blocks` instead.** Reasoning:
- The agent is alive on fingerprint mismatch — it just can't poll the device. `status: "online"` is correct for the agent's perspective; conflating "agent online" with "device functional" is the bug.
- Adding `halted_blocks: list[str]` to the heartbeat payload tells the cloud "this Pi is alive but its device's data isn't flowing for these blocks". The operator UI renders that as "fingerprint mismatch" or "device fault" without needing a separate enum value.
- A separate `solamon/{slug}/alarms/...` topic for richer events is post-MVP.

**Changes:**
- `architecture.md` §2.2 (metrics include `halted_blocks`), §3.1 step 7 (mismatch behaviour), §4 (heartbeat description).
- `mqtt-publisher.md` §7 (heartbeat payload includes `halted_blocks`), §7.2 (status enum binary).
- `modbus-poller.md` §5 (halted-block visibility note).

### #5 — `format_tolerance` referenced but not in schema

**Validity:** Confirmed.

**Resolution:** hardcoded tolerance in the loader (float-eps relative for floats, exact for ints, byte-eq for ASCII). NOT a profile field.

**Changes:**
- `command-subscriber.md` §4 — `values_equal(rb_value, value)` (no tolerance arg).
- `profile-schema.md` §5 — explicit "tolerance is hardcoded in the loader, not a profile field" note.

### #6 — `validate_control` API contract conflict

**Validity:** Confirmed. profile-schema.md said returns bool; command-subscriber.md said raises.

**Resolution:** raise-on-invalid wins. Caller carries the exception's message string into the failed ack — better UX than a bool.

**Changes:**
- `profile-schema.md` §7.1 — explicit "raises ValidationError on bad input. Returns None on success" docstring + note about the contract change.
- `command-subscriber.md` §3 — comment updated to reflect raise semantics.

### #7 — Timestamp UTC-awareness not enforced

**Validity:** Confirmed real bug. `datetime.now()` is timezone-naive; pasting `"Z"` produces malformed local-time-asserting-UTC.

**Resolution:** introduced `now_utc()` helper everywhere; documented in `architecture.md` §4 and `mqtt-publisher.md` §7.1.

**Changes:**
- `architecture.md` §4 — `now_utc()` helper definition + naked `datetime.now()` forbidden.
- `mqtt-publisher.md` §7.1 — same definition for code locality.
- `mqtt-publisher.md` §3.3 — `format_utc(timestamp)` in the telemetry payload builder.
- `modbus-poller.md` §4.1 — same helper for the SQLite buffer's `time` column.
- `command-subscriber.md` §4 — readback timestamps use `now_utc()`.
- `architecture.md` §3.1 step 0 — startup verifies `timedatectl` shows NTP sync; fails after 2.5 min of un-synced wall clock.

---

## Major

### #8 — Heartbeat task in two places

**Validity:** Confirmed. Architecture described it as a top-level task; mqtt-publisher described it inside the MQTT loop.

**Resolution:** the MQTT-loop version is correct (no broker → no heartbeat → LWT covers liveness). Updated `architecture.md` §2.1 table to remove "standalone heartbeat task" claim and point at `mqtt-publisher.md §7`.

### #9 — Bootstrap token rotation path

**Validity:** Confirmed. After cloud rotates the secret, the bootstrap.yaml bearer goes stale beyond the 24-hour grace.

**Resolution:** documented that the agent overwrites `/etc/solamon/bootstrap.yaml.bearer_token` from the response's `mqtt.password` field after every successful refresh.

**Changes:** `config-loader.md` §6.

### #10 — Dangling `../infrastructure/pi-install.md` references

**Validity:** Confirmed. The folder doesn't exist.

**Resolution:** changed the cross-references to "[SOL-21] (infrastructure spec, TBD)" until that group is written.

**Changes:** `config-loader.md` §2.

### #11 — `lib/profile_loader/` has no spec doc

**Validity:** Confirmed. The loader is referenced by edge agent + cloud + probe CLI; previously specified only as a Python-API sketch buried in profile-schema.md §7.

**Resolution chosen — judgment call: significantly expand profile-schema.md §7 rather than create a new `docs/specs/lib/` folder.** Reasoning:
- The loader is part of the device-library group (logical metric catalog → profile schema → loader semantics is one coherent contract).
- Splitting it into a third top-level `lib/` group would fragment a contract that's already at the right home.

**Changes:** `profile-schema.md` §7 expanded into a full loader spec — API surface, registered decoders, validation strategy, test acceptance. Now ~3× longer with concrete API definitions for Profile, Catalog, FingerprintResult, ValidationError, DecodeError, CustomDecoder.

### #12 — `device.id` change requires manual restart

**Validity:** Confirmed. Config refresh updates the cache only; in-memory profile not swapped.

**Resolution:** added `config-loader.md` §4.1 listing all "operator must restart" cases (profile change, device.id change, catalog change, Modbus host change, hardware replacement) and the deploy procedure for each. Until SOL-17 (hot reload) ships, this is the operator runbook.

### #13 — No re-fingerprint on Modbus reconnect / device replacement

**Validity:** Confirmed for the rare hot-swap case.

**Resolution:** documented in `architecture.md` §3.1 step 7 — device replacement requires `docker restart solamon-edge`. Re-fingerprint-on-reconnect is post-MVP polish.

### #14 — `readback_register` has no `fc` field

**Validity:** Confirmed. Schema only had `address`, `format`; the code spec assumed FC03.

**Resolution:** added `fc` field to `readback_register` schema (default 3, allowed values [3, 4]). Code in `command-subscriber.md` §4 reads `getattr(control_spec.readback_register, "fc", 3)` and dispatches correctly.

**Changes:**
- `architecture/profiles/profile.schema.json` — `fc` added to `readback_register` properties.
- `profile-schema.md` §5 — note in YAML example.
- `command-subscriber.md` §4 — dispatch logic.

### #15 — Modbus error counter per-block vs global

**Validity:** Confirmed inconsistency between specs.

**Resolution:** **per-block counters with a global aggregator.** The logical metric `edge_modbus_errors_per_minute` published as telemetry is the global sum; per-block counters expose in heartbeat for diagnostics.

**Changes:**
- `architecture.md` §2.2 — metrics list shows both per-block (`modbus_errors[block_name]`) and global (`modbus_errors_total`).

### #16 — Halted block has no operator signal

**Validity:** Confirmed.

**Resolution:** added `halted_blocks: list[str]` to the heartbeat payload. The operator UI renders "energy block halted after 10 consecutive Modbus errors" without needing SSH access. Combined with #4's resolution.

**Changes:** `mqtt-publisher.md` §7, `modbus-poller.md` §5.

### #17 — Pi NTP / clock drift

**Validity:** Confirmed.

**Resolution:** added `architecture.md` §3.1 step 0 — startup verifies `timedatectl show -p NTPSynchronized --value` returns "yes" before proceeding. Five-retry / 2.5-minute window before exit-1.

### #18 — `INSERT OR IGNORE` masks PK collisions silently

**Validity:** Confirmed. Same-millisecond-timestamp collisions could silently drop data.

**Resolution chosen — judgment call: include `block_name` in the dedup key on BOTH the Pi SQLite buffer AND the cloud Reading hypertable.** Reasoning:
- Today every logical metric is mapped from exactly one block per profile, so `block_name` in the key is effectively redundant.
- For future-proofing (a device variant that publishes the same logical metric from two different blocks), `block_name` makes the dedup unambiguous.
- Cost is one extra column in the index — trivial.
- Matching keys end-to-end keeps Pi-side and cloud-side dedup symmetric.
- Also added a sanity log on `total_changes` mismatch in the SQLite buffer write to catch the very rare "two readings within the same millisecond from clock-jump-backward via NTP step" scenario.

**Changes:**
- `modbus-poller.md` §4 — `block_name` in PK + `total_changes` sanity log.
- `architecture/profiles/profile.schema.json` — no change needed.
- `cloud/migrations/0001_initial.sql` — `idx_reading_unique` extended to include `block_name`.
- `cloud/data-model.md` §3.11 — explanation.
- `cloud/ingestion-worker.md` §4.1 + §4.2 — ON CONFLICT clause + dedup explanation.

### #19 — `now().precision` unspecified

Resolved by #7's `now_utc()` helper that pins `timespec="milliseconds"`.

### #20 — atomic_write_cache permissions / ownership

**Validity:** Minor.

**Resolution:** documented in `config-loader.md` §2 — agent runs as `solamon` user, bootstrap file is `solamon:solamon` mode `600`.

---

## Minor

### #21 — Double-counting prose tightening

Tightened error-handling table in `modbus-poller.md` §5 — explicit note that `result.isError()` doesn't raise, so the inner branch and outer except are mutually exclusive (no double-count path).

### #22 — `readback_fc` dead variable

Resolved by #14 (the variable is now used to dispatch FC03 vs FC04 readback).

### #23 — `unfiltered_messages()` redundant with topic filter

**Resolution:** switched to `client.messages_for_topic(topic_filter)` — direct filtered iteration, no second-pass topic check in `command_loop`.

**Changes:** `mqtt-publisher.md` §2 + `command-subscriber.md` §2.

### #24 — ASCII control writes in readback path

No ASCII writes in MVP. Documented; re-evaluate when an ASCII control register surfaces.

### #25 — `httpx.AsyncClient(timeout=30.0)` for config fetch

Bumped to 60.0 s in `config-loader.md` §3 with a comment about marginal LTE.

### #26 — Subscription re-issued on reconnect

Documented in `mqtt-publisher.md` §2 — `asyncio-mqtt` re-subscribes automatically across reconnects when `clean_session=False`; explicit subscribe is mostly for the first connection and is harmlessly idempotent on the broker.

### #27 — Crash-loop limits at systemd level vs Docker

**Validity:** Confirmed real bug. systemd protects dockerd, not containers.

**Resolution:** `architecture.md` §6 rewritten to use Docker compose's `restart: on-failure:5` policy. systemd ratelimit applies to the daemon, not the agent container.

### #28 — Heartbeat retain alignment ✓

Positive note. No action.

### #29 — `parse_command_payload` validation depth

**Resolution:** specified Pydantic against the cloud's command schema (`CommandPayload.model_validate_json(...)`).

**Changes:** `command-subscriber.md` §2.

### #30 — `recent_commands` cache size

Documented in `command-subscriber.md` §5 — 1000 × 5 min = ~3.3 cmd/s sustained, wildly more than MVP.

### #31 — Buffer ring drops unpublished rows older than 7 days

**Resolution:** added an operator runbook note in `mqtt-publisher.md` §6 — "if cloud has been offline >5 days, expect data loss; check buffer depth before extending the outage".

### #32 — Subscription topic uses `device.id` UUID — multi-device

Documented in `command-subscriber.md` §1 — single-device-id topic is correct for MVP; multi-device-per-Pi (SOL-16) becomes wildcard subscription with per-message dispatch.

### #33 — Profile auto-detection deferred ✓

Positive note. No action.

### #34 — Bearer redacted but not MQTT password explicitly

Documented in `config-loader.md` §6 — bearer-token-and-MQTT-password are deliberately the same in MVP; future split (post-mTLS) revisits log redaction.

### #35 — Modbus client serialised — control-write latency note

Documented in `command-subscriber.md` §2 — worst-case ~5 s extra latency when a poll is in flight at the moment a command arrives.

### #36 — `received_at` for command not specified

**Resolution:** the parser injects `cmd.received_at = now_utc()` at MQTT-message arrival time. Documented in `command-subscriber.md` §2.

---

## Summary

- **36 findings, 36 addressed.**
- **Five judgment calls** flagged (#2 defer-with-issue, #3 delete-the-sweeper, #4 heartbeat-stays-binary, #11 expand-existing-spec, #18 add-block-name-to-PK).
- **One new Linear issue** filed: [SOL-24 — Persistent command idempotency cache](https://linear.app/solamon/issue/SOL-24).
- **Cross-cutting impact** on cloud spec group (block_name in PK / dedup) and device-library (loader API expanded, readback_register.fc added).

The biggest single risk identified — **#1 (units propagation)** — is already mitigated upstream via the device-library #1 fix, and the bench Day 3 multimeter cross-check provides definitive empirical verification.

The next-biggest — **#7 (UTC timestamp bug)** — is now systematically prevented via the `now_utc()` helper + startup NTP-sync check + the explicit "naked `datetime.now()` is forbidden" rule. This category of bug is hard to spot in the field; getting it right at spec time pays off forever.
