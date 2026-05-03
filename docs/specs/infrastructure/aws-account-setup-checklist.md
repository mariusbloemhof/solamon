# AWS account setup — operator checklist

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

The full prose description of the AWS account is in [`aws-account.md`](aws-account.md). This file is the **manual setup checklist** for everything that doesn't get automated by `solamon-cloud-bootstrap.sh` or `solamon-edge-install.sh`. Run through it before either script.

Tick each item as you complete it. Most steps are AWS console clicks; a few are CLI commands.

---

## A. Account creation (one-time)

- [ ] Greenfield AWS account exists, billing email is the project email (per [`aws-account.md`](aws-account.md) §1).
- [ ] Root user MFA enabled (hardware key preferred).
- [ ] Root user credentials stored in shared password manager — never used for daily work.
- [ ] Default region set to `af-south-1` in the console preferences.
- [ ] `af-south-1` opted in (some regions require explicit opt-in for new accounts).

## B. Billing alerts (one-time)

- [ ] CloudWatch billing alert at $5 / month.
- [ ] CloudWatch billing alert at $25 / month.
- [ ] CloudWatch billing alert at $100 / month (hard ceiling for MVP).
- [ ] Alert destinations: project email + SMS to Marius.
- [ ] Free Tier usage alerts enabled in Billing preferences.

## C. IAM groups + service roles (one-time)

Per [`aws-account.md`](aws-account.md) §4:

- [ ] IAM identity centre enabled (or fall back to IAM users for MVP — single-user is acceptable).
- [ ] Group `solamon-admins` exists with `AdministratorAccess` policy.
- [ ] Marius's IAM user created and added to `solamon-admins` (with MFA enforced).
- [ ] Service role `EC2InstanceRole` created with policy for ECR pull (`solamon-cloud-app`) + S3 read/write (`solamon-backup-prod`) + CloudWatch metrics/logs (per [`ecr-and-images.md`](ecr-and-images.md) §7). The cloud bootstrap **assumes this role exists and is attached as the EC2's instance profile** — without it the bootstrap fails at the ECR-login step (exit 4).
- [ ] Service role `GitHubActionsECRPushRole` created with the trust policy + permissions policy from [`ecr-and-images.md`](ecr-and-images.md) §5.1-5.2.
- [ ] OIDC provider for `token.actions.githubusercontent.com` registered in IAM (one-time per account).
- [ ] IAM user `pi-ecr-puller` created with read-only ECR access (per [`ecr-and-images.md`](ecr-and-images.md) §6.1). Generate the initial access key — store the secret immediately; it's shown once. The Pi install script consumes this credential.

## D. ECR repositories (one-time)

- [ ] `solamon-edge-agent` repo created (Private, af-south-1, image scan-on-push enabled).
- [ ] `solamon-cloud-app` repo created (same).
- [ ] Lifecycle policy on both: keep last 10 immutable tagged images; expire untagged after 7 days (per [`ecr-and-images.md`](ecr-and-images.md) §X — when added).

## E. S3 buckets (one-time)

- [ ] `solamon-backup-prod` created (af-south-1, default encryption enabled, public access blocked, versioning ON, object-lock NOT enabled — keeps the bucket cheap).
- [ ] Lifecycle policy: under prefix `postgres/`, transition to Glacier after 30 days, delete after 90 days.
- [ ] `solamon-cloudtrail-prod` created (same region; same encryption + access settings; lifecycle policy: Glacier after 30 days, expire after 365 days).

## F. CloudTrail (one-time)

- [ ] Multi-region trail created in af-south-1, named `solamon-org-trail`.
- [ ] Log destination: `s3://solamon-cloudtrail-prod/AWSLogs/`.
- [ ] Management events: read + write captured.
- [ ] Data events: skip (cost; we don't need bucket-level audit yet).
- [ ] Trail status: enabled.

## G. EC2 prep (per cloud install)

- [ ] Bootstrap SSH key pair created in af-south-1 (will be replaced by Tailscale SSH after bootstrap; held only for the install window).
- [ ] Elastic IP allocated (one per cloud instance; release if instance is terminated permanently).
- [ ] Security group `solamon-cloud-sg`: inbound 80 / 443 / 8883 from 0.0.0.0/0; inbound 22 from Tailscale CGNAT only (`100.64.0.0/10`); outbound all.
- [ ] EC2 launched with `t4g.small`, Ubuntu 24.04 LTS ARM64 AMI, 30 GB gp3 root, `EC2InstanceRole` attached as instance profile. **Without the instance profile**, `aws ecr get-login-password` fails at bootstrap step 6 (exit 4) — the bootstrap script's pre-flight checks for the instance profile and exits with a clear error.
- [ ] EC2 tags: `Name=solamon-cloud-prod`, `Project=solamon`, `Environment=production`.

## H. DNS (per domain)

Per [`caddy-and-dns.md`](caddy-and-dns.md) §2:

- [ ] A record for the chosen domain points at the elastic IP, TTL 300.
- [ ] (Optional) CNAME for `_acme-challenge.${DOMAIN}` if using DNS-01 (not in MVP).
- [ ] Wait at least 5 minutes after creating the A record before running the bootstrap (the bootstrap script polls `dig +short ${DOMAIN}` and won't start Caddy until the record resolves to the EC2's elastic IP — Caddy's HTTP-01 challenge fails if DNS hasn't propagated).

## I. Tailscale (one-time + per device)

Per [`tailscale.md`](tailscale.md):

- [ ] Tailscale account exists, both Marius + Johan added with MFA.
- [ ] ACL JSON deployed (per `tailscale.md §5`).
- [ ] Auth key generated for Pi installs (`tag:pi`, reusable, pre-authorised, 90-day expiry).
- [ ] Auth key generated for cloud install (`tag:cloud`, reusable, pre-authorised, 90-day expiry).

---

## Pre-flight gate

The two install scripts (`solamon-cloud-bootstrap.sh` and `solamon-edge-install.sh`) each run their own pre-flight checks. The most common failure mode is "the operator skipped a step in this checklist" — typically:

| Symptom | Skipped checklist item |
|---------|-----------------------|
| `solamon-cloud-bootstrap.sh` exits 4 at ECR login | C — `EC2InstanceRole` not attached |
| Caddy logs `obtain certificate: ... Lookup failure` | H — DNS record missing or not propagated |
| Pi install exits 4 at `docker pull` | C — `pi-ecr-puller` access key wrong / expired |
| Pi install exits 3 at "tailnet not online" | I — auth key expired / wrong tag |
| `pg-backup.sh` cron logs "no such bucket" | E — backup bucket not created |

If a script fails fast on a missing prerequisite, find the row in this checklist, fix it, re-run the script (both are idempotent).
