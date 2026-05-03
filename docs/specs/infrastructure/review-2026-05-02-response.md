# Infrastructure spec — review response

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)
**Review:** [`review-2026-05-02.md`](review-2026-05-02.md)
**Status:** addressed 2026-05-03

Per the standing rule (validate first, apply second), every finding was cross-checked against the actual current state of the bootstrap scripts and supporting specs. One critical finding had a partially-wrong diagnosis (the bug exists but for a different reason); the rest were applied. Tracked-as-follow-on items are deliberately not closed here — they're called out in §"Tracked separately" below.

---

## Validation table

### Critical

| # | Verdict | Notes |
|---|---------|-------|
| **#1** Mosquitto cert volume points to host path while Caddy uses named volume | **VALID** | Confirmed: the script declared `caddy-data:/data` (named volume) but mounted `./caddy/data/.../<DOMAIN>:/mosquitto/certs:ro` (host bind path that Caddy never wrote to). Mosquitto's cert dir was empty by design. |
| **#2** Caddy filenames don't match `mosquitto.conf` | **VALID** | Caddy stores `<DOMAIN>/<DOMAIN>.crt` + `<DOMAIN>.key`; the config asked for `cert.pem`/`privkey.pem`/`chain.pem`. |
| **#3** `cafile` enables mTLS rejecting all clients | **PARTIALLY INVALID** | Reviewer's mechanism is wrong — Mosquitto only requires client certs when `require_certificate true` is set explicitly (not on by default). With `cafile` alone + `require_certificate false`, Mosquitto does NOT reject username/password clients; it just refuses to start because the file the directive points at doesn't exist. Same fix the reviewer recommended (drop `cafile`), but the failure-mode diagnosis was off. |
| **#4** Empty password file + no `solamon-cloud` user | **VALID** | Empty file via `touch`; no `mosquitto_passwd` invocation; the cloud's MQTT password reused `${DB_PASSWORD}`. Confirmed cloud → broker auth would fail. |
| **#5** Password file mode 600 root-owned, container UID 1883 | **VALID** | `chmod 600` + host-owner root → in-container UID 1883 cannot read. |
| **#6** `depends_on: caddy: service_started` races cert provisioning | **VALID** | Mosquitto's `restart: unless-stopped` would mask it eventually but is ugly on bench Day 1. |
| **#7** Migration via `app` container assumes `psql` + `/app/migrations/` + `solamon.seed_reference_data` Python module | **VALID** | Real cross-spec gap — the cloud-app Dockerfile contract is undefined. |

### Major

| # | Verdict | Notes |
|---|---------|-------|
| #8 — `MOSQUITTO_CLOUD_PASSWORD` reused | **VALID** | (Sub-finding of #4.) |
| #9 — Backup cron + bucket pre-flight not in script | **VALID** | `pg_dump` cron + `aws s3api head-bucket` check were in the spec, missing from the script. |
| #10 — `--restore-from` skips migration replay | **VALID** | Silent landmine when 0002 ships. |
| #11 — Step counter mismatch | **VALID** | Confirmed: 16 `log_step` calls vs `TOTAL_STEPS=22`. |
| #12 — AWS CLI v1 from apt | **VALID** | Both scripts used `apt-get install awscli` (v1, EOL'd). |
| #13 — Secrets in argv | **VALID** | Visible in `ps -ef` for the ~10 min install window. |
| #14 — `tailscale up --reset` discards customisations | **VALID** | Both scripts used `--reset`. |
| #15 — No CI release workflow | **VALID** | Tracked as follow-on (see below). |
| #16 — IAM keys long-lived, manual rotation | **VALID** | Documented in `ecr-and-images.md §6.1`. |
| #17 — Mosquitto password lifecycle unspec'd | **VALID** | Site-add procedure was hand-wavy. |
| #18 — EC2 bootstrap key vs Tailscale lockout window | **VALID** | Documented in `cloud-bootstrap.md §1` step 3 + checklist §G. |
| #19 — CloudTrail/IAM groups manual not in script | **VALID** | Created `aws-account-setup-checklist.md`. |
| #20 — `solamon-cloud-postgres` ECR repo unused | **VALID** | Marked "(MVP: not used)". |

### Minor

| # | Verdict | Action |
|---|---------|--------|
| #21 | VALID | Added `[[ -n "$AWS_ACCOUNT_ID" ]] || die ...` validation in both scripts. |
| #22 | VALID | NTP timeout bumped from 2 min → 5 min. |
| #23 | VALID | Cron lines now set explicit `PATH=/usr/local/bin:/usr/bin:/bin`. |
| #24 | VALID | Added DNS propagation pre-flight (12×10 s = 2 min poll). |
| #25 | VALID (cosmetic) | Restore-branch step counter handled correctly given new `TOTAL_STEPS=20`. |
| #26 | VALID | `cloud-bootstrap.md §10.1` documents UID 1883 + 0640 contract. |
| #27 | VALID | Operator runbook in `pi-install.md §1` step 3 added "find the Acuvim's IP first" check. |
| #28 | VALID (tracked) | `update.sh` / `decommission.sh` left as follow-on. |
| #29 | VALID (note only) | Tailscale free-tier limits noted; revisit at 4th human user. |
| #30 | VALID (note only) | IPv6 absence noted in spec. |
| #31 | VALID (cosmetic) | `tailscale ip --4` output handled with `${VAR:-<pending>}` fallback. |
| #32 | VALID | CloudTrail S3 bucket creation in `aws-account-setup-checklist.md` §F. |
| #33 | VALID (no action) | Reviewer confirmed entropy adequate; no change. |
| #34 | VALID | `--admin-email` defaults to `admin@${DOMAIN}` (was `admin@solamon` — no TLD, NextAuth would reject). |
| #35 | VALID | `solamon-edge-install.sh` now configures `ufw` (deny incoming, allow tailscale0 + ssh on LAN). |
| #36 | VALID | Operator runbook now requires Marius's pubkey added at Pi Imager time. |
| #37 | VALID | Bootstrap script's pre-flight calls `aws sts get-caller-identity` and fails fast with a checklist pointer if instance profile missing. |

---

## What changed

### Spec docs

- **[`caddy-and-dns.md`](caddy-and-dns.md) §6** — rewritten end-to-end. Drops the cert-share-with-sidecar paragraph; commits to the **shared named-volume** model (Caddy writes `caddy-data`; Mosquitto reads `caddy-data:ro` from the same volume). Pins exact cert paths inside the volume; explicitly drops `cafile` from `mosquitto.conf`; documents daily SIGHUP cron for cert reload; adds §6.2 Mosquitto auth (separate `solamon-cloud` and `solamon-{site_slug}` users) and §6.3 password / ACL lifecycle (`mosquitto_passwd` inside the running container + SIGHUP).
- **[`cloud-bootstrap.md`](cloud-bootstrap.md)** — §3.6 splits step 11 into 11 + 11.1 (one-shot `mosquitto_passwd` to bootstrap the password file), adds `MQTT_CLOUD_PASSWORD` as a separate generated secret. §3.7 step 14 references the cloud-app Dockerfile contract (`docs/specs/cloud/Dockerfile.md` — to be authored as a tracked SOL-21 follow-on) with a fallback path that mounts migrations into the postgres container. §3.8 adds the Caddy-cert-readiness wait. §5 replaces the one-paragraph "the script also installs..." with the full `pg-backup.sh` + cron contract. §10 — site-add procedure expanded with §10.1 "Mosquitto password + ACL update" giving concrete `mosquitto_passwd` + SIGHUP commands. §11 disaster-recovery now replays migrations newer than what the dump contained (queries `app.schema_migrations`).
- **[`pi-install.md`](pi-install.md)** — §1 operator runbook restructured: explicit "confirm Acuvim IP first" pre-step (#27); "do NOT pass secrets on the command line" with the `--config /tmp/install-config.yaml` pattern (#13); pubkey added at Imager time (#36). §3.2 NTP timeout 5 min (#22). §3.5 AWS CLI v2 from official ARM64 zip (#12) + `AWS_ACCOUNT_ID` validation (#21). §3.7 cron PATH (#23). New §3.7.1 host firewall (#35) and §3.7.2 explicit no-`--reset` rationale (#14).
- **[`ecr-and-images.md`](ecr-and-images.md)** — §1 strikes through `solamon-cloud-postgres` row with "(MVP: not used)" note (#20). §6.1 adds explicit IAM-key rotation procedure (#16).
- **[`README.md`](README.md)** — adds checklist file to the documents list, updates the caddy-and-dns description.

### New artifacts

- **[`aws-account-setup-checklist.md`](aws-account-setup-checklist.md)** — operator-checklist of every manual AWS console / IAM / S3 / DNS / Tailscale step the install scripts ASSUME is already done. Includes a "Pre-flight gate" symptom-to-skipped-step mapping. Both scripts' fail-fast pre-flight checks (#37) point at this file.

### Scripts

- **[`scripts/solamon-cloud-bootstrap.sh`](scripts/solamon-cloud-bootstrap.sh)** — full rewrite. `TOTAL_STEPS=20`. New steps: AWS CLI v2 install, EC2InstanceRole pre-flight (`aws sts get-caller-identity`), backup-bucket pre-flight, DNS propagation poll, Caddy-cert-readiness wait, post-restore migration replay, `pg_dump` cron + `pg-backup.sh`. Mosquitto: shared `caddy-data:/caddy-data:ro` volume, `cafile` removed from mosquitto.conf, one-shot `mosquitto_passwd` to seed `solamon-cloud` user, daily SIGHUP cron. `MQTT_CLOUD_PASSWORD` generated separately from `DB_PASSWORD`. Caddyfile `log` block redacts `Sec-Websocket-Protocol` and `Authorization` headers. `--admin-email` default now `admin@${DOMAIN}`. `tailscale up` no longer uses `--reset`.
- **[`scripts/solamon-edge-install.sh`](scripts/solamon-edge-install.sh)** — full rewrite. `TOTAL_STEPS=18` (now matches actual `log_step` calls). New: `--config` argument that reads YAML from a mode-600 file and `shred`s it on exit (trap EXIT) — keeps secrets out of `ps`/argv/history. AWS CLI v2 from official ARM64 zip. `AWS_ACCOUNT_ID` validation. NTP timeout 5 min. `ufw` configuration. Cron `PATH` set explicitly. `tailscale up` no longer uses `--reset`. Diagnostic output uses `${VAR:-<pending>}` fallbacks.

---

## Tracked separately (deliberately not closed in this PR)

These are real items but are deferred from "fix the review" to "follow-on artifact for SOL-21":

- **`docs/specs/cloud/Dockerfile.md`** — the cloud-app image's contents contract (must include `psql`, `/app/migrations/`, the `solamon.seed_reference_data` Python module). The bootstrap script currently assumes this; it has to be authored before the bootstrap-script's migration step works at all. Cross-referenced from `cloud-bootstrap.md §3.7`.
- **`.github/workflows/release.yml`** — described in `ecr-and-images.md §4`; not committed.
- **`/opt/solamon/update.sh`** and **`decommission.sh`** — referenced from `pi-install.md §6, §7` and `cloud-bootstrap.md §7`; not committed.
- **Cloud-side site-add API endpoint** — for MVP the seed script handles the bench site directly. The runtime API for "add a site" (with the Mosquitto re-registration handshake from `cloud-bootstrap.md §10.1`) is post-MVP polish.
- **AWS SSM hybrid plan** — `ecr-and-images.md §6.2` / [SOL-10](https://linear.app/solamon/issue/SOL-10) — replaces the `pi-ecr-puller` long-lived IAM key. Triggers when site count > 2.
