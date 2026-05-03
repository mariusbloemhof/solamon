# Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Stand up the AWS account; provision the EC2 + DNS; run `solamon-cloud-bootstrap.sh` to a green health check; flash a Pi and run `solamon-edge-install.sh` to a green heartbeat. Plus the ARM64 release pipeline that pushes images to ECR, the `cloud_app/Dockerfile.md` contract, and the operator scripts (`update.sh`, `decommission.sh`) referenced in the spec.

**Architecture:** Mostly already authored — the bash scripts and spec docs landed in the spec phase. This plan FINISHES the infrastructure tier: adds the missing release CI (`.github/workflows/release.yml`), the `Dockerfile.md` spec, the operator scripts, the bench-rehearsal verification protocol, and the spec-to-script consistency tests.

**Tech Stack:** Bash 5, Docker 25+, Caddy 2, Mosquitto 2, Timescale 2.14-pg16, Tailscale, AWS CLI v2, GitHub Actions OIDC.

**Linear:** SOL-21.

**Conventions:** [`2026-05-03-conventions.md`](2026-05-03-conventions.md).

**Spec source of truth:**
- [`docs/specs/infrastructure/`](../../specs/infrastructure/) (all files)
- [`docs/specs/infrastructure/scripts/solamon-cloud-bootstrap.sh`](../../specs/infrastructure/scripts/solamon-cloud-bootstrap.sh)
- [`docs/specs/infrastructure/scripts/solamon-edge-install.sh`](../../specs/infrastructure/scripts/solamon-edge-install.sh)

**Depends on:** all five other plans complete (this deploys what they build).

---

## File structure (added by this plan)

```
solamon/
├── .github/workflows/
│   ├── release.yml                                # tagged-release: build + push to ECR
│   └── infrastructure.yml                         # bash -n + spec/script consistency
├── docs/specs/infrastructure/
│   ├── update-script.md                           # contract for update.sh
│   ├── decommission-script.md                     # contract for decommission.sh
│   └── scripts/
│       ├── solamon-cloud-update.sh                # bumps cloud-app image
│       ├── solamon-edge-update.sh                 # bumps edge-agent image
│       └── solamon-edge-decommission.sh
├── docs/specs/cloud/
│   └── Dockerfile.md                              # contract for the cloud-app image
└── tests/infrastructure/                          # spec-script consistency tests
    ├── test_bash_n.py
    ├── test_step_counts_match_spec.py
    └── test_spec_cross_references.py
```

---

## Task 1: `cloud/Dockerfile.md` — pin the image contract

The cloud bootstrap script assumes the cloud-app image ships `psql`, `/app/migrations/`, and the `cloud_app.seed_reference_data` Python module. None of this is currently spec'd. **The bootstrap script's migration step won't work without this.**

**Files:**
- Create: `docs/specs/cloud/Dockerfile.md`

- [ ] **Step 1: Write the spec**

```markdown
# Cloud-app Dockerfile contract

**Spec group:** [cloud](README.md)
**Linear:** [SOL-8](https://linear.app/solamon/issue/SOL-8)
**Implementation:** [`packages/cloud_app/Dockerfile`](../../../packages/cloud_app/Dockerfile)

The cloud-bootstrap script assumes specific image layout. This document pins what the cloud-app image MUST ship.

## 1. Base image

Python 3.12 slim Bookworm, ARM64 (`linux/arm64`).

## 2. Runtime tools that must be on PATH

- `psql` (Postgres client) — used by the bootstrap script's migration step.
  Install via `apt-get install -y postgresql-client`.
- `python` — for the seed script.

## 3. Application layout inside the image

```
/app/
├── migrations/
│   └── 0001_initial.sql      # bundled from packages/cloud_app/migrations/
├── architecture/             # bundled at /app/architecture (catalog + profiles)
├── openapi.yaml              # served at /api/v1/openapi.json (FastAPI also generates dynamically)
└── web/                      # built dist of packages/web_ui (next export)
    └── server.js
```

## 4. Environment

- `PYTHONUNBUFFERED=1`
- `PORT=8000` (FastAPI listens on 0.0.0.0:8000)
- `WEB_PORT=3000` (Next.js listens on 0.0.0.0:3000 when run via `node /app/web/server.js`)

## 5. Entry points

- Default `CMD ["python", "-m", "cloud_app"]` — runs the FastAPI + ingestion + control relay process.
- Web mode: `docker compose run --rm app node /app/web/server.js` — runs the Next.js server.
- Migration: `docker compose run --rm app psql "..." -f /app/migrations/0001_initial.sql`.
- Seed: `docker compose run --rm -e ADMIN_EMAIL=... app python -m cloud_app.seed --catalog /app/architecture/logical_metrics.yaml --profiles /app/architecture/profiles --site-mqtt-password ...`.

## 6. Build context

The Dockerfile sits at `packages/cloud_app/Dockerfile` but expects build context to be the **repo root** (so it can copy `packages/profile_loader` + `architecture/` + `packages/web_ui/.next/standalone/`):

```bash
docker buildx build --platform linux/arm64 \
    -f packages/cloud_app/Dockerfile -t solamon-cloud-app:vX.Y.Z .
```

## 7. Acceptance

A built image must satisfy:
1. `docker run --rm <image> psql --version` → exits 0, prints version.
2. `docker run --rm <image> python -m cloud_app --help` → no import errors.
3. `docker run --rm <image> ls /app/migrations/0001_initial.sql` → file exists.
4. `docker run --rm <image> ls /app/architecture/profiles/acuvim_l.yaml` → file exists.
5. `docker run --rm <image> ls /app/web/server.js` → file exists (web bundle present).
```

- [ ] **Step 2: Update the cloud_app Dockerfile to satisfy this contract**

Verify [`packages/cloud_app/Dockerfile`](packages/cloud_app/Dockerfile) (created in cloud plan Task 17) ships these. Add `web/` bundling — apply when the web_ui plan completes:

```dockerfile
# Append to packages/cloud_app/Dockerfile after the existing builder stage:
FROM node:20-bookworm-slim AS web-builder
WORKDIR /web
COPY packages/web_ui /web
RUN corepack enable && pnpm install --frozen-lockfile && pnpm prebuild && pnpm build

# Then in the final image stage, replace `RUN mkdir -p /app/web` with:
COPY --from=web-builder /web/.next/standalone /app/web
COPY --from=web-builder /web/.next/static /app/web/.next/static
```

- [ ] **Step 3: Commit**

```bash
git add docs/specs/cloud/Dockerfile.md packages/cloud_app/Dockerfile
git commit -m "spec(cloud): Dockerfile.md contract + bundle web_ui dist into final image"
```

---

## Task 2: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'edge-agent-v*.*.*'
      - 'cloud-app-v*.*.*'

permissions:
  id-token: write       # required for AWS OIDC
  contents: read

env:
  AWS_REGION: af-south-1
  ECR_ROLE: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsECRPushRole

jobs:
  edge-agent:
    if: startsWith(github.ref, 'refs/tags/edge-agent-v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Extract version
        id: ver
        run: echo "version=${GITHUB_REF##*/edge-agent-}" >> "$GITHUB_OUTPUT"
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ env.ECR_ROLE }}
          aws-region: ${{ env.AWS_REGION }}
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - uses: docker/setup-buildx-action@v3
      - name: Build + push edge-agent
        uses: docker/build-push-action@v5
        with:
          context: .
          file: packages/edge_agent/Dockerfile
          platforms: linux/arm64
          push: true
          tags: |
            ${{ steps.ecr.outputs.registry }}/solamon-edge-agent:${{ steps.ver.outputs.version }}
            ${{ steps.ecr.outputs.registry }}/solamon-edge-agent:latest
            ${{ steps.ecr.outputs.registry }}/solamon-edge-agent:sha-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  cloud-app:
    if: startsWith(github.ref, 'refs/tags/cloud-app-v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Extract version
        id: ver
        run: echo "version=${GITHUB_REF##*/cloud-app-}" >> "$GITHUB_OUTPUT"
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ env.ECR_ROLE }}
          aws-region: ${{ env.AWS_REGION }}
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install
      - run: pnpm --filter web_ui prebuild
      - run: pnpm --filter web_ui build
      - uses: docker/setup-buildx-action@v3
      - name: Build + push cloud-app (with bundled web)
        uses: docker/build-push-action@v5
        with:
          context: .
          file: packages/cloud_app/Dockerfile
          platforms: linux/arm64
          push: true
          tags: |
            ${{ steps.ecr.outputs.registry }}/solamon-cloud-app:${{ steps.ver.outputs.version }}
            ${{ steps.ecr.outputs.registry }}/solamon-cloud-app:latest
            ${{ steps.ecr.outputs.registry }}/solamon-cloud-app:sha-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Document AWS_ACCOUNT_ID secret**

Append to `docs/specs/infrastructure/aws-account-setup-checklist.md` §C:

```
- [ ] In repo settings → Secrets and variables → Actions, add `AWS_ACCOUNT_ID` (12-digit
      account number). The release workflow uses it to assume `GitHubActionsECRPushRole`.
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml docs/specs/infrastructure/aws-account-setup-checklist.md
git commit -m "ci(infrastructure): release workflow — tag-triggered ARM64 push to ECR"
```

---

## Task 3: `update.sh` operator scripts

**Files:**
- Create: `docs/specs/infrastructure/update-script.md`
- Create: `docs/specs/infrastructure/scripts/solamon-cloud-update.sh`
- Create: `docs/specs/infrastructure/scripts/solamon-edge-update.sh`

- [ ] **Step 1: Write the spec**

```markdown
# Update script contracts

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Two small operator scripts for in-place image bumps. Distinct from the bootstrap scripts (which assume fresh hardware).

## solamon-cloud-update.sh

Inputs:
- `--cloud-image-tag vX.Y.Z` (required)

Steps:
1. Pre-flight: must be in `/opt/solamon`; `.env` must exist.
2. Update `CLOUD_IMAGE_TAG=vX.Y.Z` in `/opt/solamon/.env`.
3. `aws ecr get-login-password ... | docker login ...`.
4. `docker compose pull app web`.
5. **Run any new migrations.** Query `app.schema_migrations` for the highest applied filename; for every `migrations/[NNNN]*.sql` newer, run `docker compose run --rm app psql -f ...`.
6. `docker compose up -d app web`. **Postgres + Mosquitto + Caddy left running.**
7. Wait up to 60 s for `/api/v1/health` green; fail with diagnostics otherwise.

## solamon-edge-update.sh

Inputs:
- `--edge-image-tag vX.Y.Z` (required)

Steps:
1. `aws ecr get-login-password ... | docker login ...` (refreshes if cron skipped a beat).
2. Update the `image:` tag in `/opt/solamon/docker-compose.yml`.
3. `docker compose pull edge-agent`.
4. `docker compose up -d edge-agent`.
5. Wait up to 90 s for the next heartbeat in `${CLOUD_URL}/api/v1/sites/${SITE_SLUG}/health` showing the expected `edge_version`.
```

- [ ] **Step 2: Write the cloud update script**

```bash
# docs/specs/infrastructure/scripts/solamon-cloud-update.sh
#!/usr/bin/env bash
# solamon-cloud-update.sh — bump the cloud-app image in place.
# Spec: docs/specs/infrastructure/update-script.md
# Linear: SOL-21

set -euo pipefail

CLOUD_IMAGE_TAG=""
ECR_REGION="af-south-1"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cloud-image-tag) CLOUD_IMAGE_TAG="$2"; shift 2 ;;
        -h|--help)
            grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
            exit 0 ;;
        *) echo "✗ unknown arg: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$CLOUD_IMAGE_TAG" ]] || { echo "✗ --cloud-image-tag required" >&2; exit 1; }
cd /opt/solamon
[[ -f .env ]] || { echo "✗ /opt/solamon/.env missing — was bootstrap run?" >&2; exit 1; }

# 1. Update env
sed -i "s|^CLOUD_IMAGE_TAG=.*|CLOUD_IMAGE_TAG=${CLOUD_IMAGE_TAG}|" .env
# shellcheck disable=SC1091
source .env

# 2. ECR login
aws ecr get-login-password --region "$ECR_REGION" | \
    docker login --username AWS --password-stdin "$ECR_REGISTRY"

# 3. Pull
docker compose pull app web

# 4. Migrations: replay any newer than what schema_migrations has applied.
APPLIED=$(docker compose exec -T postgres \
    psql -U solamon -d solamon -t -A -c \
    "SELECT filename FROM app.schema_migrations ORDER BY filename;" 2>/dev/null || echo "")
for migration in /opt/solamon/migrations/[0-9]*.sql; do
    [[ -e "$migration" ]] || continue
    name=$(basename "$migration")
    if ! grep -qx "${name}" <<< "${APPLIED}"; then
        echo "→ applying ${name}"
        docker compose run --rm app \
            psql "host=postgres user=solamon password=${DB_PASSWORD} dbname=solamon" \
            -f "/app/migrations/${name}"
    fi
done

# 5. Roll the app + web
docker compose up -d app web

# 6. Health check
for i in $(seq 1 12); do
    if curl -fsS -m 10 "https://${DOMAIN}/api/v1/health" 2>/dev/null \
        | jq -e '.status == "ok"' >/dev/null 2>&1; then
        echo "✓ ${CLOUD_IMAGE_TAG} live; /api/v1/health green"
        exit 0
    fi
    sleep 5
done

echo "✗ /api/v1/health did not become green within 60 s"
docker compose logs --tail 50 app
exit 2
```

- [ ] **Step 3: Write the edge update script**

```bash
# docs/specs/infrastructure/scripts/solamon-edge-update.sh
#!/usr/bin/env bash
# solamon-edge-update.sh — bump the edge-agent image on a Pi in place.
# Spec: docs/specs/infrastructure/update-script.md
# Linear: SOL-21

set -euo pipefail

EDGE_IMAGE_TAG=""
ECR_REGION="af-south-1"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --edge-image-tag) EDGE_IMAGE_TAG="$2"; shift 2 ;;
        -h|--help)
            grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
            exit 0 ;;
        *) echo "✗ unknown arg: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$EDGE_IMAGE_TAG" ]] || { echo "✗ --edge-image-tag required" >&2; exit 1; }
[[ -d /opt/solamon ]] || { echo "✗ /opt/solamon missing — was edge install run?" >&2; exit 1; }
cd /opt/solamon

# Refresh ECR login (cron usually handles this).
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${ECR_REGION}.amazonaws.com"
aws ecr get-login-password --region "$ECR_REGION" | \
    docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Update the image tag in compose.
sed -i "s|solamon-edge-agent:[^[:space:]]*|solamon-edge-agent:${EDGE_IMAGE_TAG}|" docker-compose.yml

docker compose pull edge-agent
docker compose up -d edge-agent

echo "✓ edge agent rolled to ${EDGE_IMAGE_TAG}"
echo "  Verify in the cloud: heartbeat should show edge_version=${EDGE_IMAGE_TAG}"
```

- [ ] **Step 4: Validate scripts parse**

```bash
bash -n docs/specs/infrastructure/scripts/solamon-cloud-update.sh
bash -n docs/specs/infrastructure/scripts/solamon-edge-update.sh
```

- [ ] **Step 5: Commit**

```bash
git add docs/specs/infrastructure/update-script.md docs/specs/infrastructure/scripts/solamon-cloud-update.sh docs/specs/infrastructure/scripts/solamon-edge-update.sh
git commit -m "spec(infrastructure): update.sh contracts + scripts (cloud + edge in-place image bump)"
```

---

## Task 4: Pi decommission script

**Files:**
- Create: `docs/specs/infrastructure/decommission-script.md`
- Create: `docs/specs/infrastructure/scripts/solamon-edge-decommission.sh`

- [ ] **Step 1: Write spec + script**

```markdown
# docs/specs/infrastructure/decommission-script.md
# Decommission script

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Run on a Pi being permanently retired or moved to another site. Sequence:

1. `docker compose down -v` (removes volumes; data is already in cloud).
2. `tailscale logout` then `tailscale down`.
3. Shred secret files: `/etc/solamon/bootstrap.yaml`, `/etc/solamon/aws-credentials`.
4. Remove `/etc/solamon/`, `/var/lib/solamon/`, `/opt/solamon/`.
5. Print final message instructing the operator to: (a) remove the device from
   the Tailscale console, (b) deactivate the site row in the cloud admin,
   (c) physically wipe the SD card if hardware is reused.
```

```bash
# docs/specs/infrastructure/scripts/solamon-edge-decommission.sh
#!/usr/bin/env bash
# solamon-edge-decommission.sh — retire a Pi.
# Spec: docs/specs/infrastructure/decommission-script.md
# Linear: SOL-21

set -euo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "✗ must run as root" >&2; exit 1; }

echo "[1/5] Stopping containers + removing volumes..."
if [[ -f /opt/solamon/docker-compose.yml ]]; then
    cd /opt/solamon
    docker compose down -v || true
fi

echo "[2/5] Disconnecting Tailscale..."
tailscale logout 2>/dev/null || true
tailscale down 2>/dev/null || true

echo "[3/5] Shredding secret files..."
for f in /etc/solamon/bootstrap.yaml /etc/solamon/aws-credentials; do
    [[ -f "$f" ]] && shred -u "$f" 2>/dev/null || true
done

echo "[4/5] Removing /etc/solamon, /var/lib/solamon, /opt/solamon..."
rm -rf /etc/solamon /var/lib/solamon /opt/solamon
crontab -r 2>/dev/null || true
rm -f /etc/cron.d/solamon-ecr-refresh

echo
echo "✓ Pi decommissioned locally."
echo
echo "  Operator next steps:"
echo "    1. Tailscale admin console — remove device 'solamon-pi-{slug}'."
echo "    2. Cloud admin — deactivate the site row (or delete it)."
echo "    3. Wipe the SD card before reusing hardware."
```

- [ ] **Step 2: Validate + commit**

```bash
bash -n docs/specs/infrastructure/scripts/solamon-edge-decommission.sh
git add docs/specs/infrastructure/decommission-script.md docs/specs/infrastructure/scripts/solamon-edge-decommission.sh
git commit -m "spec(infrastructure): edge decommission script + spec"
```

---

## Task 5: Spec/script consistency tests

**Files:**
- Create: `tests/infrastructure/__init__.py`
- Create: `tests/infrastructure/test_bash_n.py`
- Create: `tests/infrastructure/test_step_counts_match_spec.py`
- Create: `tests/infrastructure/test_spec_cross_references.py`

- [ ] **Step 1: Failing tests**

```python
# tests/infrastructure/test_bash_n.py
"""Every committed shell script must be syntactically valid (`bash -n` clean)."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_all_scripts_parse():
    scripts = list((REPO / "docs/specs/infrastructure/scripts").glob("*.sh"))
    assert scripts, "no scripts found"
    failed = []
    for s in scripts:
        result = subprocess.run(["bash", "-n", str(s)], capture_output=True, text=True)
        if result.returncode != 0:
            failed.append(f"{s.name}: {result.stderr.strip()}")
    assert not failed, "\n".join(failed)
```

```python
# tests/infrastructure/test_step_counts_match_spec.py
"""TOTAL_STEPS in the bootstrap scripts must match the actual log_step count.

Drifts here cause the operator to see [16/22] forever; review #11 caught this once."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "docs/specs/infrastructure/scripts"


@pytest.mark.parametrize("name", ["solamon-cloud-bootstrap.sh", "solamon-edge-install.sh"])
def test_total_steps_matches_log_step_count(name: str):
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    match = re.search(r"^TOTAL_STEPS=(\d+)", text, re.MULTILINE)
    assert match, f"{name}: no TOTAL_STEPS= line"
    declared = int(match.group(1))
    actual = len(re.findall(r'^log_step "', text, re.MULTILINE))
    assert declared == actual, (
        f"{name}: TOTAL_STEPS={declared} but found {actual} log_step calls"
    )
```

```python
# tests/infrastructure/test_spec_cross_references.py
"""Every cross-reference link in the infrastructure specs must point at a real file."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO / "docs/specs/infrastructure"

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_every_relative_link_resolves():
    failures: list[str] = []
    for md in SPEC_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for link in LINK_RE.findall(text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = (md.parent / link.split("#", 1)[0]).resolve()
            if not target.exists():
                failures.append(f"{md.relative_to(REPO)}: link to '{link}' not found")
    assert not failures, "\n".join(failures)
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest tests/infrastructure -v
git add tests/infrastructure/
git commit -m "test(infrastructure): bash -n + step-count + cross-reference consistency"
```

---

## Task 6: `.github/workflows/infrastructure.yml`

**Files:**
- Create: `.github/workflows/infrastructure.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/infrastructure.yml
name: Infrastructure

on:
  push:
    branches: [master]
    paths:
      - "docs/specs/infrastructure/**"
      - "tests/infrastructure/**"
      - ".github/workflows/infrastructure.yml"
  pull_request:
    paths:
      - "docs/specs/infrastructure/**"
      - "tests/infrastructure/**"

permissions:
  contents: read

jobs:
  consistency:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install pytest
      - run: python -m pytest tests/infrastructure -v

  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          sudo apt-get install -y shellcheck
          shellcheck docs/specs/infrastructure/scripts/*.sh
```

- [ ] **Step 2: Run shellcheck locally + commit**

```bash
shellcheck docs/specs/infrastructure/scripts/*.sh    # if not installed: brew install shellcheck / apt install shellcheck
git add .github/workflows/infrastructure.yml
git commit -m "ci(infrastructure): bash-n + step-count + cross-ref consistency + shellcheck"
```

---

## Task 7: Bench rehearsal — Day 1 (cloud bootstrap end-to-end)

This is the human-driven verification, NOT automated CI. Document each step's expected output.

**Files:**
- Create: `docs/specs/infrastructure/bench-rehearsal.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Bench rehearsal runbook

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Two-day exercise that exercises every spec group end-to-end on real hardware.

## Day 1: Cloud bootstrap

### Prereqs
- Run through [`aws-account-setup-checklist.md`](aws-account-setup-checklist.md). Tick every item.
- Have an EC2 instance launched per checklist §G with bootstrap SSH access + EC2InstanceRole attached.
- Have an A record pointing the test domain at the EC2's elastic IP.

### Steps

1. SSH to the EC2 with the bootstrap key.
2. Run:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-cloud-bootstrap.sh \
     | sudo bash -s -- \
         --domain "cloud.solamon.bloemhof.dev" \
         --tailscale-auth-key "tskey-auth-..." \
         --cloud-image-tag "v0.1.0" \
         --letsencrypt-email "admin@bloemhof.dev"
   ```
3. Watch for `[1/20]` through `[20/20]`. Final line should be `✓ Cloud stack running` with admin credentials.
4. Save the printed admin password to your password manager.
5. Verify externally:
   ```bash
   curl https://cloud.solamon.bloemhof.dev/api/v1/health
   # → {"status":"ok","db":"ok","mqtt":"ok"}
   ```
6. Log into the web UI. Verify dashboard renders (no devices yet).

### Failure modes seen during rehearsal

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Bootstrap exits 4 at "ECR login failed" | EC2InstanceRole not attached or missing ECR permissions | Re-attach via console; re-run script (idempotent) |
| Caddy logs `obtain certificate: ... Lookup failure` | DNS not propagated yet | Wait 5-10 min for TTL 300; re-run |
| Mosquitto restart-loops | Caddy hasn't provisioned cert yet (script's wait timed out) | Re-run; the wait window extends with each retry |

## Day 2: Pi install

### Prereqs
- Day 1 completed; admin can sign into the cloud UI.
- Pi flashed with Raspberry Pi OS Lite (64-bit) per checklist §I and connected to the bench LAN.
- Acuvim L on the bench, IP confirmed (`nmap -p 502 192.168.1.0/24`).
- Per-site bearer token + Tailscale auth key + ECR pull credentials in hand.

### Steps

1. SSH to the Pi (via mDNS or LAN IP).
2. Drop the install config:
   ```bash
   sudo tee /tmp/install-config.yaml <<EOF
   site_slug: bench
   cloud_url: https://cloud.solamon.bloemhof.dev
   bearer_token: <bench bearer>
   tailscale_auth_key: tskey-auth-...
   ecr_access_key_id: AKIA...
   ecr_secret_access_key: ...
   device_host: 192.168.1.254
   EOF
   sudo chmod 600 /tmp/install-config.yaml
   ```
3. Run:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-edge-install.sh \
     | sudo bash -s -- --config /tmp/install-config.yaml
   ```
4. Watch [1/18]–[18/18]. Final: `✓ Edge agent ready`.
5. Within 90 s, the dashboard's `/sites/bench` should show the Pi's heartbeat.
6. Issue a `demand_window_minutes=30` command from the control panel. Verify it transitions through `pending → sent → confirmed` within ~2 s.

### Acceptance

- Day 1 + Day 2 both succeed without operator intervention beyond what's in the runbook.
- Heartbeat green within 90 s of Day 2 finishing.
- Control command lands the meter at the new value.
- Power-cycle the Pi; heartbeat resumes within 2 minutes.
```

- [ ] **Step 2: Commit**

```bash
git add docs/specs/infrastructure/bench-rehearsal.md
git commit -m "spec(infrastructure): bench rehearsal runbook (Day 1 cloud + Day 2 Pi)"
```

---

## Self-review

| Item | Task |
|------|------|
| `cloud_app/Dockerfile.md` contract | Task 1 |
| Web bundle copied into final cloud-app image | Task 1 |
| `release.yml` (tag-triggered ECR push, ARM64) | Task 2 |
| `solamon-cloud-update.sh` + spec | Task 3 |
| `solamon-edge-update.sh` + spec | Task 3 |
| `solamon-edge-decommission.sh` + spec | Task 4 |
| `bash -n` + step-count + cross-ref consistency tests | Task 5 |
| `infrastructure.yml` CI | Task 6 |
| Bench rehearsal runbook (Day 1 + Day 2) | Task 7 |

---

## Acceptance verification

```bash
# Local consistency
python -m pytest tests/infrastructure -v
shellcheck docs/specs/infrastructure/scripts/*.sh
bash -n docs/specs/infrastructure/scripts/*.sh

# Tagged release publishes images:
git tag cloud-app-v0.1.0
git push origin cloud-app-v0.1.0    # triggers .github/workflows/release.yml
# Verify in AWS console: ECR repo solamon-cloud-app has the new tag.

# Bench rehearsal:
# Run the steps in docs/specs/infrastructure/bench-rehearsal.md against real hardware.
# Both Day 1 and Day 2 acceptance criteria must pass.
```

---

## Out of scope

Per [`2026-05-03-conventions.md` §7](2026-05-03-conventions.md): SSM hybrid (SOL-10), AWS-native rearchitecture (SOL-10), HA/multi-region, multi-tenant.
