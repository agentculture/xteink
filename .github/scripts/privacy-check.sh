#!/usr/bin/env bash
# Privacy gate: prove the xteink stack makes zero outbound connections.
#
# 1. Build the server image.
# 2. Start the api on a docker network created `internal: true` (no gateway, no NAT).
# 3. Negative control: a container on that network must NOT be able to reach the internet.
# 4. Run the core/server/mcp test suites from a throwaway container on that same network.
#    Any skip fails the gate, so the real-pandoc test (pandoc runs with --sandbox) and the
#    fastapi/mcp suites must really run.
# 5. Drive a fake-device sync (upload -> queue -> download -> ack) against the api.
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

echo "== negative control: the internal network has no route to the internet"
if "${DC[@]}" --profile tools run --rm tester python - <<'PY'
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
then
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
"${DC[@]}" --profile tools run --rm -e XTEINK_KEY="$KEY" tester python .github/scripts/privacy-sync.py

echo "PRIVACY OK: tests + device sync passed on an internal-only network with 0 outbound connections"
