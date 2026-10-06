# Remote access

Remote access is opt-in. Without the compose `remote` profile, nothing in the
stack is reachable from outside your LAN or tailnet.

Two hostnames front the stack, each on its own Cloudflare Tunnel:

| Hostname | Target (inside compose) | Who gets in |
|----------|-------------------------|-------------|
| `ebooks.culture.dev` | `http://api:8780` (web UI + main API) | Cloudflare Access SSO, allow-listed emails only |
| `xteink.culture.dev` | `http://api:8781` (device app only) | Anyone who reaches it, but every route needs an xteink device key |

The device app on port 8781 serves only `/api/device/*`. Every other path,
including `/docs` and `/openapi.json`, returns 404. So the tunnel-only hostname
exposes device sync and nothing else: no library writes, no admin routes and no
MCP.

## Why two tunnels

`cultureflare remote-login setup` replaces a tunnel's whole ingress list with
`[hostname, 404]` (`cultureflare/_remote_login/_tunnel.py`, `ensure_tunnel_config`).
Two hostnames on one tunnel would silently drop the first one. Each hostname
therefore gets cultureflare's default per-hostname tunnel, and compose runs one
connector per tunnel (`cloudflared-ui`, `cloudflared-device`). This is recorded
as devague deviation `d1`.

## Provisioning (done once, with cultureflare)

xteink never calls the Cloudflare API. Tunnels, DNS and Access are owned by
[cultureflare](https://github.com/agentculture/cultureflare), which needs
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in its own environment.
Run each command without `--apply` first and read the plan:

```bash
cultureflare remote-login setup --hostname ebooks.culture.dev \
  --service http://api:8780 --allow OWNER_EMAIL --apply
cultureflare remote-login setup --hostname xteink.culture.dev \
  --service http://api:8781 --no-access --apply
cultureflare remote-login show --hostname ebooks.culture.dev
cultureflare remote-login show --hostname xteink.culture.dev
```

The `--service` targets use the compose service name `api`, because cloudflared
runs inside the compose network. `http://127.0.0.1:...` would point at the
cloudflared container itself.

`xteink tunnel plan` prints these commands with your hostnames and ports filled
in.

## Connector tokens

Each tunnel has a connector token. Keep the tokens out of `.env` and out of git.
On spark they are hidden secrets in the operator's
[grant](https://github.com/agentculture/grant) store:

| grant secret | Tunnel |
|--------------|--------|
| `XTEINK_TUNNEL_TOKEN_UI` | `ebooks-culture-dev` |
| `XTEINK_TUNNEL_TOKEN_DEVICE` | `xteink-culture-dev` |

A token can be fetched again at any time from Cloudflare, so rotating one means
re-running the fetch and `grant set NAME - --hidden` with the new value on stdin.

## Starting the remote profile

`grant run --inject` hands the tokens to compose as environment variables at
exec time, so they never touch a file:

```bash
grant run \
  --inject TUNNEL_TOKEN_UI=XTEINK_TUNNEL_TOKEN_UI \
  --inject TUNNEL_TOKEN_DEVICE=XTEINK_TUNNEL_TOKEN_DEVICE \
  -- docker compose --profile remote up -d
```

Without `--profile remote`, `docker compose up -d` starts only `api` and `mcp`,
and no cloudflared container runs (`scripts/check-compose.sh` checks this).

## Checking it

```bash
xteink tunnel status
curl -sI https://ebooks.culture.dev/            # Access login redirect (3xx)
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-Xteink-Protocol: 1' https://xteink.culture.dev/api/device/queue   # 401
curl -s -o /dev/null -w '%{http_code}\n' https://xteink.culture.dev/api/library  # 404
```

A device key turns the `401` into `200`. The `404` on `/api/library` shows that
library routes are not reachable through the device hostname.
