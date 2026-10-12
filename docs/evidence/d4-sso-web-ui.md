# d4 evidence: Cloudflare Access SSO is enough for the web UI

Date: 2026-10-07. Production stack on spark (compose project `xteink`),
`XTEINK_ACCESS_TEAM_DOMAIN` and `XTEINK_ACCESS_AUD` set in the gitignored `.env`.

## Before the zone cache fix

- After SSO the browser showed the previous UI and its key panel, but no request
  from the UI tunnel connector (`172.28.0.3`) reached the api.
- Cause: the culture.dev zone's catch-all cache rule (`true` -> cache, edge TTL
  7200 s override) applied to `ebooks.culture.dev` and `xteink.culture.dev`.
  Fixed by appending bypass rules (see `docs/remote-access.md`) and purging 12
  URLs. `xteink.culture.dev` now answers `cf-cache-status: DYNAMIC`.

## After (api access log, requests via the UI tunnel)

```text
172.28.0.3 - "GET / HTTP/1.1" 200 OK
172.28.0.3 - "GET /assets/index-DJmZci_G.js HTTP/1.1" 200 OK
172.28.0.3 - "GET /api/whoami HTTP/1.1" 200 OK
172.28.0.3 - "GET /api/library?limit=50 HTTP/1.1" 200 OK
172.28.0.3 - "GET /api/devices HTTP/1.1" 200 OK
172.28.0.3 - "GET /api/devices/2/queue?state=all HTTP/1.1" 200 OK
```

No `Authorization` header was involved: `/api/whoami` returned 200 on the
Cloudflare Access JWT alone.

## Negative checks (same deploy)

- LAN `GET /api/whoami` without a key: 401.
- LAN `GET /api/whoami` with a forged `Cf-Access-Jwt-Assertion`: 401
  (`access jwt refused (malformed)`).
- Anonymous `https://ebooks.culture.dev/`: 302 to the Access login.
