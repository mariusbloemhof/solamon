#!/usr/bin/env bash
# solamon-edge-install.sh — install the Solamon edge agent on a fresh Pi 5.
#
# Spec: docs/specs/infrastructure/pi-install.md
# Linear: SOL-21
#
# Run as root on a fresh Raspberry Pi OS Lite (64-bit) image:
#
#   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-edge-install.sh \
#     | sudo bash -s -- \
#         --site-slug "johansworkbench" \
#         --cloud-url "https://cloud.solamon.bloemhof.dev" \
#         --bearer-token "<per-site-secret>" \
#         --tailscale-auth-key "tskey-auth-..." \
#         --ecr-access-key-id "AKIA..." \
#         --ecr-secret-access-key "..."
#
# Idempotent — re-running on a partially-installed Pi continues from where it
# left off. For a clean re-install, manually `docker compose down -v &&
# rm -rf /etc/solamon /var/lib/solamon` first.

set -euo pipefail

# ───── defaults ───────────────────────────────────────────────────────────────
SITE_SLUG=""
CLOUD_URL=""
BEARER_TOKEN=""
TAILSCALE_AUTH_KEY=""
ECR_ACCESS_KEY_ID=""
ECR_SECRET_ACCESS_KEY=""
DEVICE_HOST="192.168.1.254"
DEVICE_UNIT_ID="1"
EDGE_IMAGE_TAG="latest"
ECR_REGION="af-south-1"
ECR_REGISTRY=""        # set after AWS_ACCOUNT_ID is discovered

STEP_NUM=1
TOTAL_STEPS=22

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

# ───── arg parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --site-slug)              SITE_SLUG="$2"; shift 2 ;;
        --cloud-url)              CLOUD_URL="$2"; shift 2 ;;
        --bearer-token)           BEARER_TOKEN="$2"; shift 2 ;;
        --tailscale-auth-key)     TAILSCALE_AUTH_KEY="$2"; shift 2 ;;
        --ecr-access-key-id)      ECR_ACCESS_KEY_ID="$2"; shift 2 ;;
        --ecr-secret-access-key)  ECR_SECRET_ACCESS_KEY="$2"; shift 2 ;;
        --device-host)            DEVICE_HOST="$2"; shift 2 ;;
        --device-unit-id)         DEVICE_UNIT_ID="$2"; shift 2 ;;
        --edge-image-tag)         EDGE_IMAGE_TAG="$2"; shift 2 ;;
        -h|--help)                usage ;;
        *)                        die "unknown argument: $1" ;;
    esac
done

require_arg SITE_SLUG
require_arg CLOUD_URL
require_arg BEARER_TOKEN
require_arg TAILSCALE_AUTH_KEY
require_arg ECR_ACCESS_KEY_ID
require_arg ECR_SECRET_ACCESS_KEY

# ───── 1-3: pre-flight ────────────────────────────────────────────────────────
log_step "Verifying root + hardware + OS"
[[ "$(id -u)" -eq 0 ]] || die "must run as root" 1
grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null || \
    die "expected Raspberry Pi 5; got $(cat /proc/device-tree/model 2>/dev/null || echo unknown)" 1
[[ "$(uname -m)" == "aarch64" ]] || die "expected aarch64; got $(uname -m)" 1
ok "Pi 5 + ARM64 confirmed"

log_step "Checking free disk"
free_gb=$(df -BG / | awk 'NR==2 {gsub("G","",$4); print $4}')
[[ "$free_gb" -ge 5 ]] || die "need 5 GB free on /; only ${free_gb}G available" 1
ok "${free_gb}G free on /"

# ───── 4: NTP sync ────────────────────────────────────────────────────────────
log_step "Verifying NTP sync"
for i in $(seq 1 24); do
    if [[ "$(timedatectl show -p NTPSynchronized --value)" == "yes" ]]; then
        ok "system clock NTP-synced"
        break
    fi
    [[ $i -eq 24 ]] && die "system clock not NTP-synced after 2 minutes" 1
    sleep 5
done

# ───── 5-6: docker ────────────────────────────────────────────────────────────
log_step "Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker pi 2>/dev/null || true
ok "Docker installed"

# ───── 7-9: tailscale ─────────────────────────────────────────────────────────
log_step "Installing Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
ok "Tailscale installed"

log_step "Joining tailnet"
tailscale up --ssh --auth-key="$TAILSCALE_AUTH_KEY" \
    --hostname="solamon-pi-${SITE_SLUG}" \
    --reset
sleep 5
tailscale status --json | jq -e '.Self.Online' >/dev/null || die "tailnet not online" 3
ok "tailnet joined as solamon-pi-${SITE_SLUG} ($(tailscale ip --4))"

# ───── 10-13: ECR auth ────────────────────────────────────────────────────────
log_step "Configuring AWS credentials"
mkdir -p /etc/solamon
chmod 700 /etc/solamon
cat > /etc/solamon/aws-credentials <<EOF
[solamon-pi]
aws_access_key_id = ${ECR_ACCESS_KEY_ID}
aws_secret_access_key = ${ECR_SECRET_ACCESS_KEY}
region = ${ECR_REGION}
EOF
chmod 600 /etc/solamon/aws-credentials
export AWS_SHARED_CREDENTIALS_FILE=/etc/solamon/aws-credentials
export AWS_PROFILE=solamon-pi
ok "AWS credentials at /etc/solamon/aws-credentials"

log_step "Installing AWS CLI"
if ! command -v aws >/dev/null 2>&1; then
    apt-get update && apt-get install -y awscli
fi
ok "AWS CLI installed"

log_step "Logging in to ECR"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${ECR_REGION}.amazonaws.com"
aws ecr get-login-password --region "$ECR_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
    || die "ECR login failed" 4
ok "logged in to ECR ${ECR_REGISTRY}"

# ───── 14-19: agent deploy ────────────────────────────────────────────────────
log_step "Creating solamon user + dirs"
id -u solamon >/dev/null 2>&1 || useradd -r -s /bin/false solamon
mkdir -p /etc/solamon /var/lib/solamon /opt/solamon
chown -R solamon:solamon /etc/solamon /var/lib/solamon
chmod 700 /etc/solamon /var/lib/solamon
ok "solamon user + /etc/solamon /var/lib/solamon /opt/solamon"

log_step "Writing /etc/solamon/bootstrap.yaml"
cat > /etc/solamon/bootstrap.yaml <<EOF
schema_version: "1.0"
site_slug: "${SITE_SLUG}"
cloud_url: "${CLOUD_URL}"
bearer_token: "${BEARER_TOKEN}"
device_host: "${DEVICE_HOST}"
device_unit_id: ${DEVICE_UNIT_ID}
log_level: INFO
EOF
chown solamon:solamon /etc/solamon/bootstrap.yaml
chmod 600 /etc/solamon/bootstrap.yaml
ok "bootstrap.yaml written"

log_step "Pulling edge agent image"
docker pull "${ECR_REGISTRY}/solamon-edge-agent:${EDGE_IMAGE_TAG}" || die "image pull failed" 4
ok "image pulled"

log_step "Writing /opt/solamon/docker-compose.yml"
cat > /opt/solamon/docker-compose.yml <<EOF
services:
  edge-agent:
    image: ${ECR_REGISTRY}/solamon-edge-agent:${EDGE_IMAGE_TAG}
    container_name: solamon-edge-agent
    restart: on-failure:5
    network_mode: host                      # so the agent can reach the local LAN's Modbus device
    volumes:
      - /etc/solamon:/etc/solamon:ro
      - /var/lib/solamon:/var/lib/solamon
    environment:
      - SOLAMON_CONFIG=/etc/solamon/bootstrap.yaml
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: "5"
EOF
ok "docker-compose.yml written"

log_step "Starting edge agent"
cd /opt/solamon
docker compose up -d
ok "container started"

# ───── 20: ECR refresh cron ───────────────────────────────────────────────────
log_step "Installing ECR auth refresh cron"
cat > /etc/cron.d/solamon-ecr-refresh <<EOF
# Refresh ECR docker login every 6 hours (token expires every 12 h)
0 */6 * * * root AWS_SHARED_CREDENTIALS_FILE=/etc/solamon/aws-credentials AWS_PROFILE=solamon-pi aws ecr get-login-password --region ${ECR_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} >> /var/log/solamon-ecr-refresh.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-ecr-refresh
ok "cron installed at /etc/cron.d/solamon-ecr-refresh"

# ───── 21-22: verify ──────────────────────────────────────────────────────────
log_step "Waiting for first heartbeat (up to 90 s)"
heartbeat_ok=false
for i in $(seq 1 18); do
    sleep 5
    if curl -fsS -m 10 -H "Authorization: Bearer ${BEARER_TOKEN}" \
            "${CLOUD_URL}/api/v1/sites/${SITE_SLUG}/health" \
            2>/dev/null | jq -e '.heartbeat_age_seconds < 90' >/dev/null 2>&1; then
        heartbeat_ok=true
        break
    fi
done

if ! $heartbeat_ok; then
    echo "✗ heartbeat not received within 90 s. Diagnostic info:"
    echo "--- agent logs (last 50 lines) ---"
    docker logs solamon-edge-agent --tail 50 || true
    echo "--- tailscale status ---"
    tailscale status || true
    echo "--- cloud /api/v1/health ---"
    curl -fsS "${CLOUD_URL}/api/v1/health" || true
    exit 2
fi

ok "first heartbeat received"

# ───── done ───────────────────────────────────────────────────────────────────
echo
echo "✓ Edge agent ready"
echo "  Pi tailnet IP:  $(tailscale ip --4)"
echo "  Site slug:     ${SITE_SLUG}"
echo "  Cloud:         ${CLOUD_URL}"
echo
echo "  Next: open the dashboard, navigate to /sites/${SITE_SLUG}, confirm the heartbeat panel is green."
