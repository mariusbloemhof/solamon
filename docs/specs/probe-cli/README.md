# Probe CLI — `solamon-probe`

**Spec group owner:** [SOL-18 — MVP — Device probe CLI (`solamon-probe`)](https://linear.app/solamon/issue/SOL-18)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §8
**Status:** Working spec.

---

## 1. Purpose

A standalone CLI tool that connects to a Modbus TCP device, fingerprints it against the available device profiles, probes its register blocks, sanity-checks decoded values, and reports findings. **Single binary, no cloud dependency, no daemon.** Used at three distinct points in a site's lifecycle:

1. **Bench Day 3** — the empirical Acuvim L `0x0600` vs `0x4000` test that resolves the Johan-vs-AccuEnergy-docs question.
2. **Site commissioning** — verify a freshly-wired meter matches the configured profile *before* the edge daemon goes live, so we catch wiring / firmware / address-space mismatches at install rather than two weeks later in invoice disputes.
3. **Field debugging** — when the dashboard shows weird values, an operator SSH'es to the Pi via Tailscale and runs `solamon-probe` to see what the meter is actually returning.

It is the **foundation for two post-MVP features**:

- [SOL-11](https://linear.app/solamon/issue/SOL-11) — auto-detection at edge agent startup (the same logic moves into the agent's startup path, not as a separate CLI invocation)
- [SOL-19](https://linear.app/solamon/issue/SOL-19) — LAN-wide discovery (subnet scan + per-host probe)

## 2. Audience and use cases

| User | Use case | Frequency |
|------|----------|-----------|
| Marius / Johan | Bench rehearsal Day 3 — settle the Acuvim L register-block question | Once per project |
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
                         Without --verify, runs identity probe against ALL profiles
                         and recommends the best match.
  --cross-check          For the matched (or specified) profile, also probe blocks
                         from other profiles to catch firmware aliasing.
                         Default: enabled when --verify is set; off otherwise.
  --catalog PATH         Path to logical_metrics.yaml. Default: bundled.
  --profiles PATH        Path to profiles directory. Default: bundled.
  --json                 Emit JSON instead of human-readable output.
  --quiet                Suppress per-block detail; just print the verdict line.
  --timeout SECONDS      Modbus operation timeout. Default: 5.
  -v, --verbose          Increase logging verbosity (-vv for DEBUG).
  --help                 Show this message and exit.

Exit codes:
  0   Identity matches a single profile AND all probed blocks return sensible values
  1   Identity matches a profile but at least one block fails verification
  2   Identity does not match any known profile
  3   Connection / Modbus protocol error (couldn't reach the device)
  4   Configuration error (bad CLI args, bad profile YAML, bad catalog)
```

### 3.2 Default mode (no `--verify`)

```
$ solamon-probe 192.168.1.61:502 --unit-id 1

Connecting to 192.168.1.61:502 unit_id=1 ... ok (3 ms)

Identity probe:
  Trying acuvim_l.yaml:
    [+] 0xC350 length=2     → exception 0x02 (illegal data address) ✓
    [+] 0x0130 length=1     → 5002 (50.02 Hz raw) ✓ in range [4500, 6500]
    [+] 0x0101 length=1     → 1 ✓ in range [1, 247]
    Match: acuvim_l (3/3 fingerprint reads passed)

  Trying acuvim_ii.yaml: skipped (acuvim_l already matched)

Block probe (acuvim_l.yaml):
  realtime  (0x0600, 74 regs, Float32 BE)        ✓ readable, 35/35 metrics in expected range
    └─ frequency_hz       = 50.02     ✓ [45, 65]
    └─ voltage_l1_n       = 231.4     ✓ [0, 1000]
    └─ active_power_total = 12.350    ✓ [-100000, 100000]
    └─ ... (32 more — all good)
  energy    (0x0156, 10 regs, Dword × 0.1)        ✓ readable, 5/5 metrics in expected range
  power_quality (0x0400, 6 regs, Word × 0.01)     ✓ readable, 6/6 metrics in expected range
  peak_demand (0x1024, 4 regs)                    ✓ readable, 1/1 metrics in expected range
  clock (0x0184, 7 regs, acuvim_clock)            ✓ readable
  config (0x0103, 7 regs, mixed)                  ✓ readable, 6/6 metrics in expected range

Cross-check probe (acuvim_ii.yaml — alternative):
  realtime (0x4000, 74 regs, Float32 BE)
    └─ Modbus exception 0x02 ✓ (block does not exist on this device — confirms acuvim_l)

Verdict: ACUVIM L (matched profile: acuvim_l.yaml)

Recommended action: configure this device with profile_slug=acuvim_l.
```

### 3.3 `--verify` mode

```
$ solamon-probe 192.168.1.61:502 --unit-id 1 --verify acuvim_l

Connecting to 192.168.1.61:502 unit_id=1 ... ok (3 ms)

Verifying acuvim_l.yaml:
  Fingerprint: ✓ (3/3 reads passed)
  Block probe: ✓ (6/6 blocks readable, 53/53 metrics in expected range)
  Cross-check: ✓ (acuvim_ii.0x4000 is absent as expected)

Verdict: ACUVIM L profile verified for 192.168.1.61.
```

Exits 0. Suitable for use in commissioning scripts and CI.

### 3.4 `--json` output

For programmatic consumers (commissioning scripts, the post-MVP edge-agent auto-detection):

```json
{
  "target": { "host": "192.168.1.61", "port": 502, "unit_id": 1 },
  "matched_profile": "acuvim_l",
  "matched_confidence": "negative_fingerprint",
  "fingerprint_results": {
    "acuvim_l": { "matched": true, "reads": [{"address": "0xC350", "result": "exception_0x02", "expected": "exception_0x02", "passed": true}, ...] },
    "acuvim_ii": { "matched": false, "skipped": true }
  },
  "block_probe": {
    "realtime": { "readable": true, "metrics_total": 35, "metrics_in_range": 35, "metrics_out_of_range": [] },
    "energy": { "readable": true, ... },
    ...
  },
  "cross_check": {
    "acuvim_ii.realtime": { "readable": false, "exception_code": 2, "interpretation": "block_absent" }
  },
  "exit_code": 0,
  "verdict": "acuvim_l",
  "duration_ms": 1842
}
```

## 4. Internal structure

The CLI is a **thin wrapper around the shared profile loader** specified in [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7. No new library code; the probe is essentially:

```python
# Pseudo-code — the entire CLI logic
async def main(target, options):
    catalog = load_catalog(options.catalog)
    profiles = load_profiles_dir(options.profiles, catalog)

    client = AsyncModbusTcpClient(target.host, target.port, timeout=options.timeout)
    await client.connect()

    if options.verify:
        profile = profiles[options.verify]
        result = await verify_profile(client, profile, profiles, options)
    else:
        result = await find_matching_profile(client, profiles, options)

    if options.json:
        print(json.dumps(result.to_dict()))
    else:
        print_human(result, verbosity=options.verbosity)

    sys.exit(result.exit_code)
```

`verify_profile` and `find_matching_profile` are the two top-level routines. Both ultimately call the loader's `fingerprint_match()` and (a probe-CLI-specific extension) `probe_blocks()` which iterates `profile.read_blocks` and decodes them via `profile.decode()` while sanity-checking against the catalog's `expected_range`.

The probe CLI does NOT depend on the edge-agent's main module — it only depends on the shared `lib/profile_loader/` and `lib/modbus_client/` packages. This is what lets it run on any host that has Python + the Solamon source.

## 5. Distribution

Three packaging targets:

1. **Pre-installed on the Pi** — every Pi has `solamon-probe` on `$PATH`. Installer (`solamon-edge-install.sh`) drops a `solamon-probe` symlink into `/usr/local/bin` pointing at a script in the agent container. Operators SSH'd in via Tailscale just run `solamon-probe ...`.
2. **Pip-installable from dev laptops** — `pip install solamon-probe` (private PyPI or direct `pip install git+https://...`). Marius runs it from his laptop pointing at the bench's Acuvim via Tailscale port forwarding.
3. **CI fixture** — the test suite spins up a fake Modbus TCP server (`pymodbus.server.AsyncModbusTcpServer` with a hand-crafted register file mimicking an Acuvim L); CI runs `solamon-probe localhost:5020 --verify acuvim_l --json` and asserts the JSON exit code is 0.

For MVP all three use the same Python source. The Pi version runs inside the agent container; the laptop version runs via `pip`.

## 6. Acceptance criteria

- `solamon-probe HOST` against a real Acuvim L on the bench correctly identifies the profile, prints a green-tick report, exits 0.
- `solamon-probe HOST --verify acuvim_l` does the same; exit 0.
- `solamon-probe HOST --verify acuvim_ii` against the same Acuvim L correctly fails (Acuvim II fingerprint requires a positive SunSpec block read; Acuvim L returns exception); exit 1 with clear "fingerprint mismatch" output.
- A CI test against a fake-Modbus fixture mimicking Acuvim L → exit 0; against a fake fixture mimicking Acuvim II → exit 0 when verifying `acuvim_ii`, exit 1 when verifying `acuvim_l`.
- `--json` output is well-formed (passes `json.loads`); fields match the §3.4 shape.
- Cross-check mode against the bench Acuvim L: definitively answers the `0x4000` question (either "block_absent" → Johan's flow has been reading nonsense; or "readable_but_garbage" → ditto; or "readable_with_sensible_values" → firmware aliases the blocks; we'd update [`acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §7 with the empirical answer).
- Connection to non-existent host → exit 3, clear "connection refused" / "no route to host" error.
- Bad profile name → exit 4, clear "profile 'foo' not found; available: acuvim_l".

## 7. Out of scope

- **LAN discovery** (subnet scan) → [SOL-19](https://linear.app/solamon/issue/SOL-19). MVP probe takes one host at a time.
- **Reading control register state / executing test writes** — the probe is read-only by design. Issuing a control command goes through the cloud's authenticated REST endpoint.
- **Continuous monitoring mode** — the probe is one-shot. Continuous polling is what the edge agent does.
- **Probing non-Modbus protocols** — the CLI only speaks Modbus TCP. Non-Modbus device families (MQTT-push devices like AXM-WEB2 in push mode, HTTP-only devices) are post-MVP additions.

## 8. Cross-references

- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) §7 — the profile loader API the probe wraps
- [`../device-library/acuvim-l-profile.md`](../device-library/acuvim-l-profile.md) §7 — the open empirical question this CLI resolves
- [`../edge-agent/modbus-poller.md`](../edge-agent/modbus-poller.md) — shared Modbus client wrapper
- Main spec [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §8
