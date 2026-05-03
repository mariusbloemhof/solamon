# Infrastructure — Pi install

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)
**Machine artifact:** [`scripts/solamon-edge-install.sh`](scripts/solamon-edge-install.sh)

The contract for `solamon-edge-install.sh` — the script that takes a fresh Raspberry Pi 5 with Pi OS Lite (64-bit) and turns it into a Solamon edge node.

---

## 1. Operator runbook (high-level)

This is the procedure a human (Marius, Johan, or a future contractor) follows at a site:

1. **Hardware:** Pi 5 (8 GB RAM recommended), 32+ GB SD card, USB-C PSU, USB LTE modem (or Ethernet to local router with internet), small Ethernet switch, Ethernet cable.
2. **Image the SD card** with **Raspberry Pi OS Lite (64-bit)** using Raspberry Pi Imager.
   - In Imager, click the gear icon: set hostname (`solamon-pi-{slug}`), enable SSH, set the `pi` user password, configure WiFi (if Pi will WiFi temporarily during install), set locale + timezone (UTC for the project — Pi clock stays UTC).
3. **Boot the Pi** with the SD card. Connect to the LAN where the Acuvim is reachable.
4. **From your laptop on the same LAN**: `ssh pi@solamon-pi-{slug}.local` (mDNS).
5. **Run the install script:**
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mariusbloemhof/solamon/master/docs/specs/infrastructure/scripts/solamon-edge-install.sh | sudo bash -s -- \
       --site-slug "johansworkbench" \
       --cloud-url "https://cloud.solamon.bloemhof.dev" \
       --bearer-token "<the per-site secret from cloud admin>" \
       --tailscale-auth-key "tskey-auth-..." \
       --ecr-access-key-id "AKIA..." \
       --ecr-secret-access-key "..."
   ```
   *(All argument values come from the cloud admin's prep-this-site procedure — see [`cloud-bootstrap.md`](cloud-bootstrap.md) §10.)*

6. **Wait for the script to finish** (~10 minutes). It prints status as it goes; final line is `✓ Edge agent ready` or an error.

7. **Verify on the cloud**: open the dashboard, navigate to the site, confirm the heartbeat appears within 90 s.

8. **Power-cycle test:** unplug the Pi for 30 s, replug. Heartbeat should resume within 2 minutes (NTP sync + Docker startup + agent connect). Done.

## 2. Script inputs

All required, no interactive prompts (the script must be runnable in CI / automation):

| Argument | Type | Source |
|----------|------|--------|
| `--site-slug` | string (slug-format) | The cloud admin's site record |
| `--cloud-url` | URL (https://) | The cloud's public domain |
| `--bearer-token` | secret string | The cloud's per-site secret (same value as MQTT password) |
| `--tailscale-auth-key` | `tskey-auth-...` | Tailscale admin console — pre-authorised, tagged `tag:pi`, reusable |
| `--ecr-access-key-id` | string | `pi-ecr-puller` IAM user (per [`ecr-and-images.md`](ecr-and-images.md) §6.1) |
| `--ecr-secret-access-key` | secret string | Same |
| `--device-host` | IP / hostname | (Optional) Acuvim IP on the site LAN, defaults to `192.168.1.254` (Acuvim factory default). Override per site. |
| `--device-unit-id` | int | (Optional) Default 1. |
| `--edge-image-tag` | string | (Optional) ECR image tag to pin (e.g., `v0.1.0`). Default: `latest` only on first install; subsequent updates pass the explicit tag. |

`--help` prints the usage. Missing required arg → exit 1 with a clear message.

## 3. Steps

The script is `set -euo pipefail`. Every step logs `[1/N] Doing X...` and `✓` on success. Most steps are idempotent — re-running on a partially-installed Pi continues from where it left off.

### 3.1 Pre-flight checks (steps 1-3)

1. **Verify root.** `[ "$(id -u)" = "0" ]` or exit 1.
2. **Verify Pi 5 hardware.** `cat /proc/device-tree/model` should contain "Raspberry Pi 5". Other Pi models likely work but aren't supported.
3. **Verify Pi OS Lite 64-bit.** `uname -m` returns `aarch64`; `/etc/os-release` ID is `debian` or `raspbian`. Other distributions can be made to work but no warranty.
4. **Verify free disk.** At least 5 GB on `/`.

### 3.2 NTP sync (step 4)

5. **Verify time-sync.** `timedatectl show -p NTPSynchronized --value` should be `yes`. If not, wait up to 2 minutes for the systemd-timesyncd to sync. If still not synced, exit 1 — the agent's UTC timestamps depend on this.

### 3.3 Install Docker (steps 5-6)

6. **Install Docker** via the official convenience script: `curl -fsSL https://get.docker.com | sh`. Idempotent — does nothing if Docker is already present.
7. **Add the `pi` user to the docker group** so `docker compose` works without sudo.

### 3.4 Install Tailscale (steps 7-9)

8. **Install Tailscale** via the official Debian repo: `curl -fsSL https://tailscale.com/install.sh | sh`. Idempotent.
9. **Bring the tailnet up** with the auth key: `tailscale up --ssh --auth-key="$TAILSCALE_AUTH_KEY" --hostname="solamon-pi-${SITE_SLUG}"`. The `--ssh` flag activates Tailscale SSH (per [`tailscale.md`](tailscale.md) §6).
10. **Verify tailnet membership.** `tailscale status` shows the device as `online`. Wait up to 30 s.

### 3.5 ECR login (step 10)

11. **Configure AWS credentials** in `/etc/solamon/aws-credentials` (mode 600, owner solamon:solamon). Standard `~/.aws/credentials` format with profile `solamon-pi`.
12. **Install AWS CLI** if not present (`apt-get install awscli`).
13. **Login Docker to ECR**: `aws --profile solamon-pi ecr get-login-password --region af-south-1 | docker login --username AWS --password-stdin {ECR_URL}`. Works for 12 hours; refreshed via cron (step 16 below).

### 3.6 Edge agent deploy (steps 11-14)

14. **Create the `solamon` user** if not present (no shell, no home dir; just owns the agent's data files).
15. **Create directories**: `/etc/solamon/`, `/var/lib/solamon/` (mode 700, owner solamon:solamon).
16. **Write `bootstrap.yaml`** to `/etc/solamon/bootstrap.yaml` (mode 600). Content:
    ```yaml
    schema_version: "1.0"
    site_slug: "${SITE_SLUG}"
    cloud_url: "${CLOUD_URL}"
    bearer_token: "${BEARER_TOKEN}"
    log_level: INFO
    ```
17. **Pull the agent image**: `docker pull {ECR_URL}/solamon-edge-agent:{TAG}`.
18. **Generate `docker-compose.yml`** at `/opt/solamon/docker-compose.yml` (small template — see script).
19. **Start the agent**: `cd /opt/solamon && docker compose up -d`.

### 3.7 Cron for ECR auth refresh (step 15)

20. **Install a cron job** that refreshes the ECR docker-login every 6 hours (well within the 12-hour token lifetime). Owner: root. Logs to `/var/log/solamon-ecr-refresh.log`.

### 3.8 Verification (step 16)

21. **Wait up to 90 s** for the agent's first heartbeat to appear in the cloud. Verification: poll `${CLOUD_URL}/api/v1/sites/${SITE_SLUG}/health` (with `Authorization: Bearer ${BEARER_TOKEN}`) until `last_heartbeat_at` is within the last 90 s.
22. Print `✓ Edge agent ready at $(tailscale ip --4)` and exit 0.

If the heartbeat doesn't appear after 90 s: print the last 50 lines of the agent's container logs (`docker logs solamon-edge-agent --tail 50`), `tailscale status`, and the result of `curl ${CLOUD_URL}/api/v1/health`. Exit with code 2 ("agent installed but not connecting").

## 4. Idempotency

Re-running the script on a partially-installed Pi is safe. Each step uses `apt-get install -y` (no-op if already installed), `mkdir -p`, `tailscale up` (re-up with the same auth key just refreshes), `docker compose up -d` (idempotent).

The bootstrap.yaml is overwritten every time — if the operator re-runs with different `--site-slug`, the new value wins. For a clean re-install, manually `docker compose down -v && rm -rf /etc/solamon /var/lib/solamon` first.

## 5. Error handling

`set -euo pipefail` exits on any error. The script wraps each step in:

```bash
log_step() {
  echo "[$STEP_NUM/$TOTAL_STEPS] $1..."
  STEP_NUM=$((STEP_NUM + 1))
}

run_or_die() {
  if ! "$@"; then
    echo "✗ Failed: $*"
    echo "Last 20 lines of journalctl -u docker.service:"
    journalctl -u docker.service --no-pager -n 20
    exit 1
  fi
}
```

Specific failures get specific exit codes:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Bad arguments / pre-flight check failed |
| 2 | Agent installed but not heart-beating to cloud (verify network, cloud URL, token) |
| 3 | Tailscale failed to register (verify auth key not expired) |
| 4 | ECR pull failed (verify AWS credentials) |
| 5 | Docker install failed |

## 6. Update procedure

For an existing Pi that needs a new agent version:

```bash
ssh pi@solamon-pi-{slug}
sudo bash /opt/solamon/update.sh --edge-image-tag v0.2.0
```

`update.sh` is a small sibling script that re-runs steps 17 + 19 only (pull new image, restart compose). The full install script is for fresh Pis.

## 7. Decommission procedure

For a Pi being removed from a site (out of MVP scope but worth the operator-runbook note):

1. From an admin laptop: `ssh pi@solamon-pi-{slug}` then `sudo /opt/solamon/decommission.sh`.
   *(Or remote via Tailscale console — remove device, wait for disconnect.)*
2. The script: stops the container, deletes credentials files, calls `tailscale down && tailscale logout`.
3. Tailscale console: remove the device.
4. Cloud admin: deactivate the site row.
5. Physically wipe the SD card if hardware is reused elsewhere.

`decommission.sh` is post-MVP polish; for now, manual cleanup of the listed steps.

## 8. Cross-references

- [`scripts/solamon-edge-install.sh`](scripts/solamon-edge-install.sh) — the actual implementation
- [`tailscale.md`](tailscale.md) §7 — the auth key this script consumes
- [`ecr-and-images.md`](ecr-and-images.md) §6.1 — the IAM user this script uses
- [`../edge-agent/config-loader.md`](../edge-agent/config-loader.md) §2 — the bootstrap.yaml shape this script writes
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.7 — the health endpoint used for verification
