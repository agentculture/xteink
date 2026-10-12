"""Fake-device sync against the live api container (run inside the internal network).

Uploads a Markdown file (pandoc converts it to EPUB server-side) and a TXT file, registers a
device, queues both, then runs tests/server/fake_device.FakeDevice's full protocol flow
(status -> queue -> download -> sha256 ack) against the device app. Exits non-zero on any
failure. Env: API_URL, DEVICE_URL, XTEINK_KEY.
"""

import os
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
    api.post(f"/api/devices/{dev['device']['id']}/queue", json={"item_id": item_id}).raise_for_status()

device_http = httpx.Client(base_url=os.environ["DEVICE_URL"], timeout=60)
result = FakeDevice(device_http, dev["key"]).sync()
assert result.delivered == ids, f"delivered {result.delivered}, expected {ids}"
print(f"fake device synced {len(result.delivered)} items over the internal network: OK")
