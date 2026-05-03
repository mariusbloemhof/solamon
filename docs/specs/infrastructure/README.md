# Infrastructure & deployment — detail specs

**Spec group owner:** [SOL-21 — MVP — Infrastructure & deployment](https://linear.app/solamon/issue/SOL-21)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §3, §5, §12
**Status:** Working spec.

---

## What this spec group covers

Everything outside the application code itself: AWS account setup, container registry, TLS + DNS, the Tailscale tailnet, the Pi install script, the cloud bootstrap script. Roughly Day 1 + Day 2 of bench rehearsal in main spec §12, plus the reusable scripts used at every site.

This group is **decoupled from application detail specs** — once the cloud and edge-agent groups land their detail specs, the infrastructure layer is what gets the resulting Docker images running on real hardware with real TLS at a real DNS name.

## Bring-up sequence

The order in which the docs in this folder get used during initial deployment:

1. **AWS account** ([`aws-account.md`](aws-account.md)) — create the account, set IAM, enable billing alerts. *One-time setup; ~30 min.*
2. **ECR + images** ([`ecr-and-images.md`](ecr-and-images.md)) — set up Private ECR repos, configure CI to push images on tagged release. *One-time setup + every release.*
3. **Caddy + DNS** ([`caddy-and-dns.md`](caddy-and-dns.md)) — domain or subdomain, DNS pointing at the EC2 elastic IP, Caddyfile in place. *One-time per cloud deployment.*
4. **Tailscale** ([`tailscale.md`](tailscale.md)) — tailnet, ACLs, MagicDNS, tags. *One-time setup; reused for every Pi.*
5. **Cloud bootstrap** ([`cloud-bootstrap.md`](cloud-bootstrap.md)) — provision the EC2, run `solamon-cloud-bootstrap.sh`, verify the stack is up. *One-time per cloud deployment; ~1 hour from a fresh EC2.*
6. **Pi install** ([`pi-install.md`](pi-install.md)) — flash Pi OS Lite, run `solamon-edge-install.sh`. *Per-site; ~20 min from boot to first heartbeat.*

Each section's spec is self-contained and includes its own acceptance criteria.

## Files in this folder

| File | What it specifies |
|------|-------------------|
| [`README.md`](README.md) | This index + bring-up sequence. |
| [`aws-account.md`](aws-account.md) | Greenfield AWS account setup, IAM, billing alerts, region config. |
| [`ecr-and-images.md`](ecr-and-images.md) | ECR Private repo for the edge-agent image; build + tag + push pipeline; Pi-side pull credentials. |
| [`caddy-and-dns.md`](caddy-and-dns.md) | Domain/subdomain choice, DNS records, Caddy auto-TLS, reverse proxy to Next.js + FastAPI. Mosquitto's TLS is separate. |
| [`tailscale.md`](tailscale.md) | Tailnet, ACL JSON, MagicDNS, tags, ephemeral keys for the install script. |
| [`pi-install.md`](pi-install.md) | The `solamon-edge-install.sh` script's contract: inputs, steps, idempotency, error handling, verification. |
| [`cloud-bootstrap.md`](cloud-bootstrap.md) | The `solamon-cloud-bootstrap.sh` script's contract: from a fresh EC2 to running stack with verified `/api/v1/health` green. |

## Machine-readable artifacts produced

| Path | What it is |
|------|------------|
| [`scripts/solamon-edge-install.sh`](scripts/solamon-edge-install.sh) | Pi-side install script. Run on a fresh Pi OS Lite (64-bit) image. |
| [`scripts/solamon-cloud-bootstrap.sh`](scripts/solamon-cloud-bootstrap.sh) | EC2-side bootstrap script. Run on a fresh Ubuntu 24.04 LTS ARM64 instance. |

(The Caddyfile, Mosquitto config, docker-compose.yml, and Postgres seed scripts produced by `cloud-bootstrap.sh` are templates inside the script — extracted at runtime to their target paths. They could move to standalone files in `scripts/templates/` if the script grows unwieldy.)

## Acceptance for SOL-21

- All seven `.md` specs in this folder committed.
- Both shell scripts in `scripts/` committed and `bash -n`-clean (syntactically valid).
- Day 1 of bench rehearsal — operator runs `solamon-cloud-bootstrap.sh` on a fresh EC2 and ends with `/api/v1/health` returning `{"status":"ok","db":"ok","mqtt":"ok"}`.
- Day 2 of bench rehearsal — operator runs `solamon-edge-install.sh` on a fresh Pi and ends with the cloud's `/api/v1/sites/bench/health` showing the Pi heartbeat appearing within 90 s of the script finishing.
- Operator runbook in each spec is detailed enough that someone who's NOT Marius can follow it (e.g., a contractor doing a future site install).

## Out of MVP scope

- AWS-native rearchitecture (IoT Core / ECS / Lambda) → [SOL-10](https://linear.app/solamon/issue/SOL-10)
- AWS SSM for Pi management → [SOL-10](https://linear.app/solamon/issue/SOL-10)
- HA / multi-region
- Automated OTA firmware updates beyond `docker compose pull && up -d`
- Terraform / IaC — manual setup in MVP; codify when we onboard the second site
- Production secrets management beyond env vars in compose; Secrets Manager / Vault is post-MVP
- CI/CD pipeline beyond a single GitHub Actions workflow that builds + pushes images on tag
- Multi-tenant isolation
- Site-replacement / decommissioning runbook (covered as a single paragraph in `pi-install.md` §10)
