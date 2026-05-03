# Infrastructure — Caddy + DNS

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Domain, DNS records, Caddy reverse proxy, automatic Let's Encrypt TLS for HTTPS. **Mosquitto runs its own TLS on port 8883** — separate from Caddy.

---

## 1. Domain choice

Two options for MVP. Either works; pick one and move on:

### 1.1 Option A: Register a project domain

`solamon.co.za` (~R 150 / year via Domains.co.za / Hetzner.co.za / similar) or `.solar.za` if available.

**Pros:** Project-owned identity. Easier rebrand-as-product later.
**Cons:** Annual renewal; one more thing to keep track of.

### 1.2 Option B: Subdomain of an existing domain (chosen for MVP)

`cloud.solamon.bloemhof.dev` or similar — Marius's existing personal domain with a subdomain delegated to the project's DNS.

**Pros:** Free; Marius already owns the apex.
**Cons:** Branding mixed with personal identity. Easy to swap later (just point a new domain's CNAME at the same EC2 IP).

For MVP, **Option B is recommended** — defer the brand decision until there's a real customer-facing reason to make it.

## 2. DNS records

For the chosen domain (e.g., `cloud.solamon.bloemhof.dev`):

| Record | Type | Value | TTL |
|--------|------|-------|-----|
| `cloud.solamon.bloemhof.dev` | A | EC2 elastic IP (e.g. `13.245.123.45`) | 300 |
| `cloud.solamon.bloemhof.dev` | AAAA | (empty — no IPv6 in MVP) | — |
| `_acme-challenge.cloud.solamon.bloemhof.dev` | CNAME | (empty unless we use DNS-01 — see §4) | — |

DNS provider is whoever the apex is registered with — Cloudflare for `bloemhof.dev` is fine. Free tier handles MVP traffic.

For Option A (project-owned domain): Route 53 hosted zone in the project AWS account; same A record. Adds ~R 12/month.

## 3. Caddy configuration

Caddy 2.x runs as a Docker container in the cloud's docker-compose stack, on ports 80 and 443. It auto-provisions TLS via Let's Encrypt (HTTP-01 challenge — works on port 80 for any reachable domain).

```caddy
# /etc/caddy/Caddyfile (templated by solamon-cloud-bootstrap.sh)

{
    email admin@bloemhof.dev      # Let's Encrypt account email
    # acme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}   # uncomment for DNS-01 if needed
}

cloud.solamon.bloemhof.dev {
    encode zstd gzip

    # Static / SPA routes go to Next.js
    reverse_proxy /api/* app:8000     # FastAPI on port 8000 inside the network
    reverse_proxy /api/v1/ws/* app:8000 {
        # WebSocket upgrade
        header_up Upgrade {http.request.header.Upgrade}
        header_up Connection {http.request.header.Connection}
    }
    reverse_proxy /* web:3000          # Next.js on port 3000

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    # Logs to stdout (Docker collects)
    log {
        output stdout
        format json
    }
}

# HTTP → HTTPS redirect handled implicitly by Caddy's automatic-https
```

`app:8000` and `web:3000` are Docker compose service names resolvable on the internal `solamon` network.

## 4. TLS provisioning

Caddy uses HTTP-01 by default — works on port 80 with no extra config beyond a publicly-reachable A record.

**DNS-01 alternative** (only relevant if we ever can't open port 80, or want wildcard certs): set `acme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}` in the global block, mount a Cloudflare API token. We don't need this in MVP.

**Cert renewal:** automatic. Caddy renews 30 days before expiry. The container's data volume persists `/data/caddy` (which holds the certs) across `docker compose down && up`.

## 5. WebSocket support

Caddy proxies WebSocket connections natively when both `Upgrade` and `Connection` headers are forwarded. The `/api/v1/ws/*` block above does this explicitly. No further config.

The `Sec-WebSocket-Protocol` header (used for auth — see [`../web-ui/auth.md`](../web-ui/auth.md) §3.3 and [`../cloud/api-surface.md`](../cloud/api-surface.md) §5.1) passes through Caddy by default.

## 6. Mosquitto's TLS — NOT through Caddy

Mosquitto handles its own TLS on port 8883 for two reasons:

1. **MQTT is not HTTP** — Caddy reverse-proxies HTTP/WebSocket, not raw TCP. Adding TCP proxy to Caddy is possible but pulls in a layer-4 proxy that we don't need.
2. **Mosquitto's TLS implementation is mature** — it accepts a cert + key file directly, supports SNI, and uses standard OpenSSL.

Mosquitto's certs come from the same Caddy data dir (which Caddy generated) — Caddy stores them at `/data/caddy/certificates/acme.zerossl.com/cloud.solamon.bloemhof.dev/cloud.solamon.bloemhof.dev.crt` (or similar; format varies). Mosquitto's container mounts that path read-only and uses it.

Cert renewal: same Caddy renewal — Mosquitto reloads its cert via SIGHUP. A small sidecar watches Caddy's cert dir for changes and signals Mosquitto.

For MVP, simplest is: **let Mosquitto request its own cert via `certbot` running once a quarter as a manual cron**. Less elegant than the auto-reload setup, but ~zero risk. Move to the auto-reload sidecar when MVP scales.

## 7. EC2 firewall

The EC2's security group (configured in [`cloud-bootstrap.md`](cloud-bootstrap.md)):

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Tailscale CGNAT range only | SSH via Tailscale |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirected to 443 by Caddy) |
| 443 | TCP | 0.0.0.0/0 | HTTPS — web + API + WS |
| 8883 | TCP | 0.0.0.0/0 | MQTT TLS — Pi connections |

**Public internet only sees ports 80, 443, 8883.** SSH is Tailscale-only. No other ports.

## 8. Acceptance

- DNS A record resolves to the EC2 elastic IP from the public internet.
- `curl https://cloud.solamon.bloemhof.dev/api/v1/health` returns `{"status":"ok",...}` over a valid Let's Encrypt cert.
- `curl http://cloud.solamon.bloemhof.dev/api/v1/health` returns 308 redirect to https://.
- WebSocket connection to `wss://cloud.solamon.bloemhof.dev/api/v1/ws/...` upgrades successfully.
- MQTT TLS connection to `cloud.solamon.bloemhof.dev:8883` from the Pi handshakes successfully (verified with `mosquitto_sub` client).
- HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy headers present (verified via `curl -I`).
- Cert auto-renews — verified by checking Caddy's logs after `acme_renew` runs the first time.

## 9. Cross-references

- [`cloud-bootstrap.md`](cloud-bootstrap.md) — provisions the EC2 + writes the Caddyfile from this template
- [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §10 — Mosquitto connection params (port 8883)
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §5 — WebSocket endpoints proxied here
