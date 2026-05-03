#!/usr/bin/env bash
# solamon-cloud-bootstrap.sh — bootstrap the Solamon cloud stack on a fresh
# EC2 Ubuntu 24.04 LTS ARM64 instance in af-south-1.
#
# Spec: docs/specs/infrastructure/cloud-bootstrap.md
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
ADMIN_EMAIL="admin@solamon"
DB_PASSWORD=""
RESTORE_FROM=""
ECR_REGION="af-south-1"
BACKUP_BUCKET="solamon-backup-prod"

STEP_NUM=1
TOTAL_STEPS=18

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
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${ECR_REGION}.amazonaws.com"
ok "Ubuntu 24.04 ARM64; AWS account ${AWS_ACCOUNT_ID}"

# ───── 4: system packages ─────────────────────────────────────────────────────
log_step "Installing system packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker.io docker-compose-plugin awscli ca-certificates curl jq ufw cron
ok "packages installed"

# ───── 5: tailscale ───────────────────────────────────────────────────────────
log_step "Installing Tailscale + joining tailnet"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
tailscale up --ssh --auth-key="$TAILSCALE_AUTH_KEY" \
    --hostname="solamon-cloud-prod" \
    --reset
sleep 5
tailscale status --json | jq -e '.Self.Online' >/dev/null \
    || die "tailnet not online" 3
ok "tailnet joined ($(tailscale ip --4))"

# ───── 6: ECR login ───────────────────────────────────────────────────────────
log_step "Logging in to ECR (via instance profile)"
aws ecr get-login-password --region "$ECR_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
    || die "ECR login failed (check EC2InstanceRole permissions)" 4
ok "logged in to ${ECR_REGISTRY}"

# Cron for ECR re-login
cat > /etc/cron.d/solamon-ecr-refresh <<EOF
0 */6 * * * root aws ecr get-login-password --region ${ECR_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} >> /var/log/solamon-ecr-refresh.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-ecr-refresh

# ───── 7: pull images ─────────────────────────────────────────────────────────
log_step "Pulling images"
docker pull "${ECR_REGISTRY}/solamon-cloud-app:${CLOUD_IMAGE_TAG}" || die "cloud-app image pull failed" 4
docker pull timescale/timescaledb:2.14-pg16
docker pull eclipse-mosquitto:2
docker pull caddy:2
ok "images pulled"

# ───── 8: directories ─────────────────────────────────────────────────────────
log_step "Creating /opt/solamon tree"
mkdir -p /opt/solamon/{caddy,mosquitto,postgres-data}
chmod 700 /opt/solamon
ok "directories created"

# ───── 9-10: secrets ──────────────────────────────────────────────────────────
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
    ADMIN_PASSWORD=$(random_secret 16)
    cat > "$ENV_FILE" <<EOF
JWT_SECRET=${JWT_SECRET}
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
DB_PASSWORD=${DB_PASSWORD}
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
        format json
    }
}
EOF
ok "Caddyfile written"

log_step "Writing Mosquitto config"
cat > /opt/solamon/mosquitto/mosquitto.conf <<EOF
listener 8883 0.0.0.0
protocol mqtt
cafile /mosquitto/certs/chain.pem
certfile /mosquitto/certs/cert.pem
keyfile /mosquitto/certs/privkey.pem
allow_anonymous false
password_file /mosquitto/config/passwords
acl_file /mosquitto/config/acls
log_dest stdout
log_type all
persistence true
persistence_location /mosquitto/data/
EOF
touch /opt/solamon/mosquitto/passwords /opt/solamon/mosquitto/acls
chmod 600 /opt/solamon/mosquitto/passwords
ok "Mosquitto config written (passwords + acls populated when first site is added)"

log_step "Writing docker-compose.yml"
cat > /opt/solamon/docker-compose.yml <<'EOF'
services:
  postgres:
    image: timescale/timescaledb:2.14-pg16
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

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: solamon-mosquitto
    restart: unless-stopped
    ports:
      - "8883:8883"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwords:/mosquitto/config/passwords:ro
      - ./mosquitto/acls:/mosquitto/config/acls:ro
      - ./caddy/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}:/mosquitto/certs:ro
      - mosquitto-data:/mosquitto/data
    depends_on:
      caddy:
        condition: service_started

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
      - MQTT_PASSWORD=${DB_PASSWORD}
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

# ───── 13-15: database ────────────────────────────────────────────────────────
log_step "Starting Postgres"
cd /opt/solamon
docker compose up -d postgres
for i in $(seq 1 24); do
    if docker compose exec -T postgres pg_isready -U solamon -q; then
        ok "Postgres healthy"
        break
    fi
    sleep 5
    [[ $i -eq 24 ]] && die "Postgres health check failed after 2 minutes" 2
done

if [[ -n "$RESTORE_FROM" ]]; then
    log_step "Restoring from ${RESTORE_FROM}"
    aws s3 cp "$RESTORE_FROM" /tmp/restore.dump
    docker compose exec -T postgres psql -U solamon -c "SELECT timescaledb_pre_restore();"
    docker compose exec -T postgres pg_restore -U solamon -d solamon /tmp/restore.dump || true
    docker compose exec -T postgres psql -U solamon -c "SELECT timescaledb_post_restore();"
    rm /tmp/restore.dump
    ok "restore complete (skipping migration + seed)"
    STEP_NUM=$((STEP_NUM + 1))   # skip seed step counter
else
    log_step "Running migration 0001_initial.sql"
    # Migration is mounted in the cloud-app image at /app/migrations/.
    # We run it via the app container which has psql + the file:
    docker compose run --rm app psql "$(docker compose exec -T postgres bash -c 'echo "host=postgres user=solamon password=$POSTGRES_PASSWORD dbname=solamon"')" -f /app/migrations/0001_initial.sql
    ok "migration applied"

    log_step "Seeding reference data + admin user"
    docker compose run --rm \
        -e ADMIN_EMAIL="$ADMIN_EMAIL" \
        -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        app python -m solamon.seed_reference_data
    ok "catalog + profiles + admin seeded"
fi

# ───── 16: start everything else ──────────────────────────────────────────────
log_step "Starting full stack"
docker compose up -d
ok "all services starting"

# ───── 17: verify ─────────────────────────────────────────────────────────────
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
        echo "--- caddy logs ---"; docker compose logs --tail 50 caddy || true
        echo "--- app logs ---";   docker compose logs --tail 50 app   || true
        exit 2
    }
done

# ───── 18: done ───────────────────────────────────────────────────────────────
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
