# Live stack redeploy (deviation d10)

Run 2026-10-11 with the owner's approval. The live compose project `xteink` was rebuilt from `ota/daily-sync` @ `f17c62d`, so the server can offer firmware to the X3 for t16/t17. This also landed the MCP bearer-key change from issue 1 (`7d6264f`).

## Steps

1. `api` and `mcp` were stopped, with the tunnels left up, so the SQLite database could be copied consistently.
2. The `xteink_xteink-data` volume was backed up to `xteink/backups/server/20261011T195030Z-xteink-data.tgz` under the operator's XDG data home (81,991 B, sha256 prefix `160e8704cb8b696e`; contains `library.db` and `files/`). This lives outside the repo and is not committed.
3. The stack was rebuilt with the issue-1 command from the worktree, adding `--env-file` pointing at the main checkout's gitignored `.env`:
   `COMPOSE_PROJECT_NAME=xteink grant run --inject TUNNEL_TOKEN_UI=… --inject TUNNEL_TOKEN_DEVICE=… --inject XTEINK_API_KEY=… -- docker compose --env-file <main checkout>/.env --profile remote up -d --build`.

## Verification

- `api` and `mcp` are healthy, and both cloudflared connectors are still up.
- `library.db` is migrated: `PRAGMA user_version` = 2, tables `firmware` and `firmware_rollbacks` are present, and `integrity_check` = `ok`.
- Data is intact: 4 library items, 3 devices (`x3-ori` id 3 still active, same `firmware_version`), 4 queue rows.
- `xteink firmware list` answers (no firmware yet).
- With no credentials: the device host gives `401` for `POST /api/device/status` and `GET /api/device/firmware/1`; the UI host gives `302` to Cloudflare Access; the LAN device port gives `401`.

## Rollback

Stop `api`/`mcp`, restore the tarball into the volume, and rebuild from `feat/issue-1`.

## Second redeploy, from `main` (2026-10-12T21:53Z)

Run with the owner's approval after xteink #5 and #6 merged, so the live server carries the stale-offer fix: a device that reports running its offered build has the offer withdrawn.

1. `api` and `mcp` were stopped, with the tunnels left up.
2. The `xteink_xteink-data` volume was backed up to `xteink/backups/server/20261012T215338Z-xteink-data.tgz` under the operator's XDG data home (20,082,057 B, sha256 prefix `1253b11156a8c47e`; contains `library.db` and `files/`). This lives outside the repo and is not committed.
3. The stack was rebuilt with the same command as above, from a clean worktree detached at `main` `d56e0d8`. The main checkout carries untracked leftovers that collide with files now on `main`, so it was not used.

Verification:

- `api` and `mcp` are healthy, and both cloudflared connectors are still up.
- `library.db`: `PRAGMA user_version` = 2 (no new migration), and `integrity_check` = `ok`.
- Data is intact: 5 library items, 3 devices and 5 firmware images. `x3-ori` (id 3) is active on `xteink-fw 1.6.5+xteink.2b3cbdea`.
- `xteink firmware list` and `xteink device list` answer. A dry-run `xteink firmware offer 5 --device 3` reports what it would do and changes nothing (the new shared dry-run path).
- With no credentials: `GET /api/device/firmware/5` gives `401` on the LAN device port and on the device host, `POST /api/device/status` gives `401`, and the UI host gives `302` to Cloudflare Access.
- **Pending:** device 3 still holds the fulfilled offer #5. The fixed server withdraws it on the X3's next status report (its next daily run). Check `offered_firmware` is null afterwards.

Rollback: stop `api`/`mcp`, restore `20261012T215338Z-xteink-data.tgz` into the volume, and rebuild from `c034c0b^` (`main` before #5).
