import { expect, test } from "@playwright/test";
import { connect, deviceCard, deviceSync, pairReader, uniq, DEVICE_URL } from "./helpers";

test("devices: pair, one-time key, mirror, rotate, revoke", async ({ page }) => {
  await connect(page, "#/readers");

  // A blank name is refused before anything is sent.
  await page.getByRole("button", { name: "Pair device" }).click();
  await expect(page.getByRole("alert")).toContainText("Give the reader a name");

  const reader = uniq("e2e-bedside");
  const key = await pairReader(page, reader);
  expect(key).toMatch(/^xtd_/);
  await expect(page.getByRole("img", { name: `QR code of the key for ${reader}` })).toBeVisible();
  await page.getByRole("button", { name: "I've saved it" }).click();
  // The raw key is gone from the page afterwards.
  await expect(page.getByText(key)).toHaveCount(0);

  const card = deviceCard(page, reader);
  await expect(card).toContainText("Not yet; enter the key on the reader");
  const mirror = card.getByLabel("Mirror the library");
  await expect(mirror).not.toBeChecked();
  await mirror.click(); // controlled input: it flips once the server confirms
  await expect(mirror).toBeChecked();
  await page.reload();
  await expect(deviceCard(page, reader).getByLabel("Mirror the library")).toBeChecked();

  // The key works against the device app, and "last seen" appears after a sync.
  await deviceSync(key);
  await page.reload();
  await expect(deviceCard(page, reader)).not.toContainText("Not yet; enter the key");
  await expect(deviceCard(page, reader)).toContainText("e2e-sim 0.0.1");

  // Rotating issues a new key and the old one stops working.
  await deviceCard(page, reader).getByRole("button", { name: "Rotate key" }).click();
  const reveal = page.getByRole("region", { name: `Key for ${reader}` });
  const newKey = (await reveal.locator("code.key-text").innerText()).trim();
  expect(newKey).not.toBe(key);
  await page.getByRole("button", { name: "I've saved it" }).click();
  const probe = (k: string) =>
    fetch(`${DEVICE_URL}/api/device/whoami`, { headers: { Authorization: `Bearer ${k}`, "X-Xteink-Protocol": "1" } });
  expect((await probe(key)).status).toBe(401);
  expect((await probe(newKey)).status).toBe(200);

  // Revoking asks first, then the key stops working.
  const c2 = deviceCard(page, reader);
  await c2.getByRole("button", { name: "Revoke key" }).click();
  await c2.getByRole("button", { name: `Revoke ${reader}'s key` }).click();
  await expect(deviceCard(page, reader).getByText("Key revoked")).toBeVisible();
  expect((await probe(newKey)).status).toBe(401);
  await expect(deviceCard(page, reader).getByRole("button", { name: "Issue a new key" })).toBeVisible();
});
