import { expect, test } from "@playwright/test";
import { bookCard, connect, deviceCard, deviceSync, goTo, pairReader, uniq, uploadText } from "./helpers";

test("send to device: queue from the library, simulated sync, UI shows delivered", async ({ page }) => {
  await connect(page, "#/readers");
  const reader = uniq("e2e-sender");
  const deviceKey = await pairReader(page, reader);
  expect(deviceKey).toMatch(/^xtd_/);
  await page.getByRole("button", { name: "I've saved it" }).click();

  const title = uniq("e2e-send");
  await uploadText(page, `${title}.txt`, `to the reader ${title}\n`);
  await goTo(page, "Library");
  const card = bookCard(page, new RegExp(title));
  await card.getByRole("button", { name: "Send to reader" }).click();
  await card.getByLabel("Reader").selectOption({ label: reader });
  await card.getByRole("button", { name: "Send", exact: true }).click();
  await expect(card.getByRole("status")).toContainText(`Sent to ${reader}`);

  // Queued, not yet delivered.
  await goTo(page, "Readers");
  const dev = deviceCard(page, reader);
  await expect(dev.locator(".delivery-queued")).toContainText(title);
  await expect(dev.locator(".delivery-queued")).toContainText("Waiting for next sync");

  // The reader syncs over the device protocol (a real fetch against the device app).
  const acked = await deviceSync(deviceKey);
  expect(acked.length).toBe(1);

  await page.reload();
  const after = deviceCard(page, reader);
  await expect(after.locator(".delivery-delivered")).toContainText(title);
  await expect(after.locator(".delivery-delivered")).toContainText("On the device since");
  await expect(after).toContainText("e2e-sim 0.0.1");
  await expect(after).toContainText("ok");
});
