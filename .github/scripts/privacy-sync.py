"""Fake-device sync against the live api container (run inside the internal network).

Uploads a Markdown file (pandoc converts it to EPUB server-side) and a TXT file, registers a
device, queues both, then runs tests/server/fake_device.FakeDevice's full protocol flow
(status -> queue -> download -> sha256 ack) against the device app. Exits non-zero on any
failure. Env: API_URL, DEVICE_URL, XTEINK_KEY.

Then runs the OTA leg: a synthetic valid X3 image is uploaded and offered through the real
``xteink firmware`` CLI, a second (new-client) fake device fetches the offer from the status
response, downloads the image and verifies its sha256, then reports ``fw_outcome=installed``.
The leg prints ``OTA LEG OK``, which privacy-check.sh requires; a skipped leg fails the gate.
"""

import hashlib
import json
import os
import subprocess  # nosec B404
import sys

import httpx

sys.path.insert(0, "/work")
from tests.server.fake_device import FakeDevice  # noqa: E402

api = httpx.Client(
    base_url=os.environ["API_URL"],
    headers={"Authorization": f"Bearer {os.environ['XTEINK_KEY']}"},
    timeout=60,
)

ids = []
for name, body in [
    ("note.md", b"# Privacy\n\nA short *markdown* article for the offline sync check.\n"),
    ("plain.txt", b"just some text\n"),
]:
    r = api.post("/api/library", files={"file": (name, body)})
    r.raise_for_status()
    item = r.json()["item"]
    print(f"uploaded {name} -> item {item['id']} ({item['format']})")
    ids.append(item["id"])

r = api.post("/api/devices", json={"name": "privacy-reader"})
r.raise_for_status()
dev = r.json()
for item_id in ids:
    api.post(
        f"/api/devices/{dev['device']['id']}/queue", json={"item_id": item_id}
    ).raise_for_status()

device_http = httpx.Client(base_url=os.environ["DEVICE_URL"], timeout=60)
result = FakeDevice(device_http, dev["key"]).sync()
assert result.delivered == ids, f"delivered {result.delivered}, expected {ids}"
print(f"fake device synced {len(result.delivered)} items over the internal network: OK")

# -- OTA leg: upload -> offer (CLI) -> fake device fetches, verifies sha256, reports installed --
IMAGE = "/work/tests/fixtures/fw/valid_x3.bin"
with open(IMAGE, "rb") as fh:
    image_bytes = fh.read()
image_sha = hashlib.sha256(image_bytes).hexdigest()


def cli(*argv: str) -> dict:
    """Run the real ``xteink`` CLI against the api (env: XTEINK_URL / XTEINK_API_KEY)."""
    env = dict(
        os.environ, XTEINK_URL=os.environ["API_URL"], XTEINK_API_KEY=os.environ["XTEINK_KEY"]
    )
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-m", "xteink", *argv, "--json"],
        cwd="/work",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"xteink {' '.join(argv)} failed: {proc.stdout}{proc.stderr}"
    return json.loads(proc.stdout)


up = cli(
    "firmware",
    "upload",
    IMAGE,
    "--commit",
    "0" * 40,
    "--pr",
    "http://localhost/privacy-check",
    "--apply",
)
fw = up["firmware"]
assert fw["sha256"] == image_sha, "stored firmware sha256 differs from the fixture"
print(f"uploaded firmware {fw['id']} ({fw['version']}, {fw['size']} bytes)")

r = api.post("/api/devices", json={"name": "privacy-ota-reader"})
r.raise_for_status()
ota_dev = r.json()
ota_id = ota_dev["device"]["id"]
off = cli("firmware", "offer", str(fw["id"]), "--device", str(ota_id), "--apply")
assert off["offered"], f"offer reached no device: {off}"

ota = FakeDevice(
    httpx.Client(base_url=os.environ["DEVICE_URL"], timeout=60),
    ota_dev["key"],
    firmware_version="xteink-fw 0.0.0-privacy",
    new_client=True,
)
result = ota.sync()
assert result.firmware_offer is not None, "status response carried no firmware offer"
assert result.firmware_offer["id"] == fw["id"], result.firmware_offer
assert ota.firmware_image == image_bytes, "downloaded image differs from the uploaded one"
assert hashlib.sha256(ota.firmware_image).hexdigest() == result.firmware_offer["sha256"]
ota.firmware_version = result.firmware_offer["version"]
ota.fw_outcome = "installed"
ota.post_status().raise_for_status()
seen = api.get(f"/api/devices/{ota_id}")
seen.raise_for_status()
assert seen.json().get("last_fw_outcome") == "installed", f"fw_outcome not recorded: {seen.json()}"
print(f"OTA fake device fetched + sha256-verified firmware {fw['id']}, reported installed")
print("OTA LEG OK")
