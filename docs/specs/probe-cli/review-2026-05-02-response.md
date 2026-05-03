# Probe-CLI spec review — response

**Reviewed:** [`review-2026-05-02.md`](review-2026-05-02.md) — 20 findings (2 critical, 8 major, 10 minor)
**Author:** Marius (with Claude)
**Date:** 2026-05-02
**Status:** All findings addressed via a clean rewrite of the README + a new JSON Schema artifact. Three judgment calls flagged.

Each finding validated independently before applying.

---

## Critical

### #1 — First-match-wins fingerprint mis-identifies non-WEB Acuvim II as Acuvim L

**Validity:** Confirmed. Original spec said "Trying acuvim_ii.yaml: skipped (acuvim_l already matched)" — that's a silent mis-identification waiting to happen.

**Resolution:** `find_matching_profile` now runs ALL profile fingerprints, collects all matches with confidence levels, and:

- Single match → that profile, exit 0/1.
- Multiple matches with `positive_fingerprint` → highest wins.
- Multiple matches at the same confidence → report ambiguous; exit 2; operator must disambiguate via device label / cross-check evidence.

The new §3.3 example shows the ambiguous-match path explicitly.

**Changes:**
- §3.2 — default-mode example shows ALL profiles fingerprinted, not first-match-wins.
- §3.3 — new section dedicated to the ambiguous-match path.
- §4.1 — explicit "does NOT short-circuit on first match" semantics.
- §6 — acceptance criterion added for the Acuvim-II-without-WEB false-positive case.

### #2 — Bench Day 3 deliverable overstated — CLI alone cannot answer the units question

**Validity:** Confirmed. The probe checks decode-success + range; a `12350.0 W` decoded as `12350.0 kW` passes range check while being 1000× wrong.

**Resolution chosen — judgment call: split the responsibility AND add `--reference-value` flag.** Reasoning:
- Honest documentation: the canonical Day 3 procedure is **probe + human-with-multimeter**. The probe handles automated decode/range checks; the human reads the actual line voltage / current / power on at least one phase and compares.
- Optional acceleration: `--reference-value metric=value` lets the operator feed the multimeter reading into the CLI for an automated comparison. The CLI flags off-by-1000× explicitly with a "likely cause" hint pointing at the device-library #1 units bug.

**Changes:**
- New §1.1 — "What the probe alone CANNOT do" — explicit.
- §3.1 — `--reference-value` flag added.
- New §3.5 — example of `--reference-value` happy path + the off-by-1000× disagreement path.
- §3.6 — JSON output includes `reference_value_comparison[]`.
- §6 — acceptance criterion: probe correctly flags off-by-1000× scenario.

---

## Major

### #3 — Distribution drift between pip-installed CLI and repo profiles

**Validity:** Confirmed. Three distribution targets, each with its own way of getting YAMLs, and the spec didn't pick one.

**Resolution:** "Package the YAMLs at build time; new profile → new probe-cli release."

- Pip package: vendors `architecture/logical_metrics.yaml` + `architecture/profiles/*.yaml` via `package_data`.
- Pi container: same source, baked into the image.
- CI: working-tree paths via explicit `--catalog` and `--profiles` so PR failures catch issues before the next pip release.

**Changes:** §5 fully rewritten with the three targets explicitly described.

### #4 — `--cross-check` default contradicts the §3.2 example

**Validity:** Confirmed.

**Resolution:** `--cross-check` is **ON by default in both default and `--verify` modes**. `--no-cross-check` to disable. The cross-check is the safety net catching the device-library #5 false-positive class — should be on always.

**Changes:** §3.1 synopsis updated; default-mode example in §3.2 now consistent.

### #5 — Pi container symlink isn't executable from host

**Validity:** Confirmed real bug.

**Resolution:** **wrapper script** at `/usr/local/bin/solamon-probe` that does `exec docker exec -i solamon-edge solamon-probe "$@"`. The operator SSHes to the Pi via Tailscale, runs `solamon-probe HOST:PORT`, and the wrapper transparently runs the probe inside the agent container.

**Changes:** §5.1 spelled out with the wrapper script; §6 acceptance criterion added.

### #6 — CI fixture has to simulate Modbus exception 0x02 on `0xC350`

**Validity:** Confirmed real implementation hazard (sparse-store behaviour varies).

**Resolution:** added §5.4 "Fixture patterns for CI" with concrete `ModbusSparseDataBlock` examples for both Acuvim L (0xC350 absent) and Acuvim II (0xC350 with "SunS" sentinel).

**Changes:** §5.4 new — fixture patterns inline.

### #7 — JSON output schema is informal

**Validity:** Confirmed.

**Resolution:** new artifact `architecture/probe-output.schema.json` — full JSON Schema covering `matched_confidence` enum, `fingerprint_results[*].reads[*]` shape, `block_probe[*].metrics_out_of_range[*]`, cross-check result interpretation, reference-value comparison, sanity warnings, exit codes.

**Changes:**
- New file: `architecture/probe-output.schema.json` (~270 lines).
- §3.6 references it; updated example matches the schema.
- §6 acceptance criterion: JSON output validates against the schema.

### #8 — Identifiers not surfaced in probe report

**Validity:** Confirmed. Acuvim L has no identifiers but Acuvim II will populate them.

**Resolution:** "Identifiers" section added to human output and `identifiers` field added to JSON. For Acuvim L the section says "(Acuvim L exposes none — capture serial / firmware / sub-variant from the device label or AXM-WEB2 web UI at commissioning)".

**Changes:** §3.2 example, §3.6 JSON example, schema artifact.

### #9 — Profiles with non-Modbus protocols silently break the probe

**Validity:** Confirmed though largely mitigated by cloud review #4 (schema enum narrowed to `modbus_tcp | modbus_rtu` only).

**Resolution:** defensive filter in `find_matching_profile` — only `connection.protocol == "modbus_tcp"` profiles are probed; others skipped with a documented reason.

**Changes:** §4 pseudo-code includes the filter.

### #10 — Exit code 1 conflates failure modes

**Validity:** Confirmed.

**Resolution chosen — judgment call: keep the four-code surface (0/1/2/3/4) coarse; rich detail goes into `--json`.** Reasoning:
- Adding 5/6/7/etc. for fine-grained failure types complicates shell scripting and operator memory without clear benefit.
- The `--json` mode is the programmatic interface; consumers (CI, post-MVP auto-detection logic) should consume that, not parse exit codes.
- Documented in §3.1: "the four-code surface stays coarse on purpose; `--json` is the programmatic interface for fine-grained handling".

**Changes:** §3.1 — note added; JSON Schema covers the fine-grained detail.

---

## Minor

### #11 — "Single binary" is misleading

Changed to "single command, no cloud dependency, no daemon".

### #12 — Verbose levels not defined

§3.1 now specifies:
- Default: WARN — silent on success
- `-v`: INFO — connect/probe lifecycle events
- `-vv`: DEBUG — raw Modbus PDU bytes, decoded byte order per metric, fingerprint match details

### #13 — No retry on transient Modbus failures

`--retries N` flag added (default 1). Useful for LTE field debugging. §3.1 + §4.3.

### #14 — Sub-variant detection silently impossible

Resolved with `sub_variant_required: true` + `sub_variant_note` fields in JSON output, and the human-readable "Sub-variant: required to be captured externally" line in the report. §3.2, §3.6, §7.

### #15 — Fast Read mode not in probe's checklist

Added to §4.2 sanity warnings:
> Fast Read mode interference: if `0x0600` returns Modbus exception but `0x3000` returns sensible Float32 → "AXM-WEB2 Fast Read mode appears enabled; standard Modbus reads suspended. Disable in the AXM-WEB2 web UI before commissioning".

### #16 — Bad port handling

§3.1 exit code 3 description updated:
> Connection / Modbus protocol error (couldn't reach the device, or the response wasn't valid Modbus framing — e.g. wrong port, port hits a non-Modbus service)

§4 pseudo-code includes the "non-Modbus response on port {port}" detection.

### #17 — Connection drops mid-probe

§4.3 documents:
- During fingerprint: report partial result; exit 3.
- During block probe: report blocks completed before drop; exit 1.
- `--retries N` covers transient failures within a block read.

### #18 — 0V reading on idle meter passes range check

**Resolution chosen — judgment call: soft warning only, doesn't fail the verdict.** §4.2:
> Idle meter: any voltage_l*_n or current_l* metric exactly 0.000 → "phase appears unenergised; verify CT and VT wiring".

This catches the wiring-but-not-sensing class of commissioning errors without false-positive failing legitimate single-phase or partially-loaded sites.

### #19 — JSON output `matched_profile` when nothing matches

`matched_profile: null`, `ambiguous_matches: []`, `verdict: "no_match"`. JSON Schema enforces. §3.6 + schema artifact.

### #20 — `--quiet` granularity

§3.1: "Suppress per-block detail and identifiers; print only the verdict line."

---

## Summary

- **20 findings, 20 addressed.**
- **Three judgment calls** flagged (#2 split-and-flag, #10 coarse-exit-codes-with-rich-JSON, #18 soft-warning-only).
- **One new machine artifact** created: `architecture/probe-output.schema.json` (~270 lines).
- **No new Linear issues** required — most items are doc fixes; the one architectural concern (#9 push-protocol filter) is already covered by cloud review #4 / SOL-22.

The probe spec was rewritten cleanly rather than 20 surgical edits — too many of the changes touched the same sections (§3 CLI interface, §5 distribution) to make targeted edits readable.

The biggest material change is **the fingerprint algorithm switch** (#1) — from first-match-wins to all-profiles-ranked-by-confidence with ambiguous-result detection. This eliminates a class of confidently-wrong verdicts, particularly important when Acuvim II support arrives.

The bench Day 3 deliverable is now honest about needing a human cross-check for the units question — backed by an optional `--reference-value` flag that automates the comparison once the human reads the multimeter.
