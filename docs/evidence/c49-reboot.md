# c49 evidence: the stack comes back after a spark reboot

Date: 2026-10-07. The operator rebooted spark; it came back up at 03:16:29
local time. Nothing was started by hand afterwards.

## Containers

All four services of compose project `xteink` restarted on their own
(`restart: unless-stopped`) about 47 s after boot and reported healthy:

```text
xteink-mcp-1                 Up 31 seconds (healthy)
xteink-api-1                 Up 31 seconds (healthy)
xteink-cloudflared-device-1  Up 31 seconds (healthy)
xteink-cloudflared-ui-1      Up 31 seconds (healthy)
```

## Endpoints (03:17:56, about 90 s after boot)

```text
ebooks /            302 -> https://agentculture.cloudflareaccess.com/cdn-cgi/access/login/ebooks.culture.dev
xteink device queue 401   (no device key)
xteink /api/library 404   (device hostname exposes device routes only)
LAN device :8781    401   (no device key)
LAN main :8780 /    200   (web UI)
MCP :8782           307   (/mcp -> /mcp/)
```

## State

With the operator's API key (injected by grant, not printed), the library
still lists 3 items, and device 3 (`x3-ori`) is still active; devices 1 and 2
are still revoked. The SQLite store and blobs survived the reboot.

## How the secrets survive

The tunnel tokens and the MCP API key are injected with `grant run --inject`
when the stack is created. Docker keeps them in each container's saved config,
which is why `unless-stopped` can restart the containers after a reboot without
grant. They are not in any file in the repo or in `.env`, but anyone who can
run `docker inspect` on spark can read them (risk r28).
