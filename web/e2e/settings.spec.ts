import { expect, test } from "@playwright/test";
import { API_KEY, connect, uniq } from "./helpers";

test("settings: this browser, remote access, create and revoke an API key, forget key", async ({ page }) => {
  await connect(page, "#/settings");
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();

  // This browser shows only the key's prefix, never the secret.
  const stored = page.getByRole("region", { name: "This browser" });
  await expect(stored).toContainText("xtk_");
  const secret = API_KEY.split("_").slice(2).join("_");
  await expect(page.locator("body")).not.toContainText(secret);

  // Remote access is configuration, and we are on the LAN.
  const remote = page.getByRole("region", { name: "Remote access" });
  await expect(remote).toContainText("ebooks.culture.dev");
  await expect(remote).toContainText("xteink.culture.dev");
  await expect(remote).toContainText("your local network");

  // Create a key: shown once, listed, and it works.
  const name = uniq("e2e-key");
  await page.getByLabel("New key name").fill(name);
  await page.getByRole("button", { name: "Create key" }).click();
  const reveal = page.getByRole("region", { name: `Key for ${name}` });
  const newKey = (await reveal.locator("code.key-text").innerText()).trim();
  expect(newKey).toMatch(/^xtk_/);
  await page.getByRole("button", { name: "I've saved it" }).click();
  const keys = page.getByRole("region", { name: "API keys" });
  const row = keys.getByRole("listitem").filter({ hasText: name });
  await expect(row).toBeVisible();
  const call = (k: string) =>
    page.request.get("/api/library?limit=1", { headers: { Authorization: `Bearer ${k}` } });
  expect((await call(newKey)).status()).toBe(200);

  // Revoke it: it stops working, the seeded key is untouched.
  await row.getByRole("button", { name: "Revoke", exact: true }).click();
  await row.getByRole("button", { name: new RegExp(`^Revoke “${name}”`) }).click();
  await expect(row.getByText("Revoked", { exact: true })).toBeVisible();
  expect((await call(newKey)).status()).toBe(401);
  expect((await call(API_KEY)).status()).toBe(200);

  // Forget this key: back to the connect panel, storage cleared, and the key is gone from storage.
  await stored.getByRole("button", { name: "Forget this key" }).click();
  await stored.getByRole("button", { name: "Forget key" }).click();
  await expect(page.getByRole("heading", { name: /Connect this browser/ })).toBeVisible();
  // (connect() re-seeds storage on every navigation, so check storage itself rather than reloading.)
  expect(await page.evaluate(() => window.localStorage.getItem("xteink.apiKey"))).toBeNull();
});
