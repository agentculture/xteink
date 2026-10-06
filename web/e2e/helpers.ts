import { expect, type Locator, type Page } from "@playwright/test";

export const API_KEY = process.env.XTEINK_E2E_KEY ?? "";
export const DEVICE_URL = process.env.XTEINK_E2E_DEVICE_URL ?? "http://127.0.0.1:18781";

/** A short token that is unique per run, so reruns never collide on duplicate hashes or names. */
export function uniq(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
}

/** Skip the connect panel by putting the seeded key in this browser's storage. */
export async function connect(page: Page, hash = "#/library") {
  await page.addInitScript((key) => window.localStorage.setItem("xteink.apiKey", key), API_KEY);
  await page.goto(`/${hash}`);
}

export async function goTo(page: Page, name: "Library" | "Add books" | "Readers" | "Settings") {
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name }).click();
}

/** Add a file through the Add view and wait for the server's verdict. */
export async function uploadText(page: Page, name: string, body: string, mime = "text/plain") {
  await goTo(page, "Add books");
  await page.locator('input[type="file"]').setInputFiles({ name, mimeType: mime, buffer: Buffer.from(body) });
  const row = page.getByRole("list", { name: "Files added in this visit" }).getByRole("listitem").filter({ hasText: name });
  await expect(row.locator(".upload-status")).toContainText(/Added as|Already in your library/, { timeout: 30_000 });
  return row;
}

export function bookCard(page: Page, title: string | RegExp): Locator {
  return page.getByRole("article").filter({ has: page.getByRole("heading", { name: title }) });
}

/** Pair a reader in the Readers view; returns the one-time device key shown in the reveal. */
export async function pairReader(page: Page, name: string, mirror = false): Promise<string> {
  await goTo(page, "Readers");
  await page.getByLabel("Device name").fill(name);
  if (mirror) await page.getByLabel(/Mirror the library/).first().check();
  await page.getByRole("button", { name: "Pair device" }).click();
  const reveal = page.getByRole("region", { name: `Key for ${name}` });
  await expect(reveal).toBeVisible();
  return (await reveal.locator("code.key-text").innerText()).trim();
}

export function deviceCard(page: Page, name: string): Locator {
  return page.getByRole("article").filter({ has: page.getByRole("heading", { name, level: 3 }) });
}

/** One simulated reader sync over the device protocol; returns the ids it acked. */
export async function deviceSync(deviceKey: string): Promise<number[]> {
  const headers = { Authorization: `Bearer ${deviceKey}`, "X-Xteink-Protocol": "1" };
  const json = { ...headers, "Content-Type": "application/json" };
  const ok = async (res: Response) => {
    if (!res.ok) throw new Error(`${res.url} -> ${res.status} ${await res.text()}`);
    return res;
  };
  await ok(
    await fetch(`${DEVICE_URL}/api/device/status`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({ free_sd_bytes: 500_000_000, firmware_version: "e2e-sim 0.0.1" }),
    }),
  );
  const queue = (await (await ok(await fetch(`${DEVICE_URL}/api/device/queue`, { headers }))).json()) as {
    items: { id: number; sha256: string; url: string }[];
  };
  const acked: number[] = [];
  const { createHash } = await import("node:crypto");
  for (const item of queue.items) {
    const bytes = Buffer.from(await (await ok(await fetch(`${DEVICE_URL}${item.url}`, { headers }))).arrayBuffer());
    const sha256 = createHash("sha256").update(bytes).digest("hex");
    await ok(
      await fetch(`${DEVICE_URL}/api/device/ack`, {
        method: "POST",
        headers: json,
        body: JSON.stringify({ item_id: item.id, sha256 }),
      }),
    );
    acked.push(item.id);
  }
  await ok(
    await fetch(`${DEVICE_URL}/api/device/status`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({ free_sd_bytes: 499_000_000, firmware_version: "e2e-sim 0.0.1", last_sync_result: "ok" }),
    }),
  );
  return acked;
}
