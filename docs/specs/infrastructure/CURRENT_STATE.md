# Infrastructure — current state (as-built)

**As of:** 2026-05-08
**Owner:** Marius Bloemhof
**Status:** All cloud infrastructure provisioned and verified. Application code (cloud_app, edge_agent) not yet implemented — see "What's NOT provisioned" below.

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

The bootstrap-time public-IP SSH rule (`156.155.54.131/32`) was deliberately revoked once Tailscale SSH was confirmed working. To re-add temporarily for emergency access:

```powershell
$myIp = (Invoke-RestMethod -Uri 'https://checkip.amazonaws.com' -TimeoutSec 5).Trim()
aws --profile solamon --region af-south-1 ec2 authorize-security-group-ingress `
    --group-id sg-03a9e7b940e0c9aa1 --protocol tcp --port 22 --cidr "$myIp/32"
```

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
| `marius-laptop` | `100.65.186.104` | `tag:admin` | Windows |
| `solamon-cloud-prod` | `100.77.122.23` | `tag:cloud` | Linux (Ubuntu 24.04) |

### ACL summary

`tag:admin` may SSH to `tag:pi` and `tag:cloud` as users `pi`, `ubuntu`, `solamon`, `root`. No `pi → pi` or `pi → cloud` rules — the Pi-to-cloud channel is the public MQTT TLS, not the tailnet. Full ACL JSON is what was pasted into <https://login.tailscale.com/admin/acls>.

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

# Via public IP — DOES NOT WORK (port 22 closed from internet by SG)
# Only works if you re-authorise your current IP first (see "emergency access" above).
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
6. **`pi-ecr-puller` IAM keys** were saved to `D:\install\pi-ecr-puller-keys.txt`. Confirm this file has been moved to 1Password and deleted from disk.
