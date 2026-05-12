# Infrastructure — Cloud bootstrap

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)
**Machine artifact:** [`scripts/solamon-cloud-bootstrap.sh`](scripts/solamon-cloud-bootstrap.sh)

The contract for `solamon-cloud-bootstrap.sh` — the script that takes a fresh EC2 Ubuntu 24.04 LTS ARM64 instance and turns it into a running Solamon cloud stack.

---

## 1. Operator runbook (high-level)

1. **Provision an EC2** in af-south-1:
   - Instance type: `t4g.small` (2 vCPU, 2 GB RAM, ARM64). Upgrade to `t4g.medium` if memory pressure shows up.
   - AMI: Ubuntu 24.04 LTS ARM64 (Canonical's official image; `ami-...` lookup via `aws ec2 describe-images`).
   - Storage: 30 GB gp3 root volume.
   - Security group: ports 80, 443, 8883 from 0.0.0.0/0; port 22 from Tailscale CGNAT (100.64.0.0/10) only.
   - IAM instance profile: `EC2InstanceRole` (per [`aws-account.md`](aws-account.md) §4.2).
   - SSH key: a one-time bootstrap key (we'll switch to Tailscale SSH after the script runs).
   - Elastic IP: associated.
   - Tags: `Name=solamon-cloud-prod`, `Project=solamon`, `Environment=production`.

2. **Configure DNS** to point your chosen domain at the EC2's elastic IP. See [`caddy-and-dns.md`](caddy-and-dns.md) §2.

3. **SSH to the EC2** with the bootstrap key (one-time): `ssh ubuntu@<elastic-ip>`.

4. **Run the bootstrap script:**
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-cloud-bootstrap.sh | sudo bash -s -- \
       --domain "cloud.solamon.bloemhof.dev" \
       --tailscale-auth-key "tskey-auth-..." \
       --cloud-image-tag "v0.1.0" \
       --web-image-tag "v0.1.0" \
       --letsencrypt-email "admin@bloemhof.dev"
   ```

5. **Wait for the script to finish** (~30 minutes — the heaviest step is Postgres init). Final lines:
   ```
   ✓ Cloud stack running.
     Web UI:     https://cloud.solamon.bloemhof.dev
     API:       https://cloud.solamon.bloemhof.dev/api/v1
     MQTT:      mqtts://cloud.solamon.bloemhof.dev:8883
     Admin user: admin@solamon  /  <generated-password-shown-once>
   ```

6. **Save the admin password** in your password manager. It will not be reprinted.

7. **Verify health:**
   ```bash
   curl https://cloud.solamon.bloemhof.dev/api/v1/health
   # { "status": "ok", "db": "ok", "mqtt": "ok" }
   ```

8. **Set up the first site** in the cloud admin (creates the per-site MQTT credentials that the Pi installer needs — see §10 below).

## 2. Script inputs

| Argument | Type | Notes |
|----------|------|-------|
| `--domain` | DNS name | Where the cloud is reachable |
| `--tailscale-auth-key` | `tskey-auth-...` | Pre-authorised, tagged `tag:cloud` |
| `--cloud-image-tag` | string | ECR tag for the cloud-app image, e.g. `v0.1.0`. Required (don't ship `latest` to prod). |
| `--web-image-tag` | string | ECR tag for the web-ui image. Defaults to `--cloud-image-tag` when omitted. |
| `--letsencrypt-email` | email | Account email for Let's Encrypt |
| `--admin-email` | email | (Optional) Admin user's email. Default: `admin@solamon`. |
| `--db-password` | secret string | (Optional) Postgres password. If omitted, generated and printed. |
| `--restore-from` | S3 URI | (Optional) For disaster-recovery restore — see §11. |

## 3. Steps

### 3.1 Pre-flight (steps 1-3)

1. Verify root.
2. Verify Ubuntu 24.04 LTS ARM64.
3. Verify EC2 IMDSv2 instance profile is reachable: `curl -s -H "X-aws-ec2-metadata-token-ttl-seconds: 60" http://169.254.169.254/latest/api/token` returns a token. Without this, ECR pull won't work.

### 3.2 System packages (step 4)

4. `apt update && apt install -y docker.io docker-compose-plugin awscli ca-certificates curl jq`.

### 3.3 Tailscale (step 5)

5. Install Tailscale (per [`tailscale.md`](tailscale.md) §1) and join the tailnet with the cloud auth key + `tag:cloud` + hostname `solamon-cloud-prod`.

### 3.4 ECR login (step 6)

6. `aws ecr get-login-password --region af-south-1 | docker login --username AWS --password-stdin {ECR_URL}`. Uses the EC2 instance profile — no static credentials. Sets up a cron to refresh every 6 hours.

### 3.5 Pull images (step 7)

7. Pull `{ECR_URL}/solamon-cloud-app:{TAG}` and the upstream `timescale/timescaledb:2.26.4-pg16`, `eclipse-mosquitto:2`, `caddy:2`.

### 3.6 Configuration (steps 8-12)

8. Create `/opt/solamon/` directory tree (volumes for postgres, mosquitto, caddy data; config dirs).
9. Generate secrets:
   - `JWT_SECRET` — 32-byte random for FastAPI's JWT signing
   - `NEXTAUTH_SECRET` — 32-byte random for NextAuth's cookie encryption
   - `DB_PASSWORD` — 24-char random Postgres superuser password
   - `MQTT_CLOUD_PASSWORD` — 24-char random for the `solamon-cloud` MQTT user. **Distinct from `DB_PASSWORD`.** The cloud's MQTT credentials and Postgres credentials are independent; conflating them was a bug in the first draft of this script.
   - `ADMIN_PASSWORD` — 16-char random for the seed admin user (printed once at the end)
10. Write `/opt/solamon/.env` (mode 600) with all secrets.
11. **Render templates** (heredocs in the script — could be split out post-MVP):
    - `/opt/solamon/docker-compose.yml` — the cloud stack
    - `/opt/solamon/caddy/Caddyfile` — TLS reverse proxy (per [`caddy-and-dns.md`](caddy-and-dns.md) §3)
    - `/opt/solamon/mosquitto/mosquitto.conf` — broker config (per [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) and [`caddy-and-dns.md`](caddy-and-dns.md) §6)
    - `/opt/solamon/mosquitto/passwords` — populated with the `solamon-cloud` user via a one-shot `mosquitto_passwd` invocation (see step 11.1 below). Per-site users are added later by the cloud's site-add procedure (§10).
    - `/opt/solamon/mosquitto/acls` — initial entries for `solamon-cloud` only; per-site entries appended at site-add time.
    - `/etc/cron.d/solamon-mosquitto-cert-reload` — daily `SIGHUP` to Mosquitto to pick up Caddy-renewed certs (per `caddy-and-dns.md §6.1`).

11.1. **Bootstrap the Mosquitto password file.** Mosquitto won't start without `password_file` populated (we set `allow_anonymous false`), and we can't `docker compose exec` into a container that hasn't started. Run a one-shot `mosquitto_passwd` against the host file before bringing the broker up:

    ```bash
    docker run --rm \
        -v /opt/solamon/mosquitto:/mosquitto/config \
        eclipse-mosquitto:2 \
        mosquitto_passwd -b -c /mosquitto/config/passwords \
            solamon-cloud "${MQTT_CLOUD_PASSWORD}"
    chown 1883:1883 /opt/solamon/mosquitto/passwords /opt/solamon/mosquitto/acls
    chmod 0640      /opt/solamon/mosquitto/passwords /opt/solamon/mosquitto/acls
    ```

    UID 1883 is the in-container `mosquitto` user; mode 0640 makes the file readable by that user when bind-mounted but not world-readable on the host.

12. Open the EC2's local firewall (`ufw`) for 80, 443, 8883.

### 3.7 Database (steps 13-15)

13. `docker compose up -d postgres` and wait for the health check to return `healthy` (Postgres + Timescale extension load takes ~20 s).
14. **Run the migration:** the cloud-app image (per [`../cloud/Dockerfile.md`](../cloud/Dockerfile.md) — to be authored as a tracked SOL-21 follow-on) ships with `psql` installed and the `migrations/` directory copied in at `/app/migrations/`. The script invokes:

    ```bash
    docker compose run --rm app \
        psql "host=postgres user=solamon password=${DB_PASSWORD} dbname=solamon" \
        -f /app/migrations/0001_initial.sql
    ```

    Until the cloud-app Dockerfile spec lands, the script SHOULD copy migrations into the postgres container instead and run via `docker compose exec postgres psql -f /migrations/...`. Either path requires that the migration file actually exists somewhere mounted into a container — that mount is part of the Dockerfile contract.

15. **Seed reference data:** `docker compose run --rm -e ADMIN_EMAIL=... -e ADMIN_PASSWORD=... app python -m solamon.seed_reference_data` (loads `architecture/logical_metrics.yaml` and `architecture/profiles/*.yaml` into the DB; creates the admin user with the generated password). Same Dockerfile dependency as step 14.

### 3.8 Application (step 16)

16. **Wait for Caddy's first cert.** Mosquitto's TLS cert/key live inside Caddy's data volume (per [`caddy-and-dns.md`](caddy-and-dns.md) §6); Caddy provisions the cert ~10-30 s after first start. Bring up Caddy first, poll for the cert files, **then** bring up the rest of the stack (so Mosquitto doesn't restart-loop on startup):

    ```bash
    docker compose up -d caddy
    # Poll the cert path inside the named volume
    for i in $(seq 1 24); do
        if docker run --rm -v solamon_caddy-data:/d alpine \
            test -f "/d/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}/${DOMAIN}.crt"; then
            ok "Caddy cert provisioned"
            break
        fi
        sleep 5
    done
    docker compose up -d                # mosquitto, app, web
    ```

    Then wait for `/api/v1/health` to return 200.

### 3.9 Verification (step 17)

17. Run end-to-end checks:
    - `curl https://${DOMAIN}/api/v1/health` → 200 with `{"status":"ok","db":"ok","mqtt":"ok"}`
    - `curl https://${DOMAIN}/api/v1/auth/login -d '{"email":"admin@solamon","password":"<generated>"}'` → 200 with a token
    - Caddy logs show no errors
    - Mosquitto logs show "started"
    - Postgres logs show "ready to accept connections"

If any check fails: print the failing component's logs and exit 2.

### 3.10 Final output (step 18)

18. Print the admin URL + admin password + a "what to do next" message:
    ```
    ✓ Cloud stack running.
      Web UI:    https://cloud.solamon.bloemhof.dev
      API:       https://cloud.solamon.bloemhof.dev/api/v1
      MQTT:      mqtts://cloud.solamon.bloemhof.dev:8883
      Admin:     admin@solamon  /  <password>

    Next steps:
      1. Save the admin password to your password manager (won't be shown again).
      2. Sign in to the web UI; verify your account.
      3. Use the cloud's site-add procedure to register the first site (or seed manually via the API).
      4. Run solamon-edge-install.sh on the Pi with the per-site bearer token from step 3.
    ```

## 4. Idempotency

Re-running the script on a partially-bootstrapped EC2:

- Postgres data volume already exists → migration `0001_initial.sql` is idempotent (every CREATE has IF NOT EXISTS).
- Seed script idempotent (uses `ON CONFLICT DO NOTHING`).
- Docker compose rolls forward without touching unchanged services.
- Generated secrets are written ONCE — if `.env` already has them, they're preserved (the script reads existing values rather than overwriting).
- Tailscale `up` with same key just re-ups.

For a clean re-install: `docker compose down -v && rm -rf /opt/solamon` first. **Backup before this if there's any production data.**

## 5. Backup integration

**Bucket pre-flight.** The script verifies `s3://${BACKUP_BUCKET}` (default `solamon-backup-prod`) exists with `aws s3api head-bucket`; if not, it exits with a hint to create it via `aws s3 mb s3://solamon-backup-prod --region af-south-1`. The bucket should have an S3 lifecycle policy deleting objects under `postgres/` after 30 days (configured manually per [`aws-account.md`](aws-account.md) §6.X).

**Daily backup cron.** The script installs `/etc/cron.d/solamon-pg-backup` running at 03:00 UTC:

```cron
0 3 * * * root /opt/solamon/pg-backup.sh >> /var/log/solamon-pg-backup.log 2>&1
```

Where `/opt/solamon/pg-backup.sh` is written by the bootstrap script:

```bash
#!/usr/bin/env bash
set -euo pipefail
DATE=$(date -u +%F)
DUMP=/tmp/solamon-${DATE}.dump
docker compose -f /opt/solamon/docker-compose.yml exec -T postgres \
    pg_dump -U solamon -Fc -d solamon > "${DUMP}"
aws s3 cp "${DUMP}" "s3://solamon-backup-prod/postgres/${DATE}.dump" --region af-south-1
rm -f "${DUMP}"
```

The `pg_dump` runs against the live Postgres via the existing container — no separate Postgres install on the host. `pg_dump -Fc` (custom format) is what `pg_restore` consumes during DR (see §11).

## 6. Logs

Every container's stdout is captured by Docker's logging driver. The script configures Docker daemon to use the `json-file` driver with `max-size=20m, max-file=5` per container. Logs land in `/var/lib/docker/containers/{id}/` — accessible via `docker logs <container>`.

For "send logs to CloudWatch" — post-MVP. Logs locally are fine at single-EC2 scale.

## 7. Update procedure

For an existing cloud being moved to a new image version:

```bash
ssh ubuntu@cloud-elastic-ip      # via Tailscale
sudo /opt/solamon/update.sh --cloud-image-tag v0.2.0
```

`update.sh` is a small sibling script that runs `aws ecr get-login-password ...`, pulls the new image, runs any new migrations (`docker compose exec postgres psql -f /migrations/0002_...sql`), restarts the app + web services. **Postgres + Mosquitto + Caddy are left untouched** — no need to bounce them on app version bumps.

## 8. Domain swap procedure

If we change the cloud's domain (e.g., from `cloud.solamon.bloemhof.dev` to `solamon.co.za`):

1. Add the new DNS A record pointing at the same elastic IP.
2. Update the Caddyfile (`/opt/solamon/caddy/Caddyfile`) — replace the old domain block with the new one. Optionally keep a redirect block for a transition period.
3. `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`
4. Caddy re-issues a Let's Encrypt cert for the new domain.
5. Old DNS entry can be removed after a grace period.

The Pi installs already point at the cloud's domain — they don't need updating until they're re-installed (rare).

## 9. Tear-down

When the project is wound down or the cloud is being moved to a new region/account:

1. `docker compose down -v` (the `-v` removes volumes — destroys data; back up first).
2. Terminate the EC2.
3. Release the elastic IP.
4. Empty + delete S3 backup bucket.
5. (Optional) Close the AWS account per [`aws-account.md`](aws-account.md) §7.

## 10. The "first site" procedure

After the cloud is up, before the Pi can be installed:

1. Sign in to the cloud web UI as `admin@solamon`.
2. (Post-MVP UI: site-add page.) For MVP: use the API directly to insert an `app.site` row with name, slug, timezone, MQTT username, MQTT password.
3. The cloud's site-add procedure runs the per-site Mosquitto registration (§10.1).
4. The same site row's `mqtt_password` is the bearer token passed to `solamon-edge-install.sh` for that site.

**MVP shortcut:** the seed script in step 15 of the bootstrap creates a single bench site with a generated password. The bootstrap output prints the bench's per-site bearer token alongside the admin password. The first Pi install uses these values directly.

### 10.1 Site-add: Mosquitto password + ACL update

When the cloud's site-add code path runs (whether via the seed script or the API endpoint that lands post-MVP), it MUST register the new site with Mosquitto. Concretely:

```bash
# 1. Add (or update) the per-site MQTT user.
docker exec solamon-mosquitto \
    mosquitto_passwd -b /mosquitto/config/passwords \
        "solamon-${SITE_SLUG}" "${SITE_MQTT_PASSWORD}"

# 2. Append the site's ACL block to /mosquitto/config/acls if not already present.
#    The cloud regenerates the file from app.site rows on every site-add — this
#    is idempotent and avoids drift between DB and broker.
docker exec solamon-mosquitto \
    sh -c "cat > /mosquitto/config/acls" <<EOF
user solamon-cloud
topic readwrite solamon/#

$(while read -r slug; do
    echo "user solamon-${slug}"
    echo "topic readwrite solamon/${slug}/#"
    echo
done < <(psql ... -t -A -c "SELECT slug FROM app.site WHERE is_active"))
EOF

# 3. SIGHUP Mosquitto so it re-reads both files.
docker kill -s HUP solamon-mosquitto
```

**Why SIGHUP works for both files in Mosquitto 2.x.** Mosquitto 2.0+ re-reads `password_file` and `acl_file` on SIGHUP (verified against the upstream changelog). Earlier 1.x versions only re-read ACLs — if we ever pin to 1.x, the password-add path would need a container restart instead. For MVP we're pinned to `eclipse-mosquitto:2`, so SIGHUP is correct.

**Implementation note for the cloud app.** The site-add API endpoint (post-MVP — for MVP this is done by the seed script during bootstrap) needs Docker socket access OR a small helper container that does the `mosquitto_passwd` + SIGHUP work. For MVP single-site, the bootstrap script calls these directly and the cloud app never touches Mosquitto config files.

## 11. Disaster recovery — restore from backup

If the EC2 is destroyed and we need to bring up a new one with the previous data:

```bash
# 1. Provision a fresh EC2 + DNS + run the bootstrap script with --restore-from:
sudo /opt/solamon/solamon-cloud-bootstrap.sh \
    --domain "cloud.solamon.bloemhof.dev" \
    --tailscale-auth-key "..." \
    --cloud-image-tag "v0.1.0" \
    --letsencrypt-email "..." \
    --restore-from "s3://solamon-backup-prod/postgres/2026-05-02.dump"
```

The `--restore-from` flag, when present, **skips the seed step (15)** but **NOT the migration replay**. The flow:

1. `aws s3 cp ${RESTORE_S3_URI} /tmp/restore.dump`.
2. `docker compose up -d postgres` and wait for healthy.
3. `docker compose exec postgres psql -U solamon -c "SELECT timescaledb_pre_restore();"` — required for Timescale (per [`../cloud/data-model.md`](../cloud/data-model.md) §8).
4. `docker compose exec postgres pg_restore -U solamon -d solamon /tmp/restore.dump`.
5. `docker compose exec postgres psql -U solamon -c "SELECT timescaledb_post_restore();"`.
6. **Replay any migrations newer than what the dump contained.** The dump preserves the `app.schema_migrations` table (per [`../cloud/migrations/0001_initial.sql`](../cloud/migrations/0001_initial.sql)). The script queries that table to determine the highest applied migration filename in the restored dump, then iterates over `migrations/*.sql` in lex order, applying any that aren't already in the table:

    ```bash
    APPLIED=$(docker compose exec -T postgres \
        psql -U solamon -d solamon -t -A -c \
        "SELECT filename FROM app.schema_migrations ORDER BY filename;")
    for migration in /app/migrations/[0-9]*.sql; do
        name=$(basename "${migration}")
        if ! grep -qx "${name}" <<< "${APPLIED}"; then
            echo "Applying migration ${name} (post-restore catch-up)"
            docker compose run --rm app psql "..." -f "${migration}"
        fi
    done
    ```

    Without this step, a dump captured at schema 0001 restored into a stack expecting 0002 would silently leave the schema lagging — an early MVP misfeature where the app then fails to start with cryptic "column does not exist" errors.

7. Resume normal bootstrap from step 16.

The bench rehearsal Day 11-12 polish includes **a restore drill** to verify this procedure works end-to-end, including the case where the dump is one migration behind current code.

## 12. Acceptance

- Fresh EC2 → `solamon-cloud-bootstrap.sh` → 30 minutes later, the cloud responds at `https://${DOMAIN}/api/v1/health` with `{"status":"ok",...}` over a valid Let's Encrypt cert.
- Admin can sign in with the printed credentials.
- A bench Pi run of `solamon-edge-install.sh` lands a heartbeat in the cloud within 90 s.
- The restore drill on Day 11-12 successfully recovers a previous day's data.
- Re-running the bootstrap script on the same EC2 is idempotent — no destructive operations.

## 13. Cross-references

- [`scripts/solamon-cloud-bootstrap.sh`](scripts/solamon-cloud-bootstrap.sh) — the actual implementation
- [`aws-account.md`](aws-account.md) §4.2 — `EC2InstanceRole` definition
- [`tailscale.md`](tailscale.md) §7 — `tag:cloud` auth key
- [`caddy-and-dns.md`](caddy-and-dns.md) §3 — Caddyfile template
- [`ecr-and-images.md`](ecr-and-images.md) §7 — ECR pull via instance profile
- [`../cloud/data-model.md`](../cloud/data-model.md) §8 — backup approach + Timescale pre/post-restore
- [`pi-install.md`](pi-install.md) — the operator's NEXT step after this one
