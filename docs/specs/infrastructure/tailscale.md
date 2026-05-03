# Infrastructure — Tailscale

**Spec group:** [infrastructure](README.md)
**Linear:** [SOL-21](https://linear.app/solamon/issue/SOL-21)

Per main spec §3, Tailscale is the MVP Pi-management mechanism. Marius and Johan SSH to Pis (and to the cloud EC2) through the tailnet — no inbound public ports anywhere except the cloud's 80/443/8883.

---

## 1. Account + tailnet

Free-tier Tailscale account dedicated to the project. Sign up with the same project email used for AWS root (per [`aws-account.md`](aws-account.md) §1).

- Free plan: 100 devices, 3 users, no SSO required.
- Tailnet name: auto-generated (something like `tail9abcd.ts.net`).
- We don't need a custom tailnet name in MVP — MagicDNS uses the auto-generated name and that's fine.

## 2. Users

Two human users:
- `marius@bloemhof.dev` (admin)
- `johan@<johan's email>` (admin or member, depending on their day-to-day role)

Both authenticate via passwordless email magic-link or via GitHub SSO if they prefer. MFA enforced at the SSO layer (GitHub MFA flows through automatically).

## 3. Devices

Tailscale auto-registers each device on first login. Naming convention via MagicDNS:

| Device class | Hostname pattern |
|--------------|------------------|
| Pi at a site | `solamon-pi-{site-slug}` (e.g., `solamon-pi-johansworkbench`) |
| Cloud EC2 | `solamon-cloud-prod` |
| Marius's laptop | `marius-laptop` |
| Johan's laptop | `johan-laptop` |

After Tailscale registration, `ssh pi@solamon-pi-johansworkbench` works from any tailnet member.

## 4. Tags

Tailscale tags identify device CLASSES (independent of their auto-registered names). ACLs operate on tags, not hostnames — so a new Pi with a `tag:pi` is automatically subject to all `pi`-related ACL rules without manual list edits.

| Tag | Applied to | Purpose |
|-----|-----------|---------|
| `tag:pi` | Every Pi | Site Pis as a class |
| `tag:cloud` | The cloud EC2 | The cloud as a class |
| `tag:admin` | Marius's + Johan's laptops | Human admin devices |

Tag ownership is declared in the tailnet ACL (§5).

## 5. ACL

Tailscale ACLs are JSON, edited via the admin console (or via the API for automation later). MVP ACL:

```json
{
  "tagOwners": {
    "tag:pi":    ["marius@bloemhof.dev", "johan@..."],
    "tag:cloud": ["marius@bloemhof.dev", "johan@..."],
    "tag:admin": ["marius@bloemhof.dev", "johan@..."]
  },

  "acls": [
    {
      "action": "accept",
      "src": ["tag:admin"],
      "dst": ["tag:pi:22", "tag:cloud:22"]
    },
    {
      "action": "accept",
      "src": ["tag:admin"],
      "dst": ["tag:pi:*", "tag:cloud:*"]
    }
  ],

  "ssh": [
    {
      "action": "accept",
      "src": ["tag:admin"],
      "dst": ["tag:pi", "tag:cloud"],
      "users": ["pi", "ubuntu", "solamon"]
    }
  ]
}
```

What this gives us:

- **`tag:admin` (Marius / Johan laptops) can SSH** to any `tag:pi` or `tag:cloud` device as user `pi`, `ubuntu`, or `solamon`.
- **`tag:admin` can also reach any other port** on `tag:pi` / `tag:cloud` (useful for VS Code Remote-SSH, port forwarding for debugging, etc.).
- **No `tag:pi` → `tag:pi`** rule — Pis CAN'T talk to each other. Multi-site VPN-mesh is post-MVP.
- **No `tag:pi` → `tag:cloud`** rule — Pi-to-cloud goes via the **public internet** (MQTT TLS on 8883), not via the tailnet. The tailnet is purely a management plane.

## 6. SSH key delegation: Tailscale SSH

Tailscale SSH (`ssh:` in the ACL) replaces traditional SSH keys with the tailnet identity. **The Pi has no `~/.ssh/authorized_keys` for Marius/Johan** — instead, the `tailscaled` daemon authenticates incoming SSH connections by verifying the source is a tagged tailnet member and the user matches.

Setup on the Pi (in `solamon-edge-install.sh`):

```bash
sudo tailscale up --ssh --auth-key=tskey-auth-...
```

The `--ssh` flag enables Tailscale's SSH server on port 22 of the device, replacing OpenSSH's auth path.

**Pros:** No SSH keys to manage. Revoking a tailnet user revokes their SSH access automatically.
**Cons:** Only works for tailnet members; doesn't help if you're locked out of Tailscale.

For belt-and-braces, also add Marius's SSH public key to `~pi/.ssh/authorized_keys` (and Johan's if applicable) — that way OpenSSH on port 22 over the tailnet still works if Tailscale SSH ever has a hiccup.

## 7. Auth keys for the install scripts

The Pi install script needs Tailscale to register the device automatically — it can't prompt the operator to log in via browser at install time.

Solution: **pre-authorised keys** ("tailnet auth keys"). Generated in the Tailscale admin console:

- Type: **Reusable** + **Pre-authorized** + **Tagged** with `tag:pi`
- Expiry: 90 days from generation (rotate quarterly)
- Description: "Pi installer — solamon-edge-install.sh"

The key value (`tskey-auth-...`) is passed to the install script via `--tailscale-auth-key` argument or read from a secrets-mounted file. The script runs `tailscale up --ssh --auth-key=...`. The Pi joins the tailnet pre-tagged.

**Same pattern for the cloud EC2 install** — a separate auth key tagged `tag:cloud`, used by `solamon-cloud-bootstrap.sh`.

## 8. MagicDNS

Enabled in tailnet settings. Provides:

- `solamon-pi-johansworkbench` resolves to the Pi's tailnet IP (100.64.0.0/10 CGNAT range).
- `solamon-pi-johansworkbench.tail9abcd.ts.net` is the FQDN.

We use the short form everywhere (`ssh marius@solamon-pi-johansworkbench`) — tailnet's DNS resolver handles the suffix.

## 9. Subnet routes — NOT used in MVP

Tailscale supports advertising "subnet routes" so a tailnet device can reach non-tailnet devices on its LAN. We **don't use this** in MVP because:

- The Pi is the only device we need to reach at each site. The Pi is itself a tailnet member.
- Advertising the site's whole LAN (192.168.x.x/24) into the tailnet is overkill and creates a route-collision risk (multiple sites with the same 192.168.1.0/24).

If we ever need to access a non-tailscale-running device on a site's LAN (e.g., to debug a Modbus device directly from Marius's laptop), we add a subnet route on the Pi for that site. Document case-by-case.

## 10. Removal — Pi decommission

When a Pi is removed from a site:

1. Tailscale admin console → Devices → select `solamon-pi-{slug}` → Remove.
2. (Pi is now off the tailnet; SSH from admin laptops fails immediately.)
3. Optionally physically wipe the Pi's SD card if reusing the hardware elsewhere.

The `solamon-edge-install.sh` script's reverse — `solamon-edge-uninstall.sh` — is post-MVP. For now, manual removal in the console is fine.

## 11. Audit log

Tailscale logs every SSH session, ACL evaluation, and device registration to the admin console's audit page. **Not exported to S3 / SIEM in MVP** — only retained on Tailscale's free tier (~30 days).

For SOC-2-like compliance work post-MVP, configure the Tailscale → S3 log streaming feature.

## 12. Acceptance

- Tailnet created; both Marius and Johan registered as users with MFA.
- ACL JSON deployed; `tag:admin → tag:pi:22` rule in place.
- Pi auth key generated, tagged `tag:pi`, expiry 90 days.
- Cloud auth key generated, tagged `tag:cloud`, expiry 90 days.
- MagicDNS enabled.
- A test Pi joins the tailnet via the auth key and is SSH-reachable from Marius's laptop within 60 s of `tailscale up`.
- ACL change to test-revoke a user → SSH fails within 30 s.

## 13. Cross-references

- [`pi-install.md`](pi-install.md) — uses the `tag:pi` auth key
- [`cloud-bootstrap.md`](cloud-bootstrap.md) — uses the `tag:cloud` auth key
- Main spec §3 + §13 — locks Tailscale for MVP, plans migration to AWS SSM
