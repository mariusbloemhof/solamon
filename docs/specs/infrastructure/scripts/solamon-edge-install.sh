#!/usr/bin/env bash
# solamon-edge-install.sh — install the Solamon edge agent on a fresh Pi 5.
#
# Spec: docs/specs/infrastructure/pi-install.md
# Linear: SOL-21
#
# Recommended invocation (secrets stay out of argv / shell history):
#
#   sudo tee /tmp/install-config.yaml <<EOF
#   site_slug: johansworkbench
#   cloud_url: https://cloud.solamon.bloemhof.dev
#   bearer_token: <per-site secret>
#   tailscale_auth_key: tskey-auth-...
#   ecr_access_key_id: AKIA...
#   ecr_secret_access_key: ...
#   device_host: 192.168.20.10
#   EOF
#   sudo chmod 600 /tmp/install-config.yaml
#
#   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-edge-install.sh \
#     | sudo bash -s -- --config /tmp/install-config.yaml
#
# Legacy argv form (CI / scripted; secrets visible to ps and bash history):
#
#   sudo bash solamon-edge-install.sh \
#       --site-slug "..." --cloud-url "..." --bearer-token "..." \
#       --tailscale-auth-key "..." --ecr-access-key-id "..." --ecr-secret-access-key "..."
#
# Idempotent — re-running on a partially-installed Pi continues from where it
# left off. For a clean re-install, manually `docker compose down -v &&
# rm -rf /etc/solamon /var/lib/solamon` first.

set -euo pipefail

# ───── defaults ───────────────────────────────────────────────────────────────
CONFIG_FILE=""
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

# Shred the config file on exit (success OR failure) so the secrets don't
# linger on disk after the install window. A no-op if --config wasn't passed.
trap 'cleanup_config' EXIT
cleanup_config() {
    if [[ -n "${CONFIG_FILE:-}" && -f "$CONFIG_FILE" ]]; then
        shred -u "$CONFIG_FILE" 2>/dev/null || rm -f "$CONFIG_FILE"
    fi
}

# Parse a YAML config file (very simple: top-level scalar keys only).
load_config() {
    local file="$1"
    [[ -f "$file" ]] || die "config file not found: $file" 1
    [[ "$(stat -c %a "$file" 2>/dev/null || stat -f %Lp "$file")" == "600" ]] \
        || die "config file must be mode 600: $file" 1
    while IFS=':' read -r key value; do
        key=$(echo "$key" | tr -d '[:space:]')
        value=$(echo "$value" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        case "$key" in
            site_slug)              SITE_SLUG="$value" ;;
            cloud_url)              CLOUD_URL="$value" ;;
            bearer_token)           BEARER_TOKEN="$value" ;;
            tailscale_auth_key)     TAILSCALE_AUTH_KEY="$value" ;;
            ecr_access_key_id)      ECR_ACCESS_KEY_ID="$value" ;;
            ecr_secret_access_key)  ECR_SECRET_ACCESS_KEY="$value" ;;
            device_host)            DEVICE_HOST="$value" ;;
            device_unit_id)         DEVICE_UNIT_ID="$value" ;;
            edge_image_tag)         EDGE_IMAGE_TAG="$value" ;;
            "" | "#"*)              ;;  # blank line or comment
        esac
    done < "$file"
}

# ───── arg parsing ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)                 CONFIG_FILE="$2"; shift 2 ;;
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

[[ -n "$CONFIG_FILE" ]] && load_config "$CONFIG_FILE"

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

# ───── 3: NTP sync (5-min budget for marginal LTE first-boot) ─────────────────
log_step "Verifying NTP sync"
for i in $(seq 1 60); do
    if [[ "$(timedatectl show -p NTPSynchronized --value)" == "yes" ]]; then
        ok "system clock NTP-synced"
        break
    fi
    [[ $i -eq 60 ]] && die "system clock not NTP-synced after 5 minutes; check Pi network connectivity" 1
    sleep 5
done

# ───── 4-5: docker ────────────────────────────────────────────────────────────
log_step "Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker pi 2>/dev/null || true
ok "Docker installed"

# ───── 6-7: tailscale ─────────────────────────────────────────────────────────
log_step "Installing Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
ok "Tailscale installed"

log_step "Joining tailnet"
# No --reset: re-running with the same auth key is idempotent and preserves
# any --accept-routes / DNS overrides the operator may have set.
tailscale up --ssh --auth-key="$TAILSCALE_AUTH_KEY" \
    --hostname="solamon-pi-${SITE_SLUG}"
sleep 5
tailscale status --json | jq -e '.Self.Online' >/dev/null || die "tailnet not online" 3
TAILNET_IP=$(tailscale ip --4 2>/dev/null | head -1)
ok "tailnet joined as solamon-pi-${SITE_SLUG} (${TAILNET_IP:-<pending>})"

# ───── 8-10: AWS CLI v2 + ECR ────────────────────────────────────────────────
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

log_step "Installing AWS CLI v2"
# apt's `awscli` package is v1, EOL'd for new deployments. Install v2 from the
# official ARM64 zip.
if ! command -v aws >/dev/null 2>&1 || ! aws --version 2>&1 | grep -q "aws-cli/2"; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unzip
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp/
    /tmp/aws/install --update
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi
aws --version | grep -q "aws-cli/2" || die "AWS CLI v2 install failed" 5
ok "AWS CLI installed: $(aws --version)"

log_step "Logging in to ECR"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
[[ -n "$AWS_ACCOUNT_ID" ]] \
    || die "AWS account discovery failed (sts get-caller-identity returned empty); check ECR_ACCESS_KEY_ID/SECRET" 4
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${ECR_REGION}.amazonaws.com"
aws ecr get-login-password --region "$ECR_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
    || die "ECR login failed" 4
ok "logged in to ECR ${ECR_REGISTRY}"

# ───── 11: host firewall ──────────────────────────────────────────────────────
log_step "Configuring host firewall (ufw)"
if ! command -v ufw >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw
fi
# Default-deny incoming protects against the agent's `network_mode: host`
# accidentally exposing internal listeners on the LAN.
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh comment 'OpenSSH fallback (LAN)'
ufw allow in on tailscale0 comment 'Tailscale management'
ufw --force enable >/dev/null
ok "ufw active: SSH on LAN; everything else via tailnet"

# ───── 12-15: agent deploy ────────────────────────────────────────────────────
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

log_step "Writing /opt/solamon/docker-compose.yml + starting agent"
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
cd /opt/solamon
docker compose up -d
ok "container started"

# ───── 16: ECR refresh cron ───────────────────────────────────────────────────
log_step "Installing ECR auth refresh cron"
# PATH explicitly set: default cron PATH is /usr/bin:/bin, and AWS CLI v2
# installs to /usr/local/bin/aws.
cat > /etc/cron.d/solamon-ecr-refresh <<EOF
PATH=/usr/local/bin:/usr/bin:/bin
AWS_SHARED_CREDENTIALS_FILE=/etc/solamon/aws-credentials
AWS_PROFILE=solamon-pi
0 */6 * * * root aws ecr get-login-password --region ${ECR_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY} >> /var/log/solamon-ecr-refresh.log 2>&1
EOF
chmod 644 /etc/cron.d/solamon-ecr-refresh
ok "cron installed at /etc/cron.d/solamon-ecr-refresh"

# ───── 17-18: verify ──────────────────────────────────────────────────────────
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
echo "  Pi tailnet IP:  ${TAILNET_IP:-<pending; check 'tailscale ip --4'>}"
echo "  Site slug:      ${SITE_SLUG}"
echo "  Cloud:          ${CLOUD_URL}"
echo
echo "  Next: open the dashboard, navigate to /sites/${SITE_SLUG}, confirm the heartbeat panel is green."
