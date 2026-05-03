# Probe CLI — `solamon-probe`

**Spec group owner:** [SOL-18 — MVP — Device probe CLI (`solamon-probe`)](https://linear.app/solamon/issue/SOL-18)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §8
**Status:** Working spec.
**Machine artifact:** [`architecture/probe-output.schema.json`](../../../architecture/probe-output.schema.json)

---

## 1. Purpose

A standalone Python CLI that connects to a Modbus TCP device, fingerprints it against the available device profiles, probes its register blocks, sanity-checks decoded values, and reports findings. **Single command, no cloud dependency, no daemon.** Used at three distinct points in a site's lifecycle:

1. **Bench Day 3** — the empirical Acuvim L `0x0600` vs `0x4000` test that resolves the Johan-vs-AccuEnergy-docs question. **The probe is one half of this; the other half is a human comparing the decoded values to a clamp-meter reading on the live conductors** — see §1.1 below.
2. **Site commissioning** — verify a freshly-wired meter matches the configured profile *before* the edge daemon goes live, so we catch wiring / firmware / address-space mismatches at install rather than two weeks later in invoice disputes.
3. **Field debugging** — when the dashboard shows weird values, an operator SSHes to the Pi via Tailscale and runs `solamon-probe` to see what the meter is actually returning.

It is the **foundation for two post-MVP features**:

- [SOL-11](https://linear.app/solamon/issue/SOL-11) — auto-detection at edge agent startup (the same logic moves into the agent's startup path, not as a separate CLI invocation)
- [SOL-19](https://linear.app/solamon/issue/SOL-19) — LAN-wide discovery (subnet scan + per-host probe)

### 1.1 What the probe alone CANNOT do

The probe sanity-checks that **decoded values fall inside the catalog's `expected_range`**. It cannot tell whether decoded values are *physically right*. A meter that returns `12350.0 W` while the profile mistakenly tags it as kW (the device-library #1 units bug) decodes as `12350.0 kW`, passes the catalog range check `[-100000, 100000]`, and the probe reports ✓ — even though the value is off by 1000×.

For Bench Day 3 the **probe + a human-with-multimeter** is the deliverable. The human reads the actual line voltage / current / power on at least one phase, the probe reports the decoded value, and the operator compares. The probe can assist this step via `--reference-value metric=value` (§3.2).

This split — automated checks + human reference — is documented in [`../device-library/acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §7.2 as the bench Day 3 procedure.

## 2. Audience and use cases

| User | Use case | Frequency |
|------|----------|-----------|
| Marius / Johan | Bench rehearsal Day 3 — settle the Acuvim L register-block + units questions | Once per project |
| Site installer | Verify the configured profile against the physically-deployed meter | Once per new site |
| Operator debugging | Diagnose a misbehaving site without touching the running edge agent | Ad-hoc, occasional |
| CI test suite | Verify the `acuvim_l.yaml` profile against a fake-Modbus-server fixture | Every commit |

## 3. CLI interface

### 3.1 Synopsis

```
solamon-probe [OPTIONS] HOST[:PORT]

Fingerprint a Modbus TCP device; probe its register blocks; report findings.

Arguments:
  HOST[:PORT]            Target device. Port defaults to 502.

Options:
  --unit-id INTEGER      Modbus slave / unit ID (default: 1)
  --verify PROFILE       Verify against a specific profile (e.g. "acuvim_l").
                         Without --verify, runs identity probe against ALL
                         profiles and recommends the best match.
  --no-cross-check       Disable cross-check probe. (Default: cross-check is ON
                         in both default and --verify modes — it's the safety
                         net that catches the device-library #5 false-positive
                         class.)
  --reference-value METRIC=VALUE
                         Provide an externally-measured reference value (e.g.
                         from a multimeter) for one decoded metric. The probe
                         compares the decoded value to the reference; reports
                         agreement / disagreement / off-by-1000× scenarios.
                         Repeatable for multiple metrics. Used in bench Day 3
                         to resolve units uncertainty.
                         Example: --reference-value voltage_l1_n=231.4
                                  --reference-value active_power_total=12.5
  --retries N            Retry transient Modbus failures up to N times before
                         giving up on a block. Default: 1. Useful when probing
                         over LTE.
  --catalog PATH         Path to logical_metrics.yaml. Default: bundled
                         (vendored from architecture/ at build time — see §5).
  --profiles PATH        Path to profiles directory. Default: bundled.
  --json                 Emit JSON instead of human-readable output. JSON
                         conforms to architecture/probe-output.schema.json.
  --quiet                Suppress per-block detail and identifiers; print
                         only the verdict line.
  --timeout SECONDS      Modbus operation timeout. Default: 5.
  -v, --verbose          Increase logging verbosity. Default: WARN level
                         (silent on success).
                         -v: INFO — connect/probe lifecycle events.
                         -vv: DEBUG — raw Modbus PDU bytes, decoded byte
                              order per metric, fingerprint match details.
  --help                 Show this message and exit.

Exit codes:
  0   Identity matches a single profile AND all probed blocks pass verification
  1   Identity matched but at least one block / metric verification failed
      (Modbus exception, out-of-range value, decode error, or reference-value
      disagreement. See JSON output for the precise reason.)
  2   Identity does not match any known profile, OR matches multiple profiles
      with equal confidence (operator must disambiguate)
  3   Connection / Modbus protocol error (couldn't reach the device, or the
      response wasn't valid Modbus framing — e.g. wrong port, port hits a
      non-Modbus service)
  4   Configuration error (bad CLI args, bad profile YAML, bad catalog)
```

The four-code surface stays coarse on purpose; **`--json` is the programmatic interface for fine-grained handling**. CI scripts and the post-MVP auto-detection logic should consume the JSON, not parse exit codes.

### 3.2 Default mode (no `--verify`) — fingerprint ALL profiles

```
$ solamon-probe 192.168.1.61:502 --unit-id 1

Connecting to 192.168.1.61:502 unit_id=1 ... ok (3 ms)

Identity probe — running fingerprint against all profiles:
  acuvim_l.yaml:
    [+] 0xC350 length=2     → exception 0x02 (illegal data address) ✓
    [+] 0x0130 length=1     → 5002 (50.02 Hz raw) ✓ in range [4500, 6500]
    [+] 0x0101 length=1     → 1 ✓ in range [1, 247]
    Match: ✓ (3/3 reads passed) — confidence: negative_fingerprint
  acuvim_ii.yaml:
    [+] 0xC350 length=2     → exception 0x02 (block absent — Acuvim II w/o WEB?)
    Match: ✗ — fingerprint failure (expected SunSpec sentinel "SunS")
  (no other profiles defined)

Verdict: matched profile acuvim_l (confidence: negative_fingerprint)

Identifiers: (Acuvim L exposes none — capture serial / firmware / sub-variant
              from the device label or AXM-WEB2 web UI at commissioning)

Sub-variant: required to be captured externally. Acuvim L family has CL / DL /
             EL / KL — identical Modbus map; the probe cannot distinguish them.

Block probe (acuvim_l.yaml):
  realtime  (0x0600, 74 regs, Float32 BE)        ✓ readable, 35/35 metrics in expected range
    └─ frequency_hz       = 50.02     ✓ [45, 65]
    └─ voltage_l1_n       = 231.4     ✓ [0, 1000]
    └─ active_power_total = 12.350    ✓ [-100000, 100000]
    └─ ... (32 more — all good)
  energy    (0x0156, 10 regs, Dword × 0.1)        ✓ readable, 5/5 metrics in expected range
  power_quality (0x0400, 6 regs, Word × 0.01)     ✓ readable, 6/6 metrics in expected range
  peak_demand (0x1024, 4 regs, dword_high_first)  ✓ readable
  clock (0x0184, 7 regs, custom decoder)          ✓ readable
  config (0x0103, 7 regs, mixed)                  ✓ readable, 6/6 metrics in expected range

Cross-check probe (acuvim_ii.yaml — alternative; ON by default):
  realtime (0x4000, 74 regs, Float32 BE)
    └─ Modbus exception 0x02 ✓ — block absent (confirms acuvim_l, not acuvim_ii)

Sanity warnings:
  (none)

Verdict: ACUVIM L (matched profile: acuvim_l.yaml, confidence: negative_fingerprint)
Recommended action: configure this device with profile_slug=acuvim_l.
```

### 3.3 Ambiguous match — multiple profiles fingerprinted

```
$ solamon-probe 192.168.1.62:502

...

Verdict: AMBIGUOUS — two profiles matched with equal confidence:
  - acuvim_l (negative_fingerprint, 3/3 reads passed)
  - acuvim_ii_no_web (negative_fingerprint, 3/3 reads passed)

Operator action required: physically inspect the device label to disambiguate.
The cross-check probe (below) reads the alternative profile's blocks against
this device — values from the right profile should be physically sensible;
values from the wrong profile should be garbage or absent.

Cross-check (acuvim_ii.yaml/realtime at 0x4000):
  └─ frequency_hz @ offset 0    = 0.000  ✗ outside expected range [45, 65]
  └─ voltage_l1_n @ offset 4    = 0.000  ✗ outside expected range [0, 1000]
  └─ → 0x4000 block addresses respond but values are zero / garbage.
       This is more consistent with Acuvim L than Acuvim II without WEB.

Recommended profile (low confidence): acuvim_l. Confirm via device label.
Exit code: 2
```

### 3.4 `--verify` mode — fast confirmation against a known profile

```
$ solamon-probe 192.168.1.61:502 --unit-id 1 --verify acuvim_l

Connecting to 192.168.1.61:502 unit_id=1 ... ok (3 ms)

Verifying acuvim_l.yaml:
  Fingerprint: ✓ (3/3 reads passed)
  Block probe: ✓ (6/6 blocks readable, 53/53 metrics in expected range)
  Cross-check: ✓ (acuvim_ii.0x4000 absent as expected)

Verdict: ACUVIM L profile verified for 192.168.1.61.
Exit code: 0
```

### 3.5 `--reference-value` mode — units cross-check

```
$ solamon-probe 192.168.1.61:502 --verify acuvim_l \
    --reference-value voltage_l1_n=231.4 \
    --reference-value active_power_total=12.500

Verifying acuvim_l.yaml:
  Fingerprint: ✓
  Block probe: ✓ (all metrics in range)
  Reference-value comparison:
    voltage_l1_n        decoded=231.4    reference=231.4    ✓ agreement (Δ < 0.1 %)
    active_power_total  decoded=12.350   reference=12.500   ✓ agreement (Δ = 1.2 %, within 5 %)
  Cross-check: ✓

Verdict: ACUVIM L profile verified — units agree with reference values.
Exit code: 0
```

If a reference value disagrees by 1000× (the device-library #1 units bug), the report flags it explicitly:

```
  Reference-value comparison:
    active_power_total  decoded=12350.0  reference=12.500    ✗ DISAGREEMENT — decoded ÷ reference = 988
                        Likely cause: missing scale: 0.001 in profile (W vs kW units bug).
                        See docs/specs/device-library/acuvim-l-profile.md §7.2.

Verdict: profile fingerprint matches, but units appear wrong. Fix the profile before commissioning.
Exit code: 1
```

### 3.6 `--json` output

For programmatic consumers (commissioning scripts, the post-MVP edge-agent auto-detection). JSON conforms to [`architecture/probe-output.schema.json`](../../../architecture/probe-output.schema.json).

```json
{
  "schema_version": "1.0",
  "target": { "host": "192.168.1.61", "port": 502, "unit_id": 1 },
  "matched_profile": "acuvim_l",
  "matched_confidence": "negative_fingerprint",
  "ambiguous_matches": [],
  "fingerprint_results": {
    "acuvim_l": {
      "matched": true,
      "confidence": "negative_fingerprint",
      "reads": [
        {"address": "0xC350", "expected": "exception_0x02", "result": "exception_0x02", "passed": true},
        {"address": "0x0130", "expected_range": [4500, 6500], "result": 5002, "passed": true},
        {"address": "0x0101", "expected_range": [1, 247], "result": 1, "passed": true}
      ]
    },
    "acuvim_ii": {
      "matched": false,
      "confidence": "none",
      "reads": [
        {"address": "0xC350", "expected_contains": "SunS", "result": "exception_0x02", "passed": false}
      ]
    }
  },
  "identifiers": {},
  "sub_variant_required": true,
  "sub_variant_note": "Acuvim L family CL/DL/EL/KL identical on the wire — capture from device label",
  "block_probe": {
    "realtime": { "readable": true, "metrics_total": 35, "metrics_in_range": 35, "metrics_out_of_range": [] },
    "energy": { "readable": true, "metrics_total": 5, "metrics_in_range": 5, "metrics_out_of_range": [] }
  },
  "cross_check": {
    "acuvim_ii.realtime": { "readable": true, "exception_code": null, "values_sensible": false, "interpretation": "block_responds_with_zeros — likely block_aliased_or_absent" }
  },
  "reference_value_comparison": [
    { "metric": "voltage_l1_n", "decoded": 231.4, "reference": 231.4, "delta_pct": 0.0, "agreement": true }
  ],
  "sanity_warnings": [],
  "exit_code": 0,
  "verdict": "acuvim_l",
  "duration_ms": 1842
}
```

When no profile matches: `matched_profile: null`, `ambiguous_matches: []`, `verdict: "no_match"`. When ambiguous: `matched_profile: null`, `ambiguous_matches: ["acuvim_l", "acuvim_ii_no_web"]`, `verdict: "ambiguous"`.

## 4. Internal structure

The CLI is a **thin wrapper around the shared profile loader** specified in [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7. No new library code; the probe is essentially:

```python
# Pseudo-code — the entire CLI logic
async def main(target, options):
    catalog = load_catalog(options.catalog)
    profiles = load_profiles_dir(options.profiles, catalog)

    # Defensive filter — only Modbus profiles are probe-able. The MVP schema
    # enum only allows modbus_tcp / modbus_rtu (see cloud review #4), but
    # filter anyway for robustness if a future profile slips through.
    profiles = {name: p for name, p in profiles.items()
                if p.connection.protocol == "modbus_tcp"}

    client = AsyncModbusTcpClient(target.host, target.port, timeout=options.timeout)
    if not await client.connect():
        # Distinguish "wrong port" from "Modbus error":
        # if connect succeeded but first read returns invalid framing,
        # report "non-Modbus response on port {port}"; exit 3.
        ...

    if options.verify:
        result = await verify_profile(client, profiles[options.verify], profiles, options)
    else:
        result = await find_matching_profile(client, profiles, options)

    if options.reference_value:
        result.reference_value_comparison = await compare_reference_values(
            client, result, options.reference_value
        )

    result.sanity_warnings = compute_sanity_warnings(result)

    if options.json:
        print(json.dumps(result.to_dict()))
    else:
        print_human(result, verbosity=options.verbosity)

    sys.exit(result.exit_code)
```

### 4.1 `find_matching_profile` — runs ALL profile fingerprints

Critical fix per review #1: the function does NOT short-circuit on first match. It runs every profile's fingerprint, collects all matches with their confidence, and:

- If exactly one match, regardless of confidence → that profile, verdict and exit 0/1 as appropriate.
- If multiple matches with `positive_fingerprint` → highest confidence wins (none today; both Acuvim L and Acuvim II identifying are `negative_fingerprint` and `positive_fingerprint` respectively, so this case is a genuine "device confused").
- If multiple matches at the same confidence (e.g., Acuvim L and a hypothetical "Acuvim II without WEB" both with `negative_fingerprint`) → report ambiguous; exit 2; operator must disambiguate via device label / cross-check evidence.

### 4.2 Sanity warnings

Soft-warning checks that don't fail the verdict but flag suspicious reads for the operator:

- **Idle meter:** any voltage_l*_n or current_l* metric exactly 0.000 → "phase appears unenergised; verify CT and VT wiring".
- **Fast Read mode interference:** if `0x0600` returns Modbus exception but `0x3000` returns sensible Float32 → "AXM-WEB2 Fast Read mode appears enabled; standard Modbus reads suspended. Disable in the AXM-WEB2 web UI before commissioning".
- **Reference-value disagreement:** if `--reference-value` shows >5 % delta → flag with severity proportional to delta.

### 4.3 Connection drop handling

- During fingerprint: report partial fingerprint result; exit 3.
- During block probe: report the blocks completed before the drop; exit 1 (some blocks unverified).
- The `--retries N` flag (default 1) covers transient Modbus failures within a block read; harder failures (TCP reset) terminate the probe.

## 5. Distribution

The YAMLs (`logical_metrics.yaml`, `profiles/*.yaml`) are **packaged at build time** with the probe; new profiles → new probe-cli release. Three distribution targets, all consume the same pinned-at-build YAMLs:

### 5.1 Pi container

The agent's Docker image already has the YAMLs (the agent itself uses them) and a `solamon-probe` entry point. The Pi installer drops a **wrapper script** at `/usr/local/bin/solamon-probe` (NOT a symlink — see #5 below):

```bash
#!/bin/sh
# /usr/local/bin/solamon-probe (host-side wrapper)
exec docker exec -i solamon-edge solamon-probe "$@"
```

The operator SSHes to the Pi via Tailscale, runs `solamon-probe HOST:PORT ...`, and the wrapper transparently runs the probe inside the agent container. The container's Modbus client connects to `HOST:PORT` over the Pi's LAN — same network reachability as the agent itself.

### 5.2 Pip-install on dev laptop

```
pip install solamon-probe
```

The Python package vendors `architecture/logical_metrics.yaml` and `architecture/profiles/*.yaml` via `package_data` (specified in `setup.py` / `pyproject.toml`). New profile in the repo → bump version → publish. The pip-installed CLI uses `--catalog` and `--profiles` defaults to the package-vendored copies; pass `--catalog ../path/to/yaml --profiles ../path/to/profiles/` to use a working-tree version (CI does this).

### 5.3 CI fixture

The test suite spins up a fake Modbus TCP server (`pymodbus.server.AsyncModbusTcpServer` with hand-crafted `ModbusSparseDataBlock` register files) and runs `solamon-probe localhost:5020 --verify acuvim_l --json`. Asserts on the JSON exit code and key fields.

The CI pins `--catalog` and `--profiles` at the working-tree paths so test failures are caught at PR time, before the next pip release.

### 5.4 Fixture patterns for CI

For the Acuvim L fixture, the `0xC350` SunSpec block must return Modbus exception `0x02` (illegal data address). With `pymodbus`'s `ModbusSparseDataBlock`, addresses NOT registered in the dict raise the exception by default — but only if the data block is constructed correctly:

```python
# Acuvim L fixture — note 0xC350 is intentionally absent
acuvim_l_holding = ModbusSparseDataBlock({
    # 0x0101 — Modbus address echo
    0x0101: 1,
    # 0x0130 — frequency × 100 (50.02 Hz)
    0x0130: 5002,
    # 0x0600 — primary Float32 block: 74 registers
    # Fill in expected-range values; encode as Float32 BE registers
    **acuvim_l_realtime_block(0x0600),
    # ... energy, power_quality, peak_demand, clock, config blocks
})
# IMPORTANT: 0xC350 is NOT in the dict — pymodbus returns exception 0x02 for it
```

For the Acuvim II fixture, `0xC350` returns the SunSpec sentinel:

```python
# Acuvim II fixture — 0xC350-0xC353 contains "SunS" + model 1 + length 65
acuvim_ii_holding = ModbusSparseDataBlock({
    0xC350: 0x5375,      # 'S' 'u'
    0xC351: 0x6E53,      # 'n' 'S'
    0xC352: 1,           # SunSpec model 1 (common)
    0xC353: 65,          # length
    # 0xC354..0xC363 — manufacturer "Accuenergy" padded to 32 bytes
    **ascii_to_registers(0xC354, "Accuenergy", padded_length=16),
    # 0xC364..0xC373 — model "Acuvim II"
    **ascii_to_registers(0xC364, "Acuvim II", padded_length=16),
    # ... 0x4000 primary Float32 block, etc.
})
```

Helper utilities (`ascii_to_registers`, `acuvim_l_realtime_block`, etc.) live in the test fixtures package; the spec doesn't pin their exact implementation.

## 6. Acceptance criteria

- `solamon-probe HOST` against a real Acuvim L on the bench correctly identifies the profile, prints a green-tick report, exits 0.
- `solamon-probe HOST --verify acuvim_l` does the same; exit 0.
- `solamon-probe HOST --verify acuvim_ii` against the same Acuvim L correctly fails (Acuvim II fingerprint requires a positive SunSpec block read; Acuvim L returns exception); exit 1 with clear "fingerprint mismatch" output.
- A CI test against a fake-Modbus fixture mimicking Acuvim L → exit 0; against a fake fixture mimicking Acuvim II → exit 0 when verifying `acuvim_ii`, exit 1 when verifying `acuvim_l`.
- A CI test against a fake fixture mimicking the **Acuvim II without WEB** false-positive case (review #1 / device-library #5) → default mode reports `ambiguous` and exit 2 with both `acuvim_l` and `acuvim_ii_no_web` listed in `ambiguous_matches`.
- `--json` output is well-formed (passes `json.loads`) and validates against `architecture/probe-output.schema.json`.
- `--reference-value` correctly flags an off-by-1000× scenario (the device-library #1 bug if it ever resurfaces).
- Cross-check mode against the bench Acuvim L: definitively answers the `0x4000` question (either "block_absent" → Johan's flow has been reading nonsense; or "readable_but_garbage" → ditto; or "readable_with_sensible_values" → firmware aliases the blocks; we'd update [`acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §7 with the empirical answer).
- Connection to non-existent host → exit 3, clear "connection refused" / "no route to host" error.
- Connection to a non-Modbus port (e.g., MQTT TLS 8883) → exit 3 with "non-Modbus response from {host}:{port}" error rather than a cryptic protocol error.
- Bad profile name → exit 4, clear "profile 'foo' not found; available: acuvim_l".
- Pi-side wrapper script `/usr/local/bin/solamon-probe` correctly proxies to `docker exec solamon-edge solamon-probe ...` and surfaces the inner exit code unchanged.

## 7. Out of scope

- **LAN discovery** (subnet scan) → [SOL-19](https://linear.app/solamon/issue/SOL-19). MVP probe takes one host at a time.
- **Reading control register state / executing test writes** — the probe is read-only by design. Issuing a control command goes through the cloud's authenticated REST endpoint.
- **Continuous monitoring mode** — the probe is one-shot. Continuous polling is what the edge agent does.
- **Probing non-Modbus protocols** — the CLI only speaks Modbus TCP. Non-Modbus device families (MQTT-push devices like AXM-WEB2 in push mode, HTTP-only devices) are post-MVP additions.
- **Sub-variant detection** — for device families like Acuvim L (CL/DL/EL/KL identical on the wire) the probe explicitly cannot detect sub-variant. The JSON output's `sub_variant_required: true` flag advises commissioning to capture this externally.

## 8. Cross-references

- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7 — the profile loader API the probe wraps
- [`../device-library/acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §7 — the open empirical questions this CLI helps resolve
- [`../edge-agent/modbus-poller.md`](../edge-agent/modbus-poller.md) — shared Modbus client wrapper
- [`../../../architecture/probe-output.schema.json`](../../../architecture/probe-output.schema.json) — JSON output schema (§3.6)
- Main spec [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §8
