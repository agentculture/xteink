#!/usr/bin/env bash
# Validate compose.yaml: cloudflared only under --profile remote; restart policies and
# healthchecks present. Needs docker compose and python3. No containers are started.
set -euo pipefail
cd "$(dirname "$0")/.."

# Do not depend on a local .env: supply placeholders for required variables.
export XTEINK_API_KEY="${XTEINK_API_KEY:-<check>}"
export TUNNEL_TOKEN="${TUNNEL_TOKEN:-<check>}"
DC=(docker compose --env-file /dev/null)

base="$("${DC[@]}" config --services)"
remote="$("${DC[@]}" --profile remote config --services)"

if grep -qx cloudflared <<<"$base"; then
  echo "FAIL: cloudflared listed without --profile remote" >&2
  exit 1
fi
if ! grep -qx cloudflared <<<"$remote"; then
  echo "FAIL: cloudflared missing with --profile remote" >&2
  exit 1
fi
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
if cfg["services"]["cloudflared"].get("profiles") != ["remote"]:
    bad.append("cloudflared: profiles != [remote]")
if bad:
    print("FAIL: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)
'
echo "OK: compose config valid (cloudflared only under --profile remote)"
