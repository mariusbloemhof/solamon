# Infrastructure — AWS account

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Greenfield AWS account dedicated to the Solamon project. One-time setup. Drives every subsequent piece of infrastructure (EC2, ECR, Route 53, S3, IAM).

---

## 1. Account choice

A **fresh AWS account** specifically for this project rather than reusing an existing personal/business account. Reasons:

- Clean billing — every cent attributed to Solamon, easy to invoice.
- Clean blast radius — a misconfiguration here can't take down anything else.
- Clean credential boundaries — Marius's day-to-day AWS work doesn't share root access with the project.
- Easy hand-off — if Johan ever takes ownership of the project, transferring the whole account is a single AWS support ticket.

**Account name:** `solamon-prod` (slug-style; matches naming everywhere else).
**Root email:** a project-specific email alias — e.g., `aws-root+solamon@bloemhof.dev` or a shared mailbox both Marius and Johan can read. **Never** Marius's primary personal email (the root user is sacred; we don't want it tied to one person's identity).

## 2. Region

**Single region: `af-south-1` (Cape Town).** Locked from main spec §3.

- POPIA-clean by default; data resident in South Africa.
- All resources go here unless explicitly required elsewhere (none in MVP).
- The IAM control plane is global (you create users in `us-east-1` whether you mean to or not — that's OK).

## 3. Initial setup procedure

### 3.1 Create the account

1. Sign up at https://aws.amazon.com/, region South Africa, billing currency ZAR.
2. Provide payment card. Initial $1 hold; refunded.
3. Verify email + phone.
4. Choose **Basic Support** (free). Upgrading to Developer / Business support is a post-MVP cost decision.

### 3.2 Secure the root user

**Immediately after account creation, before doing anything else:**

1. **Enable MFA on the root user.** Use a hardware key (YubiKey) or a virtual MFA app (Authy, 1Password). Don't use SMS.
2. Generate a strong root password (40+ chars from a password manager).
3. Store both the password and MFA recovery codes in a shared password manager (1Password / Bitwarden) accessible to both Marius and Johan.
4. **Never use the root user for anything else.** It's an emergency-only credential. Day-to-day work uses an IAM user.

### 3.3 Create the admin IAM user

```
IAM → Users → Add user
  Name:                marius-admin
  Access type:         Console + Programmatic
  Permission policies: AdministratorAccess (managed policy)
  MFA:                 Enabled (hardware key or virtual MFA)
```

The IAM admin user is the day-to-day credential. CLI access keys go into `~/.aws/credentials` on Marius's laptop with profile name `solamon`. **CLI keys also rotate every 90 days** (set a calendar reminder).

For Johan if/when he needs AWS access:
- Separate IAM user `johan-admin` with the same `AdministratorAccess`.
- Both users have MFA enforced.

**Don't share IAM users.** Each human has their own.

### 3.4 Configure billing alerts

Predictable monthly cost for MVP is roughly:

| Resource | Estimate (ZAR / month) |
|----------|-------------------------|
| EC2 t4g.small (24/7) | ~R 250 |
| EBS storage (30 GB gp3) | ~R 60 |
| Data transfer out | ~R 20 (minimal — telemetry is incoming) |
| Route 53 hosted zone (if used) | ~R 12 |
| ECR Private (1 GB) | ~R 2 |
| S3 backup bucket (5 GB, occasional restore reads) | ~R 5 |
| **Total** | **~R 350** |

Set two budget alerts in **AWS Budgets**:
- **R 500/month** — informational; Marius is notified by email.
- **R 1000/month** — alert level; both Marius and Johan are notified, action is required (something is wrong with the deployment).

Both budgets cover the running calendar month with auto-reset.

### 3.5 Set the default region

In the AWS console: top-right → switch to `af-south-1`. This is per-session, not permanent — but training the muscle memory matters.

For the CLI on Marius's laptop:

```ini
# ~/.aws/config
[profile solamon]
region = af-south-1
output = json
```

```ini
# ~/.aws/credentials
[solamon]
aws_access_key_id = ...
aws_secret_access_key = ...
```

Then `export AWS_PROFILE=solamon` (or use `--profile solamon` on each command).

## 4. IAM groups + roles (designed for the future)

For MVP we only need the `marius-admin` user. But create the IAM groups + roles now so the post-MVP migration to AWS-native ([SOL-10](https://linear.app/solamon/issue/SOL-10)) is incremental rather than a re-org.

### 4.1 Groups

| Group | Purpose | MVP members |
|-------|---------|-------------|
| `Admins` | Full account access (the IAM admin users) | `marius-admin`, eventually `johan-admin` |
| `Developers` | Read everything, write to ECR + S3 backup buckets, EC2 access via SSM (post-MVP) | (empty in MVP) |
| `Operators` | Read-only on production resources; can SSH to Pis via SSM (post-MVP) | (empty in MVP) |

### 4.2 Service roles

| Role | Used by | Permissions |
|------|---------|-------------|
| `ECRPullRole` | The Pi (when we move to AWS SSM hybrid activation) | `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` on `solamon-edge-agent` repo only |
| `S3BackupRole` | The cloud's backup sidecar | `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on `solamon-backup-prod` bucket only |
| `EC2InstanceRole` | The cloud EC2 (instance profile) | Combine ECRPullRole + S3BackupRole; CloudWatch metrics + logs |

In MVP only `EC2InstanceRole` is wired up (so the cloud bootstrap script can use IAM-instance-profile credentials instead of stuffing access keys into env vars). The Pi uses long-lived ECR pull credentials configured at install time (see [`ecr-and-images.md`](ecr-and-images.md) §4) until the SSM migration.

## 5. Service quotas to watch

Out of the box, AWS af-south-1 has fairly generous default quotas. The ones to watch:

| Service | Default quota | Our use |
|---------|--------------|---------|
| EC2 vCPU (T-family) | 32 | 2 (one t4g.small) |
| EBS storage | 50 TB (provisional) | 30 GB |
| Elastic IPs | 5 | 1 |
| Route 53 hosted zones | 50 | 1 |
| ECR repositories | 10000 | 1-3 |

No quota uplift requests needed for MVP.

## 6. CloudTrail (audit log)

**Enable CloudTrail** on the account to log every API call. Default trail captures the last 90 days for free; configure it to also write to an S3 bucket (`solamon-cloudtrail-prod`) for indefinite retention.

This is cheap insurance — if anything goes weird ("who deleted the Postgres volume?") the audit trail tells you. Configure once; never look at it unless you need to.

## 7. Tear-down procedure

If the project is ever wound down or transferred:

1. Stop all EC2 instances (don't terminate immediately — gives a chance for second-thought).
2. Wait one billing cycle to confirm no missed dependencies.
3. Delete EC2, ECR repos, S3 buckets, Route 53 zone, IAM users.
4. Close the AWS account from My Account → Close Account.

The shared password manager keeps the root credentials available throughout this process.

## 8. Acceptance

- Account created in af-south-1, root MFA enabled.
- `marius-admin` IAM user created with admin policy + MFA + CLI keys.
- Billing alerts at R 500 and R 1000.
- CloudTrail enabled with an S3 trail.
- IAM groups (`Admins`, `Developers`, `Operators`) and service roles (`EC2InstanceRole`, `ECRPullRole`, `S3BackupRole`) created — most empty in MVP, ready for SOL-10.
- Marius's laptop can `aws --profile solamon sts get-caller-identity` and see `arn:aws:iam::ACCOUNT-ID:user/marius-admin`.

## 9. Cross-references

- [`ecr-and-images.md`](ecr-and-images.md) — the first thing we put in the account
- [`cloud-bootstrap.md`](cloud-bootstrap.md) — provisions the EC2 in this account
- [`../cloud/data-model.md`](../cloud/data-model.md) §8 — S3 bucket security requirements for backups
