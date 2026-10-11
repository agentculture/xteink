#!/usr/bin/env bash
# Privacy gate: prove the xteink stack makes zero outbound connections.
#
# 1. Build the server image.
# 2. Start the api on a docker network created `internal: true` (no gateway, no NAT).
# 3. Negative control: a container on that network must NOT be able to reach the internet.
# 4. Run the core/server/mcp test suites from a throwaway container on that same network.
#    Any skip fails the gate, so the real-pandoc test (pandoc runs with --sandbox) and the
#    fastapi/mcp suites must really run.
# 5. Drive a fake-device sync (upload -> queue -> download -> ack) against the api, then the
#    OTA leg (firmware upload + offer via the CLI, device fetch + sha256 verify, fw_outcome=
#    installed). The OTA leg is mandatory: its "OTA LEG OK" marker must be in the output.
# 6. Re-prove after the OTA leg that the network is still air-gapped and that the api made no
#    connection outside it, and that no firmware code path uses an outbound HTTP client.
#
# Local use (throwaway names; never touches the production `xteink` project):
#   COMPOSE_PROJECT_NAME=xteink-ci-t10 XTEINK_IMAGE=xteink-ci-t10:local \
#     .github/scripts/privacy-check.sh
# Set KEEP=1 to leave the stack up for inspection.
set -euo pipefail

cd "$(dirname "$0")/../.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-xteink-privacy}"
export XTEINK_IMAGE="${XTEINK_IMAGE:-xteink-privacy:local}"
PRIVACY_DEPS_DIR="$(mktemp -d)"
export PRIVACY_DEPS_DIR
DC=(docker compose -f .github/compose.privacy.yaml)

cleanup() {
  rm -rf "$PRIVACY_DEPS_DIR"
  if [ "${KEEP:-0}" != "1" ]; then
    "${DC[@]}" --profile tools down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "== build image ($XTEINK_IMAGE)"
"${DC[@]}" build api

echo "== install pytest into a host dir via a plain container (default network; stack not up)"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PRIVACY_DEPS_DIR:/deps" \
  "$XTEINK_IMAGE" pip install --quiet --no-cache-dir --target /deps pytest

echo "== start api on the internal network"
"${DC[@]}" up -d api
for _ in $(seq 1 30); do
  if "${DC[@]}" --profile tools run --rm tester python - <<'PY' 2>/dev/null; then
import urllib.error, urllib.request
try:
    urllib.request.urlopen("http://api:8780/", timeout=2)
except urllib.error.HTTPError:
    pass
PY
    break
  fi
  sleep 1
done

no_route_check() {
  "${DC[@]}" --profile tools run --rm tester python - <<'PY'
import socket, sys
for host in ("1.1.1.1", "8.8.8.8"):
    try:
        socket.create_connection((host, 443), timeout=3).close()
    except OSError:
        continue
    print(f"reached {host}: network is NOT air-gapped", file=sys.stderr)
    sys.exit(1)
try:
    socket.getaddrinfo("github.com", 443)
except OSError:
    sys.exit(0)
print("resolved github.com: network is NOT air-gapped", file=sys.stderr)
sys.exit(1)
PY
}

echo "== negative control: the internal network has no route to the internet"
if no_route_check; then
  echo "control ok: no outbound route"
else
  echo "FAIL: internal network is not isolated" >&2
  exit 1
fi

echo "== core + server + mcp tests inside the internal network (no skips allowed)"
OUT="$(mktemp)"
set +e
"${DC[@]}" --profile tools run --rm tester \
  python -m pytest tests/core tests/server tests/mcp -q -rs -p no:cacheprovider \
  -o addopts="" 2>&1 | tee "$OUT"
rc=${PIPESTATUS[0]}
set -e
[ "$rc" -eq 0 ] || { echo "FAIL: tests failed (rc=$rc)" >&2; exit 1; }
if grep -Eq "SKIPPED|skipped" "$OUT"; then
  echo "FAIL: some tests were skipped (real pandoc / fastapi / mcp must run)" >&2
  exit 1
fi
"${DC[@]}" --profile tools run --rm tester \
  python -m pytest tests/core/test_ingest.py::test_real_pandoc -q -p no:cacheprovider -o addopts=""

echo "== fake-device sync against the api"
KEY="$("${DC[@]}" exec -T api python -m xteink.server create-key privacy-ci 2>/dev/null)"
SYNC_OUT="$(mktemp)"
"${DC[@]}" --profile tools run --rm -e XTEINK_KEY="$KEY" tester \
  python .github/scripts/privacy-sync.py 2>&1 | tee "$SYNC_OUT"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "FAIL: fake-device sync failed" >&2; exit 1; }
if ! grep -qx "OTA LEG OK" "$SYNC_OUT"; then
  echo "FAIL: the OTA leg did not run to completion (no 'OTA LEG OK' marker)" >&2
  exit 1
fi
rm -f "$SYNC_OUT"

echo "== after the OTA leg: still air-gapped, and the api made no outbound connection"
if ! no_route_check; then
  echo "FAIL: internal network is not isolated after the OTA leg" >&2
  exit 1
fi
# Snapshot the api container's sockets: every remote peer must be loopback or on the airgap
# subnet (the only network it is attached to). The no-route control above is the hard proof;
# this catches a live connection to anything else.
SUBNET="$(docker network inspect "${COMPOSE_PROJECT_NAME}_airgap" \
  --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}')"
"${DC[@]}" exec -T -e SUBNETS="$SUBNET" api python - <<'PY'
import ipaddress, os, socket, struct, sys

nets = [ipaddress.ip_network(n) for n in os.environ["SUBNETS"].split()]
bad = []
for path, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
    try:
        lines = open(path).read().splitlines()[1:]
    except OSError:
        continue
    for line in lines:
        f = line.split()
        raw, _, port = f[2].partition(":")
        if f[3] == "0A" or int(raw, 16) == 0:  # LISTEN / unconnected
            continue
        if v6:
            b = bytes.fromhex(raw)
            b = b"".join(struct.pack("<I", struct.unpack(">I", b[i : i + 4])[0]) for i in range(0, 16, 4))
            ip = ipaddress.IPv6Address(b)
            ip = ip.ipv4_mapped or ip
        else:
            ip = ipaddress.IPv4Address(socket.ntohl(int(raw, 16)))
        if ip.is_loopback or any(ip in n for n in nets if n.version == ip.version):
            continue
        bad.append(f"{ip}:{int(port, 16)}")
if bad:
    print("api has connections outside the airgap network: " + ", ".join(bad), file=sys.stderr)
    sys.exit(1)
print("api sockets: all peers are loopback or on the internal network")
PY

echo "== no outbound HTTP client is used for firmware"
# access.py's urllib.request fetches the Cloudflare Access JWKS (operator auth, opt-in); it is
# the only HTTP-client use under core/server; firmware code (core/firmware.py, fwimage.py,
# routes_device.py, routes_admin.py) has none.
CLIENTS="$(grep -rlE "^\s*(import|from)\s+(httpx|requests|aiohttp|urllib\.request|http\.client)" \
  xteink/core xteink/server || true)"
if [ "$CLIENTS" != "xteink/server/access.py" ]; then
  echo "FAIL: unexpected HTTP-client use under xteink/core or xteink/server:" >&2
  echo "$CLIENTS" >&2
  exit 1
fi
echo "ok: only xteink/server/access.py (JWKS) uses an HTTP client; firmware paths do not"

echo "PRIVACY OK: tests + device sync + OTA leg passed on an internal-only network with 0 outbound connections"
