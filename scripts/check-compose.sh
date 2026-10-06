#!/usr/bin/env bash
# Validate compose.yaml: cloudflared only under --profile remote; restart policies and
# healthchecks present. Needs docker compose and python3. No containers are started.
set -euo pipefail
cd "$(dirname "$0")/.."

# Do not depend on a local .env or exported secrets: the stack must resolve with NO
# variables set, so `docker compose up -d` and the create-key bootstrap work on a fresh
# clone (compose interpolates every service, including inactive-profile ones).
unset XTEINK_API_KEY TUNNEL_TOKEN_UI TUNNEL_TOKEN_DEVICE
DC=(docker compose --env-file /dev/null)

base="$("${DC[@]}" config --services)"
remote="$("${DC[@]}" --profile remote config --services)"

for c in cloudflared-ui cloudflared-device; do
  if grep -qx "$c" <<<"$base"; then
    echo "FAIL: $c listed without --profile remote" >&2
    exit 1
  fi
  if ! grep -qx "$c" <<<"$remote"; then
    echo "FAIL: $c missing with --profile remote" >&2
    exit 1
  fi
done
for s in api mcp; do
  grep -qx "$s" <<<"$base" || { echo "FAIL: service $s missing" >&2; exit 1; }
done

"${DC[@]}" --profile remote config --format json | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
bad = []
for name, svc in cfg["services"].items():
    if svc.get("restart") != "unless-stopped":
        bad.append(f"{name}: restart != unless-stopped")
    if not svc.get("healthcheck", {}).get("test"):
        bad.append(f"{name}: no healthcheck")
for c in ("cloudflared-ui", "cloudflared-device"):
    if cfg["services"][c].get("profiles") != ["remote"]:
        bad.append(f"{c}: profiles != [remote]")
if bad:
    print("FAIL: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)
'
echo "OK: compose config valid (cloudflared-ui and cloudflared-device only under --profile remote)"
