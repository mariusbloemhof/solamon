# Edge agent — config loader

**Spec group:** [edge-agent](README.md)
**Linear:** [SOL-7](https://linear.app/solamon/issue/SOL-7)

How the edge agent obtains its configuration: bootstrap file at install time, cloud fetch on startup, local cache for offline survival, periodic refresh.

---

## 1. Two-tier config

The agent uses **two configuration files** with different lifecycles:

| File | Lifecycle | Contents | Edited by |
|------|-----------|----------|-----------|
| `/etc/solamon/bootstrap.yaml` | Set at Pi install; rarely changes | Site identity + cloud endpoint + per-site secret | Installer (human) via `solamon-edge-install.sh` |
| `/etc/solamon/site_config.yaml` | Cached from cloud; refreshed every 5 min | Full site config (profile, catalog, MQTT creds, device details) | Cloud (via `GET /api/v1/edge/config/{site_slug}`) |

The bootstrap file is the minimum required to call the cloud. Once we can reach the cloud, the cloud is the authoritative source of all other config.

## 2. Bootstrap file

```yaml
# /etc/solamon/bootstrap.yaml
schema_version: "1.0"
site_slug: johansworkbench
cloud_url: https://cloud.solamon.example
bearer_token: "<per-site secret, same value as the MQTT password>"
log_level: INFO    # optional; default INFO
```

Generated at install time by `solamon-edge-install.sh` (specified in the infrastructure spec group — [SOL-21](https://linear.app/solamon/issue/SOL-21), TBD). The installer passes `site_slug` + `cloud_url` + `bearer_token` as arguments; the script writes the YAML.

**Expected runtime user:** the agent runs as the `solamon` system user (created by the installer). The bootstrap file is owned by `solamon:solamon` mode `600` so a non-root operator can `sudo cat` it but the agent itself doesn't need root to read it.

**Validation on startup:**

- File exists at the expected path. Missing → exit 1, log `bootstrap_missing`.
- YAML parses. Parse error → exit 1, log `bootstrap_invalid`.
- Required fields present (`site_slug`, `cloud_url`, `bearer_token`). Missing → exit 1.
- `cloud_url` is a parseable HTTPS URL. Plain HTTP rejected.

The `bearer_token` is the same secret the agent uses as the MQTT password. We deliberately conflate them in MVP — one secret per Pi simplifies provisioning. They diverge when we move to mTLS device certificates ([SOL-10](https://linear.app/solamon/issue/SOL-10)).

## 3. Cloud config fetch

```python
# Pseudo-code
async def fetch_site_config(bootstrap: Bootstrap) -> SiteConfig:
    url = f"{bootstrap.cloud_url}/api/v1/edge/config/{bootstrap.site_slug}"
    headers = {"Authorization": f"Bearer {bootstrap.bearer_token}"}
    # 60 s timeout — generous on bench LAN; survives marginal LTE during a field deploy
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return parse_site_config(response.json())
```

Returns the full `EdgeConfig` shape per [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.6:

- `site` — slug, id, timezone, name
- `device` — id, host, port, unit_id, profile_slug
- `profile` — full profile YAML (parsed to dict)
- `logical_metrics_catalog` — full catalog
- `mqtt` — broker_host, broker_port, username, password, client_id, topic_prefix

### 3.1 Validation on receive

- Response status 200. 401/403 → exit 1, log `bootstrap_token_rejected` (probably the bearer_token in bootstrap is wrong).
- Response shape matches the OpenAPI `EdgeConfig` schema. Mismatch → log error, fall back to cached config if available; else exit 1.
- `profile` validates against `architecture/profiles/profile.schema.json`. Validation failure → log error, fall back to cache.
- `device.profile_slug` matches the profile's declared `device.model`. Mismatch → log warning (cloud-side seeding error) but continue with the profile that was sent.

### 3.2 Caching

After a successful fetch, write the entire response to `/etc/solamon/site_config.yaml` atomically:

```python
import os, tempfile, yaml

def atomic_write_cache(path: Path, data: dict):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".site_config.tmp.")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        os.replace(tmp, path)        # atomic rename
    except Exception:
        os.unlink(tmp)
        raise
```

The atomic rename ensures no partial / corrupt cache on disk if the process crashes mid-write.

The cache is **the agent's source of truth** during runtime — even after a successful fetch, the cache file is what the rest of the code reads. The fetch is essentially an "update the cache + tell pollers to reload" operation.

## 4. Periodic refresh

Every **5 minutes**, the config refresh task re-fetches the cloud config:

```python
async def config_refresh_task():
    while not shutdown:
        await asyncio.sleep(300)  # 5 minutes
        try:
            new_config = await fetch_site_config(bootstrap)
            if new_config_differs(current_config, new_config):
                log.info("site_config_changed",
                         old_version=current_config.version,
                         new_version=new_config.version)
                # MVP: log only. Restart required to apply.
                # SOL-17 (post-MVP): trigger hot reload.
            atomic_write_cache(SITE_CONFIG_PATH, new_config.dict())
        except httpx.HTTPError as e:
            log.warn("config_refresh_failed", error=e)
            # Continue with current cache — no behavioural change
```

For MVP, **the in-memory profile is not swapped on refresh**. Only the cache file is updated. Operator must `systemctl restart solamon-edge` (or `docker compose restart edge-agent`) to pick up changes. Hot reload is [SOL-17](https://linear.app/solamon/issue/SOL-17).

### 4.1 Operator-restart cases

The following config / state changes require a manual `docker compose restart edge-agent` (until SOL-17 lands hot reload):

- **Device profile change** — e.g., a register address corrected in the YAML, or a per-site override added.
- **`device.id` change** — the cloud reseeded the device row (e.g., during a profile correction). The Pi's MQTT subscription is hardcoded to `solamon/{slug}/commands/{device.id}`; the new device.id won't take effect until restart, and any commands issued in the meantime are silently dropped.
- **Logical metric catalog change** — added/removed metrics, range edits.
- **Modbus host / port / unit_id change** — site config carries these but the Modbus client is opened once at startup.
- **Device hardware replacement** — re-fingerprint only runs at startup; new hardware needs a fresh fingerprint check.

Each of these is operator-driven and rare. The deploy procedure for any of them is "edit YAML in repo → re-seed cloud → SSH to Pi → restart container". Document this in the operator runbook (TBD; lives in infrastructure spec).

## 5. Fallback behaviour

| Scenario | Behaviour |
|----------|-----------|
| Bootstrap file missing | Exit 1; operator must run install script |
| Cloud unreachable on first startup, no cache | Exit 1; operator must restore connectivity |
| Cloud unreachable on first startup, cache present | Load cache, log warning, continue |
| Cloud reachable but returns error (401/403) | Exit 1; bootstrap token bad |
| Cloud reachable but returns invalid config | Fall back to cache; if cache missing, exit 1 |
| Cloud unreachable mid-life | Continue with current config; refresh task retries every 5 min; nothing logged at ERROR |
| Cache file corrupted | Treat as missing; same fallbacks as above |

The principle: **a Pi that's already running stays running**. Cloud transient failures don't cause restarts. Only first-boot or hard-failures terminate the process.

## 6. Secret hygiene

- Bootstrap file permissions: `600`, owner `solamon` (the daemon's user). Created by the install script.
- Site config cache permissions: same.
- The bearer token / MQTT password is logged ONLY when masked: `Bearer ****1234` (last 4 chars). Never the full token.
- The Pi's environment variables don't carry the secret — it's only in the YAML file. This is so a `docker inspect` doesn't expose it.
- The bearer-token-and-MQTT-password are deliberately the same value in MVP (see [`../cloud/api-surface.md`](../cloud/api-surface.md) §3.4). A future split (post-mTLS migration, [SOL-10](https://linear.app/solamon/issue/SOL-10)) would require revisiting log redaction to mask both independently.
- When the cloud rotates the per-site secret (post-MVP feature), **the agent must overwrite `/etc/solamon/bootstrap.yaml.bearer_token` from the response's `mqtt.password` field** after every successful refresh. Otherwise the bootstrap file's bearer goes stale beyond the 24-hour grace period and the agent permanently loses ability to refresh config.

## 7. Acceptance criteria

- Bootstrap parsing: missing field → clear error message naming which field; invalid YAML → clear parse error.
- Cloud fetch: succeeds on a happy-path bench setup; produces a valid cache file readable by `yaml.safe_load`.
- Cache fallback: simulate cloud-down at startup with a pre-populated cache → agent boots and runs.
- Cache fallback exit-1 path: simulate cloud-down with no cache → agent exits 1 with `no_config_available` log line.
- Token mask in logs: grep for any occurrence of the actual bearer token in journal output → none found.
- File permissions: `stat -c %a /etc/solamon/bootstrap.yaml` returns `600`.
- Refresh detects change: post a simulated config update on the cloud (change `device.host`); within 5 min the agent's cache file reflects the new value (in-memory profile unchanged until restart).

## 8. Cross-references

- [`architecture.md`](architecture.md) §3.1 — startup uses this loader
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.6 — `/edge/config/{slug}` endpoint
- [`../infrastructure/pi-install.md`](../infrastructure/pi-install.md) — generates bootstrap.yaml
- [`../device-library/profile-schema.md`](../device-library/profile-schema.md) — profile validated on receive
