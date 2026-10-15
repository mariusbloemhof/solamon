# Infrastructure — current state (as-built)

**As of:** 2026-05-08 (provisioning) · operations updated 2026-10-15 — see §9 for the incident log and handover
**Owner:** Marius Bloemhof
**Status:** All cloud infrastructure provisioned and verified. The full cloud stack (Caddy, Postgres/Timescale, Mosquitto, cloud-app, web-ui) has run on the EC2 since 2026-05-08 and is live at <https://cloud.amendi.dev>. §7 below is the original May-08 snapshot and is now historical.

This document is the **single source of truth for what actually exists in the real world**. The specs in this folder describe intended behaviour; this file lists the resources that have been created. When the cloud-bootstrap or edge-install scripts run, they consume these resource IDs.

---

## 1. AWS

| Property | Value |
|---|---|
| Account ID | `556671502751` |
| Region | `af-south-1` (Cape Town) |
| Billing currency | ZAR |
| Root MFA | enabled |
| AWS CLI profile (Marius's laptop) | `solamon` |
| Local CLI config | `C:\Users\Marius\.aws\config`, `C:\Users\Marius\.aws\credentials` |

### 1.1 IAM

| Resource | Notes |
|---|---|
| User `Marius` | Day-to-day admin. In group `Admins`. CLI keys in `~/.aws/credentials` profile `solamon`. |
| Group `Admins` | `AdministratorAccess` attached. |
| Group `Developers` | Empty in MVP. |
| Group `Operators` | Empty in MVP. `ReadOnlyAccess` attached. |
| User `pi-ecr-puller` | ECR-pull-only on `solamon-edge-agent`. Inline policy `PiECRReadOnly`. Access key originally written to `D:\install\pi-ecr-puller-keys.txt` then moved to 1Password as **"Solamon pi-ecr-puller IAM keys"**. |
| Role `EC2InstanceRole` | Used by the cloud EC2's instance profile. ECR pull on `solamon-cloud-app`, `solamon-web-ui`, and `solamon-edge-agent` + S3 read/write on backup bucket + CloudWatch metrics/logs. Inline policy `SolamonEC2Permissions`. |
| Role `GitHubActionsECRPushRole` | Trusted by GitHub Actions OIDC for `mariusbloemhof/solamon` on tag pushes only (`refs/tags/v*`). Permissions: ECR push to `solamon-cloud-app`, `solamon-web-ui`, and `solamon-edge-agent`. ARN: `arn:aws:iam::556671502751:role/GitHubActionsECRPushRole` |
| OIDC provider | `arn:aws:iam::556671502751:oidc-provider/token.actions.githubusercontent.com` |

### 1.2 S3

| Bucket | Purpose | Config |
|---|---|---|
| `solamon-backup-prod` | Postgres `pg_dump` backups | AES-256 SSE; versioning on; lifecycle: expire `postgres/*` at 30 days; public access blocked |
| `solamon-cloudtrail-prod` | CloudTrail log destination | AES-256 SSE; bucket policy allows `cloudtrail.amazonaws.com` to write; public access blocked |

### 1.3 CloudTrail

| Trail | Bucket | Config |
|---|---|---|
| `solamon-trail` | `solamon-cloudtrail-prod` | Multi-region; log file validation enabled; logging active |

### 1.4 ECR (Elastic Container Registry)

| Repository | URI | Config |
|---|---|---|
| `solamon-edge-agent` | `556671502751.dkr.ecr.af-south-1.amazonaws.com/solamon-edge-agent` | scan-on-push; lifecycle: keep last 5 tagged `v*`, expire untagged > 7 d, anything > 90 d |
| `solamon-cloud-app` | `556671502751.dkr.ecr.af-south-1.amazonaws.com/solamon-cloud-app` | same lifecycle + scan |
| `solamon-web-ui` | `556671502751.dkr.ecr.af-south-1.amazonaws.com/solamon-web-ui` | same lifecycle + scan |

**No images have been pushed yet.** First image pushes happen via the GitHub Actions release workflow (which itself isn't committed yet — see `ecr-and-images.md §4`).

### 1.5 Budget alerts

| Budget | Threshold | Notification |
|---|---|---|
| `solamon-info-30-usd` | $30 USD/mo (~R 555) | email `mariusbloemhof@gmail.com` at 80% actual |
| `solamon-alert-60-usd` | $60 USD/mo (~R 1110) | email `mariusbloemhof@gmail.com` at 80% actual |

Note: AWS Budgets does not support ZAR despite billing being in ZAR. The spec's "R 500 / R 1000" was converted to USD at ~R18.50.

### 1.6 EC2 (cloud host)

| Property | Value |
|---|---|
| Instance ID | `i-028b3a7906dcd4185` |
| Instance type | `t4g.small` (ARM64, Graviton2) |
| AMI | `ami-04ea5830b33e82130` (Ubuntu 24.04 LTS noble arm64, Canonical) |
| Public Elastic IP | `13.247.131.5` (allocation `eipalloc-06fd3937df56dd97f`) |
| Internal IP | `172.31.7.151` |
| Tailscale IP | `100.77.122.23` |
| Hostname (in tailnet) | `solamon-cloud-prod` |
| Public DNS | `cloud.amendi.dev` (Cloudflare A record) |
| Tags | `Name=solamon-cloud-prod`, `Project=solamon`, `Environment=production` |
| Root volume | 30 GB gp3, encrypted, delete-on-termination |
| Instance profile | `EC2InstanceRole` |
| Key pair | `solamon-bootstrap` (key ID `key-0909a95547fef2db2`) |
| IMDS | v2 required (`HttpTokens=required`) |
| VPC | `vpc-0345d33247dc2b49c` (default) |
| Subnet | `subnet-0618cc10545575f86` |

**Security group** `sg-03a9e7b940e0c9aa1` (`solamon-cloud-sg`):

| Port | Source | Purpose |
|---|---|---|
| 22/tcp | `100.64.0.0/10` (Tailscale CGNAT) | SSH via tailnet only — public-IP SSH is blocked |
| 80/tcp | `0.0.0.0/0` | HTTP (Let's Encrypt challenge + redirect to 443) |
| 443/tcp | `0.0.0.0/0` | HTTPS — web UI + API + WebSocket |
| 8883/tcp | `0.0.0.0/0` | MQTT TLS — Pi connections |

The bootstrap-time public-IP SSH rule (`156.155.54.131/32`) was deliberately revoked once Tailscale SSH was confirmed working.

> **Opening port 22 in the security group does NOT give you SSH.** The bootstrap also configures **ufw on the host**: `default deny incoming`, with SSH allowed **only on `tailscale0`** (`scripts/solamon-cloud-bootstrap.sh:427-435`). A security-group rule for your IP gets you past AWS and is then dropped by ufw. This was proven the hard way on 2026-09-04.
>
> **If the tailnet path is down, the only ways in are:**
> 1. **User-data recovery boot** — stop the instance, set cloud-init user-data with `cloud_final_modules: [[scripts-user, always]]` and a `runcmd`, start it, and read the output with `aws ec2 get-console-output --latest`. Clear the user-data afterwards (needs another stop). Gotchas: AWS CLI v2 rejects `--value fileb://…` *and echoes the whole file into the error*, so pass `--value "$(base64 -w0 file)"` instead and verify by decoding `describe-instance-attribute --attribute userData`. Validate the YAML first: a single bad escape (`\s` inside a double-quoted scalar) makes cloud-init discard the entire cloud-config silently.
> 2. **Detach the root volume** and mount it on a rescue instance.
>
> SSM Session Manager is **not** an option: the agent is unregistered and the account has no SSM instance-management role (console log: `Systems Manager's instance management role is not configured for account`).

---

## 2. Cloudflare

| Property | Value |
|---|---|
| Domain (apex) | `amendi.dev` (registered through Cloudflare Registrar) |
| Cloudflare account | Marius's personal (`mariusbloemhof@gmail.com`) |
| Zone ID | `3974a2b90766e2cbb8d398e78923b048` |
| API token | `solamon-dns-edit`, scoped to `Zone › DNS › Edit` on `amendi.dev` only. **Originally pasted into chat history; should be rotated.** Stored locally at `C:\Users\Marius\.cloudflare-token`. |

### DNS records

| Record | Type | Value | TTL | Proxied |
|---|---|---|---|---|
| `cloud.amendi.dev` | A | `13.247.131.5` | 300 | **No** (DNS-only / grey-cloud) |

Record ID `40a6086ff01fa9238c31232ac8da0e9a`. The record **must remain DNS-only** — Caddy needs the real client IP for the Let's Encrypt HTTP-01 challenge, and Mosquitto's MQTT TLS on 8883 is not proxyable on Cloudflare's free tier.

---

## 3. Tailscale

| Property | Value |
|---|---|
| Account | Marius's personal (`mariusbloemhof@gmail.com`, GitHub SSO) |
| Tailnet name (auto-generated) | `tailcc347e.ts.net` |
| Plan | Free tier (limit: 100 devices, 3 users) |
| MagicDNS | **Pending — toggle on at <https://login.tailscale.com/admin/dns> if not yet** |

### Tags (defined in ACL)

| Tag | Owners | Applied to |
|---|---|---|
| `tag:admin` | `autogroup:admin` | Marius's laptop |
| `tag:cloud` | `autogroup:admin` | EC2 (`solamon-cloud-prod`) |
| `tag:pi` | `autogroup:admin` | future Pis |

### Devices (current)

| Device | Tailnet IP | Tag | OS |
|---|---|---|---|
| `marius-laptop` | `100.65.186.104` | *(user-owned, not tagged — see ACL summary)* | Windows |
| `solamon-cloud-prod` | `100.77.122.23` | `tag:cloud`, **key expiry disabled** (2026-09-04) | Linux (Ubuntu 24.04) |

### ACL summary

`tag:admin` may SSH to `tag:pi` and `tag:cloud` as users `pi`, `ubuntu`, `solamon`, `root`. **As of 2026-09-04 the laptop is user-owned rather than `tag:admin`**, so the policy also grants `autogroup:member → tag:cloud:*, tag:pi:*` (acls) and `autogroup:member → tag:pi, tag:cloud` as `ubuntu`/`root` (ssh). Without those two rules the laptop cannot reach the tagged EC2 at all. Do **not** fix this by tagging the laptop: a tagged laptop stops being `autogroup:member` and loses access to Marius's other personal devices. `tagOwners` must exist for all three tags, or the auth-key page won't offer them. No `pi → pi` or `pi → cloud` rules — the Pi-to-cloud channel is the public MQTT TLS, not the tailnet. Full ACL JSON is what was pasted into <https://login.tailscale.com/admin/acls>.

### Auth keys (status)

| Description | Tag | Reusable | Expiry | Stored where |
|---|---|---|---|---|
| `solamon cloud EC2` | `tag:cloud` | no | 90 days from issue | already consumed (one-shot); 1Password "Solamon Tailscale — cloud key" |
| `solamon Pi installer` | `tag:pi` | yes | 90 days from issue | 1Password "Solamon Tailscale — Pi key" — **passed to `solamon-edge-install.sh --tailscale-auth-key` later** |

**Both keys were pasted in chat — should be rotated** (Tailscale console → Settings → Keys → revoke old + regenerate). Re-issue the Pi key as reusable + tag:pi when rotating; revoke the cloud key after rotation since the EC2 is already authenticated and doesn't need it again.

---

## 4. Local artifacts (Marius's laptop)

| Path | What |
|---|---|
| `C:\Users\Marius\.aws\config` | AWS CLI profile `solamon` |
| `C:\Users\Marius\.aws\credentials` | AWS access keys for IAM user `Marius` |
| `C:\Users\Marius\.ssh\solamon-bootstrap` | EC2 bootstrap SSH private key (ed25519, no passphrase) |
| `C:\Users\Marius\.ssh\solamon-bootstrap.pub` | Public half (also imported to EC2 as key pair `solamon-bootstrap`) |
| `C:\Users\Marius\.cloudflare-token` | Cloudflare API token (locked to user, mode 600 equivalent) |
| `D:\Docker\` | Docker Desktop binaries (≈ 4 GB) |
| `D:\Docker\data\` | Docker Desktop WSL2 data (`docker_data.vhdx`, `ext4.vhdx`) |
| `D:\install\aws-bootstrap.ps1` | The Phase 2 AWS provisioning script (idempotent) |
| `D:\install\provision-ec2.ps1` | The EC2 launch script (idempotent) |
| `C:\Program Files\Tailscale\` | Tailscale Windows client |
| `C:\Program Files\Amazon\AWSCLIV2\` | AWS CLI v2 |

---

## 5. How to do common things

### SSH to the cloud EC2

```powershell
# Via Tailscale tailnet IP (current method — preferred)
ssh ubuntu@100.77.122.23

# Via Tailscale MagicDNS (works once MagicDNS is enabled in admin)
ssh ubuntu@solamon-cloud-prod

# Via public IP — DOES NOT WORK, even with a security-group rule: host ufw allows SSH
# only on tailscale0. See the warning in §1.6 for the real recovery paths.
```

Tailscale SSH on the EC2 means you don't need the bootstrap key after the tailnet join — Tailscale identity authenticates. The bootstrap key is still in `C:\Users\Marius\.ssh\solamon-bootstrap` as belt-and-braces fallback.

### Push a Docker image to ECR (from a dev box)

Manual path (CI is the intended path — see `ecr-and-images.md §4`):

```powershell
aws --profile solamon --region af-south-1 ecr get-login-password |
  docker login --username AWS --password-stdin 556671502751.dkr.ecr.af-south-1.amazonaws.com
docker buildx build --platform linux/arm64 `
    --tag 556671502751.dkr.ecr.af-south-1.amazonaws.com/solamon-cloud-app:v0.1.0 `
    --push services/cloud-app/
```

### Update the DNS record

```powershell
$token = Get-Content "$env:USERPROFILE\.cloudflare-token" -Raw
$h = @{ Authorization = "Bearer $($token.Trim())"; 'Content-Type' = 'application/json' }
$zoneId = '3974a2b90766e2cbb8d398e78923b048'
$recordId = '40a6086ff01fa9238c31232ac8da0e9a'
$body = @{ type='A'; name='cloud'; content='<NEW-IP>'; ttl=300; proxied=$false } | ConvertTo-Json
Invoke-RestMethod -Method PUT `
    -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records/$recordId" `
    -Headers $h -Body $body
```

### Stop / start the EC2 (save cost during implementation pauses)

```powershell
# Stop (drops compute cost; EBS + EIP still charge ~$3/mo)
aws --profile solamon --region af-south-1 ec2 stop-instances --instance-ids i-028b3a7906dcd4185

# Start (Tailscale will re-establish automatically; same Elastic IP)
aws --profile solamon --region af-south-1 ec2 start-instances --instance-ids i-028b3a7906dcd4185
aws --profile solamon --region af-south-1 ec2 wait instance-running --instance-ids i-028b3a7906dcd4185
```

### See what's actually running

```powershell
aws --profile solamon --region af-south-1 ec2 describe-instances --instance-ids i-028b3a7906dcd4185 `
    --query 'Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress,PrivateIpAddress]' --output table
aws --profile solamon ecr describe-repositories --query 'repositories[].[repositoryName,createdAt]' --output table
aws --profile solamon ecr list-images --repository-name solamon-cloud-app --query 'imageIds[*]' --output table
& 'C:\Program Files\Tailscale\tailscale.exe' status
```

---

## 6. Monthly cost estimate (running, no app load)

| Item | Cost (USD/mo) | Cost (ZAR/mo @ R18.50) |
|---|---|---|
| EC2 t4g.small (24/7) | ~$12 | ~R 222 |
| EBS gp3 30 GB | ~$2.40 | ~R 44 |
| Elastic IP (associated) | $0 | R 0 |
| ECR storage (negligible until images pushed) | ~$0.10 | ~R 2 |
| S3 (negligible until backups start) | ~$0.10 | ~R 2 |
| CloudTrail management events | $0 (first trail free) | R 0 |
| Cloudflare DNS | $0 (free plan) | R 0 |
| Cloudflare Registrar (`amendi.dev`) | ~$1 | ~R 18 (~$12/yr amortised) |
| Tailscale | $0 (free plan) | R 0 |
| **Total idle** | **~$15** | **~R 290** |

When images are pushed and an actual workload runs, ECR storage + DB + log volumes grow. Budgets will alert at $30 first.

---

## 7. What's NOT provisioned (the wall)

> **Historical (2026-05-08 snapshot).** The deployment rows below were resolved in May: the stack is deployed and running. `release.yml` exists but **has never run** — there are no `v*` tags, so the running containers were built and deployed by hand and nothing is reproducible from CI yet.

| Pending | Required for | Tracked |
|---|---|---|
| `solamon-cloud-app` Docker image | `solamon-cloud-bootstrap.sh` to run | needs `packages/cloud_app/` implementation (SOL-8) |
| `solamon-edge-agent` Docker image | Pi install | needs `packages/edge_agent/` implementation (SOL-7) |
| `solamon-cloud-bootstrap.sh` execution on EC2 | bench Day 1 | blocked by image; spec also has bugs to fix per `review-2026-05-02.md` |
| `solamon-edge-install.sh` execution on Pi | bench Day 2+ | blocked by image |
| GitHub Actions `release.yml` workflow | image push pipeline | not yet committed (see `ecr-and-images.md §4`) |
| Pi 5 hardware setup | bench Day 2+ | Johan has procured the Pi, not yet imaged |
| AXM-WEB2 / Acuvim L bench unit | bench Day 3 (probe day) | available from Johan |

---

## 8. Known issues / follow-ups

1. **Cloudflare token + Tailscale auth keys** were pasted in chat. Rotate them when convenient.
2. **MagicDNS** may still need toggling on at <https://login.tailscale.com/admin/dns>. Without it, the short hostname `solamon-cloud-prod` doesn't resolve from the laptop — fall back to `100.77.122.23` or `cloud.amendi.dev`.
3. **The infrastructure spec docs reference `cloud.solamon.bloemhof.dev`.** Reality is `cloud.amendi.dev`. Spec docs not yet updated; bootstrap script's `--domain` argument needs to be set to the real value at run-time.
4. **`solamon-cloud-bootstrap.sh` has unfixed bugs** flagged in `review-2026-05-02.md` — Mosquitto TLS cert path, password file lifecycle, migration step. These must be addressed before first run.
5. **AWS CLI v2** is what's installed. Per the infrastructure review, the spec's `apt-get install awscli` (v1) on Pis should be migrated to v2 too — not yet addressed.
6. **`pi-ecr-puller` IAM keys** were saved to `D:\install\pi-ecr-puller-keys.txt`. **Still on disk as of 2026-09-04** — move to 1Password and delete.
7. **Cron filename mismatch.** The Mosquitto cert-reload cron is installed as `/etc/cron.d/solamon-mosquitto-reload`, but `cloud-bootstrap.md` §11 and `caddy-and-dns.md` §6.1 call it `solamon-mosquitto-cert-reload`. It works: the cert renewed 2026-09-05 and Mosquitto on 8883 serves the renewed cert. Check cron by **content**, not expected filename — it was misdiagnosed as missing once.
8. **Stale user-data** on `i-028b3a7906dcd4185` from the 2026-09-04 recovery attempt. Its auth key is revoked, so it's inert, but clear it at the next planned stop.
9. **Dashboard shows stale data as live.** The web UI renders the newest stored reading as `LIVE NOW` with "100% telemetry quality confidence" regardless of age. On 2026-09-04 it showed a 51-day-old reading that way, driving a sizing recommendation. Needs a staleness cutoff before clients see it.

---

## 9. Incident log and handover (2026-10-15)

### 9.1 Outage 2026-08-18 → 2026-09-04

| When (UTC) | What |
|---|---|
| 2026-07-15 14:41 | Last reading from the bench Acuvim (`solamon/bench/acuvim/CLD56020398/data`). The meter stopped connecting at all — no auth or TLS failures were logged, just silence. The cloud was healthy and received nothing for 34 days. |
| 2026-08-18 22:46 | AWS account `556671502751` **suspended**: the EC2 was stopped and both IAM access keys (`Marius`, `pi-ecr-puller`) went inactive. Authoritative source is `last -x reboot` on the box (ran May 8 → Aug 18, 102 days), not CloudTrail. |
| 2026-09-04 | Marius reinstated the account and reactivated the keys. The first `start-instances` failed with `Client.InvalidKMSKey`; CloudTrail showed `kms:CreateGrant` denied *"because the resource owner's account is not active"* while reinstatement propagated. A retry ~10 minutes later succeeded. |
| 2026-09-04 | 4 of 5 containers came back. `solamon-mosquitto` did not (exit 0 at the shutdown instant; `unless-stopped` didn't re-trigger, cause unknown) and was started manually with `docker compose -f /opt/solamon/docker-compose.yml up -d mosquitto`. **After any unplanned stop, check all five containers.** |
| 2026-09-04 | Tailscale node key expiry disabled on `solamon-cloud-prod` (it would have lapsed 2026-11-04 and cut the only SSH path). ACL rules for user-owned devices added (§3). |
| 2026-09-23 14:35 | Bench meter resumed publishing. **No backfill** — the AXM-WEB2 did not replay its offline cache, so 2026-07-15 → 2026-09-23 is a permanent gap. |

**Lesson:** this is a personal AWS account billed to a card. A suspension stops everything silently, and AWS terminates resources about 90 days into a suspension — including the EBS volume and the `solamon-backup-prod` backups in the same account. Keep the payment method current, and make sure the budget-alert mailbox is actually read.

### 9.2 Verified state on 2026-10-15

- `https://cloud.amendi.dev/client/login` → 200; `/api/v1/health` → `{"status":"ok","db":"ok","mqtt":"ok"}`
- All 5 containers up since 2026-09-04
- TLS cert renewed 2026-09-05, valid to 2026-12-04, served on both 443 and 8883
- Telemetry flowing: ~153k readings/day since 2026-09-24. The 90-day retention means stored data now starts 2026-09-23.
- Host crons present: `solamon-mosquitto-reload` (03:30), `solamon-pg-backup` (03:00), `solamon-ecr-refresh` (every 6 h)

### 9.3 Working on this from a Claude Code cloud session

A cloud session has the repo (GitHub) but none of the infrastructure credentials. Repo-only work (code, docs, tests, PRs) runs in the cloud sandbox.

Anything touching live infrastructure runs **on Marius's local machine**, via the desktop app's local-run approval:

| Access | What it's for |
|---|---|
| AWS CLI, profile `solamon`, region `af-south-1` | EC2 state, start/stop, CloudTrail, ECR, S3 backups |
| Tailscale | the only SSH path to the box: `ssh ubuntu@100.77.122.23` |
| Cloudflare API token | DNS for `amendi.dev` |

**This local access is set up as needed, and Marius facilitates the secrets.** Don't assume a profile, key, token or tailnet connection is already present, and never ask for a secret to be pasted into chat. When a task needs one, say which access is needed and why, and Marius provides it on the local machine. The laptop paths in §4 describe the original setup and may not match the machine in use.

**Open items (§8):** dashboard staleness (9), stale user-data (8), `pi-ecr-puller` key file (6), rotate the Cloudflare token (1), and a first CI release so deployments are reproducible (§7).
