# Infrastructure — ECR and container images

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

The container images for the edge agent and (eventually) the cloud services live in **AWS ECR Private** in `af-south-1`. CI builds and pushes on tagged release; the Pi and the EC2 pull from there.

---

## 1. Repository layout

| ECR repository | What's in it | Pulled by |
|----------------|--------------|-----------|
| `solamon-edge-agent` | The Pi-side Python edge agent | Every Pi at install time + on update |
| `solamon-probe-cli` | Standalone CLI image (optional — could be inside `solamon-edge-agent` for MVP) | Same Pi, but only if probe is delivered as a separate container |
| `solamon-cloud-app` | FastAPI API + ingestion + control-relay container | The cloud EC2 |
| `solamon-web-ui` | Next.js operator dashboard | The cloud EC2 behind Caddy |
| ~~`solamon-cloud-postgres`~~ | _(MVP: not used.)_ The bootstrap script uses upstream `timescale/timescaledb:2.26.4-pg16` directly. The custom-image slot is reserved for if/when we need a Timescale build with extra extensions or our own retention-policy bundles. | n/a |

For MVP, ship two repos: `solamon-edge-agent` and `solamon-cloud-app`. The probe-cli ships inside the edge-agent image (single binary `solamon-probe` on PATH inside the container). Postgres uses the upstream image — no customisation worth versioning.

## 2. Architecture target

**ARM64 only.** Both targets are arm64 hardware:

- Pi 5: Cortex-A76, ARMv8 (`linux/arm64`)
- EC2 t4g.small: Graviton2 (`linux/arm64`)

Single-arch builds — `buildx` with `--platform linux/arm64` — sufficient. AMD64 builds aren't useful for our deployments and add CI time.

## 3. Image tagging

Each push tags two ways:

- `:vX.Y.Z` — semver release tag, immutable. The thing the Pi/cloud is configured to pull.
- `:latest` — moves with each push. **Don't pin to `:latest` in production** — only used for "what was the most recent image?" diagnostics.
- `:sha-abcdef0` — short git SHA, immutable. Useful for "the last commit before vX.Y.0" debug.

Production deploys reference the version tag; rollback = update the deploy config to the previous version tag and `docker compose pull && up -d`.

## 4. Build pipeline

GitHub Actions workflow at `.github/workflows/release.yml` (created during implementation):

```
Trigger: push of a git tag matching v*.*.*
Steps:
  1. Checkout the tagged commit
  2. Configure AWS credentials (OIDC role assumed via the GitHub Actions OIDC provider — see §5)
  3. Login to ECR (af-south-1)
  4. docker buildx build --platform linux/arm64 \
       --tag {ECR_URL}/solamon-edge-agent:vX.Y.Z \
       --tag {ECR_URL}/solamon-edge-agent:latest \
       --tag {ECR_URL}/solamon-edge-agent:sha-{shortSHA} \
       --push \
       services/edge-agent/
  5. Same for `solamon-cloud-app` and `solamon-web-ui`
  6. Run `aws ecr describe-images` to verify the tags landed
  7. Post a Slack/Discord notification (optional)
```

Build cache via GitHub Actions cache (`type=gha`) — first build of the day takes ~5 min, subsequent ~30 s.

For MVP, push-on-tag only. PR builds (CI smoke test the Dockerfile parses, run unit tests) live in a separate workflow.

## 5. Authentication: GitHub Actions → ECR via OIDC

GitHub Actions has built-in OIDC support; AWS IAM has built-in trust for GitHub OIDC. **No long-lived AWS credentials live in GitHub secrets** — the workflow assumes a role at run time.

### 5.1 IAM role: `GitHubActionsECRPushRole`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::{ACCOUNT-ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:mariusbloemhof/solamon:ref:refs/tags/v*"
        }
      }
    }
  ]
}
```

The condition restricts assumption to **tag pushes** on the `mariusbloemhof/solamon` repo only. A workflow run on a feature branch can't push to ECR.

### 5.2 Role's permissions policy

Scoped to ECR push on the two repos:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart",
        "ecr:DescribeImages"
      ],
      "Resource": [
        "arn:aws:ecr:af-south-1:{ACCOUNT-ID}:repository/solamon-edge-agent",
        "arn:aws:ecr:af-south-1:{ACCOUNT-ID}:repository/solamon-cloud-app",
        "arn:aws:ecr:af-south-1:{ACCOUNT-ID}:repository/solamon-web-ui"
      ]
    }
  ]
}
```

## 6. Pulling on the Pi

The Pi is **not** an AWS-managed instance (Tailscale handles management for MVP — see [`tailscale.md`](tailscale.md)). It can't use IAM instance profiles. Two options:

### 6.1 Option A: Long-lived ECR pull-only IAM user (chosen for MVP)

Create an IAM user `pi-ecr-puller` with **read-only** access to the ECR repos. CLI access keys go into `/etc/solamon/aws-credentials` on the Pi (mode 600). The install script writes these from the install-time arguments.

The container engine (Docker) uses the credentials via `aws ecr get-login-password --region af-south-1 | docker login --username AWS --password-stdin {ECR_URL}`. The `solamon-edge-install.sh` script runs this at install + sets up a small cron to refresh the login (ECR auth tokens expire every 12 hours).

A pull-only IAM user is acceptable for MVP because:
- One per project (not per Pi) — small blast radius if compromised.
- Rotated quarterly (calendar reminder).
- Read-only — even a stolen token can only pull public images, not push or delete.

**Rotation procedure.** Manual rotation is fine for MVP single-Pi but needs documenting; "calendar reminder" alone is forgotten-rotation waiting to happen. Procedure:

1. In the AWS console, generate a new access key for `pi-ecr-puller`. Don't disable the old one yet.
2. For every deployed Pi (run a list query against `app.site` to enumerate site slugs), tail-end SSH via Tailscale and rewrite `/etc/solamon/aws-credentials` with the new key + secret. Force a `docker login` to test.
3. Once every Pi has the new credentials and a successful login, disable the old access key in the AWS console.
4. After ~24 hours, delete the old access key entirely.

After site count > 2, this becomes annoying. The right next step is the SSM hybrid plan (§6.2 / [SOL-10](https://linear.app/solamon/issue/SOL-10)) — that eliminates the long-lived credentials entirely.

### 6.2 Option B: AWS SSM hybrid activation (post-MVP, [SOL-10](https://linear.app/solamon/issue/SOL-10))

When we move Pi management to SSM, each Pi gets registered as a managed instance with an attached IAM role. The role gives ECR pull permissions per-instance, with rotation handled by SSM.

This eliminates the long-lived credentials but adds the SSM agent + activation flow per-Pi.

## 7. Pulling on the cloud EC2

The EC2 has an **IAM instance profile** with `EC2InstanceRole` attached (from [`aws-account.md`](aws-account.md) §4.2). Permissions:

- ECR pull on `solamon-cloud-app` and `solamon-web-ui`
- S3 read/write on `solamon-backup-prod`
- CloudWatch metrics + logs

No credentials in env vars on the EC2. `aws ecr get-login-password` works automatically via the instance metadata service.

## 8. Image retention

ECR Private's lifecycle policy keeps:

- Last **5 versions** for each repository.
- Untagged images deleted after **7 days**.
- Images older than **90 days** deleted regardless of tag (covers the case where a `v0.0.1-rc1` tag from forever ago accumulates).

This avoids ECR storage growing unbounded.

## 9. Vulnerability scanning

ECR Private has built-in scanning (basic scanning, free tier). Enabled per repo. New image scans run on push.

For MVP we **review the scan output** but don't gate the deploy on it (most low-severity findings in Python base images are noise). When a HIGH or CRITICAL appears, the implementer triages: rebuild on a newer base image vs. accept and document.

Inspector V2 (deeper scanning) is post-MVP.

## 10. Acceptance

- Two ECR Private repositories created in af-south-1.
- GitHub Actions OIDC provider connected to the AWS account.
- `GitHubActionsECRPushRole` created and tested with a manual `aws sts assume-role-with-web-identity` from a test workflow.
- `pi-ecr-puller` IAM user created with read-only ECR access; access keys generated.
- Lifecycle policy applied (last 5 + untagged-7d + age-90d).
- Vulnerability scanning enabled on both repos.
- A test image pushed end-to-end (tagged `v0.0.0-test`); Pi and EC2 can both pull it.

## 11. Cross-references

- [`aws-account.md`](aws-account.md) §4.2 — service roles definitions
- [`pi-install.md`](pi-install.md) — how `solamon-edge-install.sh` configures ECR auth on the Pi
- [`cloud-bootstrap.md`](cloud-bootstrap.md) — how `solamon-cloud-bootstrap.sh` uses the EC2 instance profile to pull
