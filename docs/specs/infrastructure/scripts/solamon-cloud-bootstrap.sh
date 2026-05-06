#!/usr/bin/env bash
# solamon-cloud-bootstrap.sh — bootstrap the Solamon cloud stack on a fresh
# EC2 Ubuntu 24.04 LTS ARM64 instance in af-south-1.
#
# Spec: docs/specs/infrastructure/cloud-bootstrap.md
# Prereqs: docs/specs/infrastructure/aws-account-setup-checklist.md
# Linear: SOL-21
#
# Run as root on a fresh EC2 with the EC2InstanceRole IAM profile attached:
#
#   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-cloud-bootstrap.sh \
#     | sudo bash -s -- \
#         --domain "cloud.solamon.bloemhof.dev" \
#         --tailscale-auth-key "tskey-auth-..." \
#         --cloud-image-tag "v0.1.0" \
#         --letsencrypt-email "admin@bloemhof.dev"
#
# Idempotent — re-running on a partially-bootstrapped EC2 continues from where
# it left off. For a clean re-install, manually `docker compose down -v &&
# rm -rf /opt/solamon` first (BACK UP DATA FIRST).

set -euo pipefail

# ───── defaults ───────────────────────────────────────────────────────────────
DOMAIN=""
TAILSCALE_AUTH_KEY=""
CLOUD_IMAGE_TAG=""
LETSENCRYPT_EMAIL=""
ADMIN_EMAIL=""
DB_PASSWORD=""
RESTORE_FROM=""
ECR_REGION="af-south-1"
BACKUP_BUCKET="solamon-backup-prod"

STEP_NUM=1
TOTAL_STEPS=20

# ───── helpers ────────────────────────────────────────────────────────────────
log_step() {
    echo
    echo "[$STEP_NUM/$TOTAL_STEPS] $1..."
    STEP_NUM=$((STEP_NUM + 1))
}
ok() { echo "✓ $1"; }
die() {
    local code="${2:-1}"
    echo "✗ $1" >&2
    exit "$code"
}
usage() {
    grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
    exit 0
}
require_arg() {
    [[ -n "${!1:-}" ]] || die "missing required argument: --${1//_/-}"
}
random_secret() {
    head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c "${1:-24}"
}

# ───── arg parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)             DOMAIN="$2"; shift 2 ;;
        --tailscale-auth-key) TAILSCALE_AUTH_KEY="$2"; shift 2 ;;
        --cloud-image-tag)    CLOUD_IMAGE_TAG="$2"; shift 2 ;;
        --letsencrypt-email)  LETSENCRYPT_EMAIL="$2"; shift 2 ;;
        --admin-email)        ADMIN_EMAIL="$2"; shift 2 ;;
        --db-password)        DB_PASSWORD="$2"; shift 2 ;;
        --restore-from)       RESTORE_FROM="$2"; shift 2 ;;
        -h|--help)            usage ;;
        *)                    die "unknown argument: $1" ;;
    esac
done

require_arg DOMAIN
require_arg TAILSCALE_AUTH_KEY
require_arg CLOUD_IMAGE_TAG
require_arg LETSENCRYPT_EMAIL

# Default admin email to admin@${DOMAIN} so it has a real TLD (NextAuth's
# email validator rejects bare "admin@solamon"). Can still be overridden
# via --admin-email.
[[ -z "$ADMIN_EMAIL" ]] && ADMIN_EMAIL="admin@${DOMAIN}"

# ───── 1-3: pre-flight ────────────────────────────────────────────────────────
log_step "Verifying root + OS + IMDSv2"
[[ "$(id -u)" -eq 0 ]] || die "must run as root" 1
grep -q "Ubuntu 24.04" /etc/os-release || die "expected Ubuntu 24.04 LTS" 1
[[ "$(uname -m)" == "aarch64" ]] || die "expected aarch64" 1
IMDS_TOKEN=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null) \
    || die "EC2 IMDSv2 unreachable; is this an EC2 instance?" 1
AWS_ACCOUNT_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
    "http://169.254.169.254/latest/dynamic/instance-identity/document" \
    | jq -r .accountId)
[[ -n "$AWS_ACCOUNT_ID" && "$AWS_ACCOUNT_ID" != "null" ]] \
    || die "AWS account ID discovery failed (IMDS returned empty)" 1
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${ECR_REGION}.amazonaws.com"
ok "Ubuntu 24.04 ARM64; AWS account ${AWS_ACCOUNT_ID}"

# ───── 4: system packages + AWS CLI v2 ────────────────────────────────────────
log_step "Installing system packages + AWS CLI v2"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker.io docker-compose-plugin ca-certificates curl jq ufw cron unzip dnsutils
# AWS CLI v2 (the apt awscli package is v1, EOL'd for new deployments).
if ! command -v aws >/dev/null 2>&1 || ! aws --version 2>&1 | grep -q "aws-cli/2"; then
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp/
    /tmp/aws/install --update
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi
aws --version | grep -q "aws-cli/2" || die "AWS CLI v2 install failed" 5
ok "packages installed; aws=$(aws --version)"

# ───── 5: tailscale ───────────────────────────────────────────────────────────
log_step "Installing Tailscale + joining tailnet"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
# No --reset: re-running with the same auth key is idempotent and preserves
# any --accept-routes / DNS overrides the operator may have set.
tailscale up --ssh --auth-key="$TAILSCALE_AUTH_KEY" \
    --hostname="solamon-cloud-prod"
sleep 5
tailscale status --json | jq -e '.Self.Online' >/dev/null \
    || die "tailnet not online" 3
TAILNET_IP=$(tailscale ip --4 2>/dev/null | head -1)
ok "tailnet joined (${TAILNET_IP:-<pending>})"

# ───── 6: ECR login + pre-flight ─────────────────────────────────────────────
log_step "Verifying EC2InstanceRole + logging in to ECR"
# This is the canary for "EC2InstanceRole is attached + has ECR permissions".
# Failure here almost always means the operator skipped the AWS-account
# checklist's instance-profile attachment.
aws sts get-caller-identity >/dev/null \
    || die "EC2 instance profile missing or has no AWS permissions; see aws-account-setup-checklist.md §C/G" 4
aws ecr get-login-password --region "$ECR_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
    || die "ECR login failed (check EC2InstanceRole permissions)" 4

# Cron for ECR re-login (PATH explicitly set; default cron PATH is /usr/bin:/bin).
cat > /etc/cron.d/solamon-ecr-refresh <<EOF
PATH=/usr/local/bin:/usr/bin:/bin
0 */6 * * * root aws ecr get-login-password --region ${ECR_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} >> /var/log/solamon-ecr-refresh.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-ecr-refresh
ok "logged in to ${ECR_REGISTRY}; refresh cron installed"

# ───── 7: backup bucket pre-flight ────────────────────────────────────────────
log_step "Verifying backup bucket s3://${BACKUP_BUCKET}"
if ! aws s3api head-bucket --bucket "${BACKUP_BUCKET}" 2>/dev/null; then
    die "backup bucket s3://${BACKUP_BUCKET} does not exist or is inaccessible.
Create with:  aws s3 mb s3://${BACKUP_BUCKET} --region ${ECR_REGION}
Then re-run this script. (See aws-account-setup-checklist.md §E.)" 4
fi
ok "backup bucket reachable"

# ───── 8: pull images ─────────────────────────────────────────────────────────
log_step "Pulling images"
docker pull "${ECR_REGISTRY}/solamon-cloud-app:${CLOUD_IMAGE_TAG}" || die "cloud-app image pull failed" 4
docker pull timescale/timescaledb:2.26.4-pg16
docker pull eclipse-mosquitto:2
docker pull caddy:2
ok "images pulled"

# ───── 9: directories ────────────────────────────────────────────────────────
log_step "Creating /opt/solamon tree"
mkdir -p /opt/solamon/{caddy,mosquitto,postgres-data}
chmod 700 /opt/solamon
ok "directories created"

# ───── 10: secrets ────────────────────────────────────────────────────────────
log_step "Generating secrets"
ENV_FILE=/opt/solamon/.env
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    ok "loaded existing secrets from .env (idempotent re-run)"
else
    JWT_SECRET=$(random_secret 32)
    NEXTAUTH_SECRET=$(random_secret 32)
    [[ -z "$DB_PASSWORD" ]] && DB_PASSWORD=$(random_secret 24)
    MQTT_CLOUD_PASSWORD=$(random_secret 24)
    ADMIN_PASSWORD=$(random_secret 16)
    cat > "$ENV_FILE" <<EOF
JWT_SECRET=${JWT_SECRET}
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
DB_PASSWORD=${DB_PASSWORD}
MQTT_CLOUD_PASSWORD=${MQTT_CLOUD_PASSWORD}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
DOMAIN=${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
ECR_REGISTRY=${ECR_REGISTRY}
CLOUD_IMAGE_TAG=${CLOUD_IMAGE_TAG}
EOF
    chmod 600 "$ENV_FILE"
    ok "secrets generated and stored in .env (mode 600)"
fi

# ───── 11: render config templates ────────────────────────────────────────────
log_step "Writing Caddyfile"
cat > /opt/solamon/caddy/Caddyfile <<EOF
{
    email ${LETSENCRYPT_EMAIL}
}

${DOMAIN} {
    encode zstd gzip

    reverse_proxy /api/v1/ws/* app:8000 {
        header_up Upgrade {http.request.header.Upgrade}
        header_up Connection {http.request.header.Connection}
    }
    reverse_proxy /api/* app:8000
    reverse_proxy /* web:3000

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    log {
        output stdout
        format json {
            # Redact bearer tokens that travel in Sec-WebSocket-Protocol on /ws/* paths.
            # Without this, JWTs land in /var/log/caddy access logs.
            request>headers>Sec-Websocket-Protocol delete
            request>headers>Authorization delete
        }
    }
}
EOF
ok "Caddyfile written"

log_step "Writing Mosquitto config + bootstrapping password file"
# mosquitto.conf points at Caddy's exact cert paths (see caddy-and-dns.md §6).
# No cafile — we don't do mTLS in MVP; auth is username/password.
cat > /opt/solamon/mosquitto/mosquitto.conf <<EOF
listener 8883 0.0.0.0
protocol mqtt
certfile /caddy-data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}/${DOMAIN}.crt
keyfile  /caddy-data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}/${DOMAIN}.key
allow_anonymous false
password_file /mosquitto/config/passwords
acl_file /mosquitto/config/acls
log_dest stdout
log_type all
persistence true
persistence_location /mosquitto/data/
EOF

# Bootstrap the password file BEFORE starting Mosquitto. Otherwise the broker
# refuses to start (allow_anonymous=false + empty password_file). One-shot
# mosquitto_passwd in a throwaway container does the bcrypt hashing.
docker run --rm \
    -v /opt/solamon/mosquitto:/mosquitto/config \
    eclipse-mosquitto:2 \
    mosquitto_passwd -b -c /mosquitto/config/passwords \
        solamon-cloud "${MQTT_CLOUD_PASSWORD}"

# Initial ACLs: just the cloud user. Per-site users get appended at site-add time
# (see cloud-bootstrap.md §10.1).
cat > /opt/solamon/mosquitto/acls <<'EOF'
user solamon-cloud
topic readwrite solamon/#
EOF

# Owner UID 1883 = mosquitto user inside eclipse-mosquitto:2.
# Mode 0640 = readable by owner+group, not world-readable on the host.
chown 1883:1883 /opt/solamon/mosquitto/passwords /opt/solamon/mosquitto/acls
chmod 0640      /opt/solamon/mosquitto/passwords /opt/solamon/mosquitto/acls

# Daily SIGHUP cron so Mosquitto picks up Caddy-renewed certs (and any
# password/ACL changes from site-adds).
cat > /etc/cron.d/solamon-mosquitto-reload <<'EOF'
PATH=/usr/local/bin:/usr/bin:/bin
30 3 * * * root docker kill -s HUP solamon-mosquitto >> /var/log/solamon-mosquitto-reload.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-mosquitto-reload
ok "Mosquitto config + passwords + acls + reload cron written"

log_step "Writing docker-compose.yml"
cat > /opt/solamon/docker-compose.yml <<'EOF'
services:
  postgres:
    image: timescale/timescaledb:2.26.4-pg16
    container_name: solamon-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: solamon
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: solamon
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U solamon"]
      interval: 5s
      timeout: 3s
      retries: 20

  caddy:
    image: caddy:2
    container_name: solamon-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: solamon-mosquitto
    restart: unless-stopped
    ports:
      - "8883:8883"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwords:/mosquitto/config/passwords
      - ./mosquitto/acls:/mosquitto/config/acls
      - caddy-data:/caddy-data:ro     # SHARED: read Caddy's certs from the same named volume
      - mosquitto-data:/mosquitto/data
    depends_on:
      caddy:
        condition: service_started

  app:
    image: ${ECR_REGISTRY}/solamon-cloud-app:${CLOUD_IMAGE_TAG}
    container_name: solamon-app
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql+asyncpg://solamon:${DB_PASSWORD}@postgres:5432/solamon
      - JWT_SECRET=${JWT_SECRET}
      - MQTT_HOST=mosquitto
      - MQTT_PORT=8883
      - MQTT_USERNAME=solamon-cloud
      - MQTT_PASSWORD=${MQTT_CLOUD_PASSWORD}
      - DOMAIN=${DOMAIN}
    depends_on:
      postgres:
        condition: service_healthy

  web:
    image: ${ECR_REGISTRY}/solamon-cloud-app:${CLOUD_IMAGE_TAG}
    container_name: solamon-web
    restart: unless-stopped
    command: ["node", "/app/web/server.js"]
    environment:
      - NEXTAUTH_URL=https://${DOMAIN}
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
      - API_BASE_URL=http://app:8000
    depends_on:
      app:
        condition: service_started

volumes:
  caddy-data:
  caddy-config:
  mosquitto-data:
EOF
ok "docker-compose.yml written"

# ───── 12: firewall ───────────────────────────────────────────────────────────
log_step "Configuring host firewall"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp comment 'Caddy HTTP (LE challenge + redirect)'
ufw allow 443/tcp comment 'Caddy HTTPS'
ufw allow 8883/tcp comment 'Mosquitto MQTT TLS'
ufw allow in on tailscale0 comment 'Tailscale management'
ufw --force enable
ok "ufw active: 80, 443, 8883 public; SSH via tailnet only"

# ───── 13: DNS sanity check ──────────────────────────────────────────────────
log_step "Verifying DNS for ${DOMAIN}"
EXPECTED_IP=$(curl -fsS https://api.ipify.org 2>/dev/null || curl -fsS https://checkip.amazonaws.com 2>/dev/null | tr -d '\n')
for i in $(seq 1 12); do
    RESOLVED=$(dig +short A "${DOMAIN}" @8.8.8.8 | head -1)
    if [[ -n "$RESOLVED" && "$RESOLVED" == "$EXPECTED_IP" ]]; then
        ok "${DOMAIN} → ${RESOLVED}"
        break
    fi
    echo "  DNS not yet propagated (got '${RESOLVED:-empty}', expected ${EXPECTED_IP}); waiting 10 s..."
    sleep 10
    [[ $i -eq 12 ]] && die "DNS for ${DOMAIN} did not resolve to ${EXPECTED_IP} within 2 minutes.
Check: aws-account-setup-checklist.md §H — A record + propagation." 1
done

# ───── 14-15: Postgres + caddy + cert wait ───────────────────────────────────
log_step "Starting Postgres + Caddy"
cd /opt/solamon
docker compose up -d postgres caddy
for i in $(seq 1 24); do
    if docker compose exec -T postgres pg_isready -U solamon -q; then
        ok "Postgres healthy"
        break
    fi
    sleep 5
    [[ $i -eq 24 ]] && die "Postgres health check failed after 2 minutes" 2
done

log_step "Waiting for Caddy's first Let's Encrypt cert"
# Caddy provisions the cert ~10-30 s after starting. Mosquitto needs the cert
# files to exist before its container starts (otherwise restart-loop on bench Day 1).
CERT_PATH="/caddy-data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}/${DOMAIN}.crt"
for i in $(seq 1 36); do
    if docker run --rm -v solamon_caddy-data:/caddy-data alpine \
            test -f "${CERT_PATH}" 2>/dev/null; then
        ok "Caddy cert provisioned"
        break
    fi
    sleep 5
    [[ $i -eq 36 ]] && {
        echo "✗ Caddy did not provision a cert within 3 minutes. Logs:"
        docker compose logs --tail 50 caddy || true
        exit 2
    }
done

# ───── 16-17: migration + seed ────────────────────────────────────────────────
if [[ -n "$RESTORE_FROM" ]]; then
    log_step "Restoring from ${RESTORE_FROM} + replaying migrations"
    aws s3 cp "$RESTORE_FROM" /tmp/restore.dump
    docker compose exec -T postgres psql -U solamon -d solamon -c "SELECT timescaledb_pre_restore();"
    docker compose exec -T postgres pg_restore -U solamon -d solamon /tmp/restore.dump || true
    docker compose exec -T postgres psql -U solamon -d solamon -c "SELECT timescaledb_post_restore();"
    rm /tmp/restore.dump
    ok "dump restored; checking for missed migrations"

    # Replay any migrations newer than what was in the dump. The dump preserves
    # app.schema_migrations; query it to see what's already applied.
    APPLIED=$(docker compose exec -T postgres \
        psql -U solamon -d solamon -t -A -c \
        "SELECT filename FROM app.schema_migrations ORDER BY filename;" 2>/dev/null || echo "")
    APPLIED_COUNT=0
    for migration in /tmp/migrations/*.sql; do
        [[ -e "$migration" ]] || break  # no migrations dir yet on a fresh restore? skip.
        name=$(basename "$migration")
        if ! grep -qx "${name}" <<< "${APPLIED}"; then
            echo "  Applying ${name} (post-restore catch-up)"
            docker compose run --rm app psql \
                "host=postgres user=solamon password=${DB_PASSWORD} dbname=solamon" \
                -f "/app/migrations/${name}" \
                || die "post-restore migration ${name} failed" 6
            APPLIED_COUNT=$((APPLIED_COUNT + 1))
        fi
    done
    ok "restore complete (${APPLIED_COUNT} catch-up migrations applied)"
    STEP_NUM=$((STEP_NUM + 1))   # skip seed step counter
else
    log_step "Running migration 0001_initial.sql"
    # The cloud-app image (per docs/specs/cloud/Dockerfile.md — to be authored
    # as a SOL-21 follow-on) is expected to ship with psql + /app/migrations/.
    docker compose run --rm app \
        psql "host=postgres user=solamon password=${DB_PASSWORD} dbname=solamon" \
        -f /app/migrations/0001_initial.sql
    ok "migration applied"

    log_step "Seeding reference data + admin user"
    docker compose run --rm \
        -e ADMIN_EMAIL="$ADMIN_EMAIL" \
        -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        app python -m solamon.seed_reference_data
    ok "catalog + profiles + admin seeded"
fi

# ───── 18: start everything else ──────────────────────────────────────────────
log_step "Starting full stack"
docker compose up -d
ok "all services starting"

# ───── 19: pg_dump backup cron ───────────────────────────────────────────────
log_step "Installing pg_dump backup cron (daily 03:00 UTC → s3://${BACKUP_BUCKET}/postgres/)"
cat > /opt/solamon/pg-backup.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
DATE=\$(date -u +%F)
DUMP=/tmp/solamon-\${DATE}.dump
docker compose -f /opt/solamon/docker-compose.yml exec -T postgres \\
    pg_dump -U solamon -Fc -d solamon > "\${DUMP}"
aws s3 cp "\${DUMP}" "s3://${BACKUP_BUCKET}/postgres/\${DATE}.dump" --region ${ECR_REGION}
rm -f "\${DUMP}"
EOF
chmod 0755 /opt/solamon/pg-backup.sh

cat > /etc/cron.d/solamon-pg-backup <<EOF
PATH=/usr/local/bin:/usr/bin:/bin
0 3 * * * root /opt/solamon/pg-backup.sh >> /var/log/solamon-pg-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-pg-backup
ok "backup cron installed at /etc/cron.d/solamon-pg-backup"

# ───── 20: verify ─────────────────────────────────────────────────────────────
log_step "Waiting for /api/v1/health (up to 3 minutes)"
for i in $(seq 1 36); do
    if curl -fsS -m 10 "https://${DOMAIN}/api/v1/health" 2>/dev/null \
        | jq -e '.status == "ok" and .db == "ok" and .mqtt == "ok"' >/dev/null 2>&1; then
        ok "/api/v1/health is green"
        break
    fi
    sleep 5
    [[ $i -eq 36 ]] && {
        echo "✗ /api/v1/health did not become green within 3 minutes."
        echo "--- caddy logs ---";     docker compose logs --tail 50 caddy     || true
        echo "--- mosquitto logs ---"; docker compose logs --tail 50 mosquitto || true
        echo "--- app logs ---";       docker compose logs --tail 50 app       || true
        exit 2
    }
done

# ───── done ───────────────────────────────────────────────────────────────────
echo
echo "✓ Cloud stack running"
echo "  Web UI:    https://${DOMAIN}"
echo "  API:       https://${DOMAIN}/api/v1"
echo "  MQTT:      mqtts://${DOMAIN}:8883"
echo
if [[ -z "$RESTORE_FROM" ]]; then
    echo "  Admin:     ${ADMIN_EMAIL}  /  ${ADMIN_PASSWORD}"
    echo
    echo "  ⚠ The admin password will not be shown again. Save it to your password manager NOW."
fi
echo
echo "  Next steps:"
echo "    1. Sign in to the web UI; verify your account."
echo "    2. Use the cloud's site-add procedure to register the first site (or seed manually via the API)."
echo "    3. Run solamon-edge-install.sh on the Pi with the per-site bearer token."
