# Secrets — SOP for agents and sessions

**Applies to:** every Claude Code session on this repo, local or cloud.
**Owner:** Marius Bloemhof. **Last updated:** 2026-10-15.

## The rules

1. **Secrets never appear in chat, in the repo, or in logs.** Don't ask for one to be pasted, don't print one, don't commit one.
2. **All Solamon secrets live in the Ironwire Client Zone vault.** Workspace **Amendi**, project **Solamon**. Nothing else is the source of truth.
3. **You don't hold standing access. You request it, and Marius grants it** — per use, approved with his passkey.

## What's in the vault

Workspace `amendi` (id `6JPtyTecz0XmsFa9`), project Solamon (id `0ayQLFdAxVCgZoyj`). Names and ids only — the values are end-to-end encrypted and only open with a person's passkey.

| Secret | Id | Fields |
|---|---|---|
| AWS key: IAM user Marius (FULL ADMIN) | `ZtqSdEsxJ0Sg8bPrUnaT` | `Access key ID`, `Secret access key` |
| AWS key: pi-ecr-puller (ECR pull only) | `zM7YLmiH1suJxPnGPlau` | `Access key ID`, `Secret access key` |
| Cloudflare DNS token (amendi.dev) | `OETFpBA8X8428i9L493v` | the token |
| EC2 bootstrap SSH key (private) | `AHyuCrBTLpjcRNIdkWEr` | private key; `Username`, `Host` |
| EC2 bootstrap SSH public key | `jKSzqRfpDW1L4IsC0zu1` | `Public key` |
| Production .env (`/opt/solamon/.env`) | `JGdlYvHKZNjraTOyZnR8` | the file |
| Previous .env versions (10 backups, May 2026) | `YIUi9JDq7JXKo2d7ad5D` | the file |
| Mosquitto auth files (passwords + acls) | `P4zVFADnrmZZP5LWNsQb` | `Contents` |
| Bench MQTT TLS truststore | `MrS4KxkbCertrykzMIbr` | the certificate |

The list may have grown — check with the Ironwire connector's `list_secrets` (workspace `6JPtyTecz0XmsFa9`). It returns names and metadata, never values.

## Before you ask: do you need a secret at all?

Most infrastructure work runs **on Marius's local machine** (via the desktop app's local-run approval), which already has:

- the AWS CLI profile `solamon` (`--profile solamon --region af-south-1`)
- the Tailscale tailnet — the only SSH path to the box: `ssh ubuntu@100.77.122.23`
- the Cloudflare token at `~/.cloudflare-token`

If the task runs there, use what's there. **Don't pull a secret from the vault just to recreate access that already exists locally.** Request one only when the access is genuinely missing — a new machine, a cloud sandbox, or a secret that only exists in the vault (the production `.env`, for example).

## How to request access

Use **`iw-use`** on the machine that needs the value. It asks Marius, waits for his approval, and hands the value **straight into one command** — the value never enters your context.

```bash
# Get the helper (Node 20+)
curl -sS -o iw-use.mjs https://clients.ironwire.co.za/cli/iw-use.mjs

# It needs the zone address and a zone token
export IRONWIRE_URL=https://clients.ironwire.co.za
export IRONWIRE_TOKEN="$(cat ~/.ironwire-token)"   # on Marius's machine; elsewhere, ask Marius

# Use a secret once: the value arrives in $IW_SECRET for this command only
node iw-use.mjs --secret OETFpBA8X8428i9L493v \
  --reason "Point cloud.amendi.dev at the replacement EC2" \
  -- sh -c 'curl -sS -H "Authorization: Bearer $IW_SECRET" https://api.cloudflare.com/client/v4/...'
```

What happens:

1. `iw-use` makes a one-use key pair and asks the zone. **Marius is emailed.**
2. He approves with his passkey. **The ask lapses after 30 minutes.**
3. The value is sealed to the one-use key, handed over **once, within 5 minutes**, then deleted from the zone.
4. It runs your command with the value in `IW_SECRET`.

Useful options:

- `--field "<Label>"` picks a field, e.g. `--field "Secret access key"`. The default is the secret part.
- `--env NAME` puts the value in `NAME` instead of `IW_SECRET`.
- `--file` writes the value to a private temporary file, which is deleted afterwards. Use `{}` in the command for its path, e.g. `ssh -i {} …`.
- `--task <KEY>` links the use to a task.

**Write a real `--reason`.** Marius approves based on it: say what you're doing and why, e.g. "Restore production DB password after rebuilding the EC2" — not "need access".

**Never use `--print` or `--print-json`.** They write the value to standard output, which puts it in your context and the transcript.

AWS needs two fields. Nest two `iw-use` calls, which means two approvals:

```bash
node iw-use.mjs --secret ZtqSdEsxJ0Sg8bPrUnaT --field "Access key ID" --env AWS_ACCESS_KEY_ID --reason "..." -- \
  node iw-use.mjs --secret ZtqSdEsxJ0Sg8bPrUnaT --field "Secret access key" --env AWS_SECRET_ACCESS_KEY --reason "..." -- \
  aws sts get-caller-identity --region af-south-1
```

The Marius AWS key is **full admin**. Prefer the local `solamon` profile on Marius's machine, and say so in the reason if you truly need the vault copy.

## How to add or update a secret

Use **`iw-seal`**, which encrypts on the local machine so neither you nor the zone can read the value:

```bash
curl -sS -o iw-seal.mjs https://clients.ironwire.co.za/cli/iw-seal.mjs
node iw-seal.mjs --client amendi --pin "D1F4 1268 955C 275A" \
  --file <path> --kind <api_key|token|ssh_key|env_file|certificate|note|...> \
  --name "<what it is>" --environment production --project 0ayQLFdAxVCgZoyj \
  --notes "<what it's for, scope, where it's issued>" --submit
```

- Read the value from where it already lives: `--file`, `--env`, or `--stdin` piped from a command. For example, `ssh … 'sudo cat /opt/solamon/.env' | node iw-seal.mjs --stdin …`.
- `--pin` is the vault's signing-key fingerprint. If `iw-seal` reports a different key, **stop and tell Marius** — don't use `--repin` yourself.
- Check the input isn't empty before trusting the result. `iw-seal` rejects an empty value, and a permission error inside an SSH pipe produces exactly that.
- Tell Marius what you added. He opens it once with his passkey to confirm it.

## Requirements in the zone (Marius's side)

For any of this to work:

- A zone token with **"May add secrets"** (for `iw-seal`), created under Settings → Agent access.
- The Amendi workspace setting **"Agents may ask to use a secret"** turned on (for `iw-use`).
- On Marius's machine, the token lives at `~/.ironwire-token`. A cloud sandbox has no token by default — ask Marius to provide one if a task truly needs `iw-use` there.
