import { expect, test } from "@playwright/test";
import { bookCard, connect, goTo, uniq, uploadText } from "./helpers";

test("library: search, kind filter, download, delete", async ({ page }) => {
  await connect(page, "#/add");
  const a = uniq("e2e-alpha");
  const b = uniq("e2e-bravo");
  await uploadText(page, `${a}.txt`, `body ${a}\n`);
  await uploadText(page, `${b}.md`, `# ${b}\n\nbody ${b}\n`, "text/markdown");
  await goTo(page, "Library");
  await expect(bookCard(page, new RegExp(a))).toBeVisible();
  await expect(bookCard(page, new RegExp(b))).toBeVisible();

  // Search narrows the shelf.
  await page.getByRole("searchbox").fill(a);
  await expect(bookCard(page, new RegExp(b))).toHaveCount(0);
  await expect(bookCard(page, new RegExp(a))).toBeVisible();
  await page.getByRole("searchbox").fill("zzz-no-such-title-zzz");
  await expect(page.getByText("Nothing matches")).toBeVisible();
  await page.getByRole("searchbox").fill("");

  // Kind filter: the markdown upload is an article, the text file a book.
  await page.getByRole("radiogroup", { name: "Show" }).getByText("Articles", { exact: true }).click();
  await expect(bookCard(page, new RegExp(b))).toBeVisible();
  await expect(bookCard(page, new RegExp(a))).toHaveCount(0);
  await page.getByRole("radiogroup", { name: "Show" }).getByText("Books", { exact: true }).click();
  await expect(bookCard(page, new RegExp(a))).toBeVisible();
  await expect(bookCard(page, new RegExp(b))).toHaveCount(0);
  await page.getByRole("radiogroup", { name: "Show" }).getByText("All", { exact: true }).click();

  // Download returns the stored bytes.
  const card = bookCard(page, new RegExp(a));
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    card.getByRole("button", { name: "Download" }).click(),
  ]);
  const { readFile } = await import("node:fs/promises");
  expect((await readFile((await download.path())!)).toString()).toContain(`body ${a}`);

  // Delete asks first, and Keep leaves it.
  await card.getByRole("button", { name: "Delete", exact: true }).click();
  await card.getByRole("button", { name: "Keep" }).click();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Delete", exact: true }).click();
  await card.getByRole("button", { name: /^Delete “/ }).click();
  await expect(bookCard(page, new RegExp(a))).toHaveCount(0);
  await page.reload();
  await expect(bookCard(page, new RegExp(b))).toBeVisible();
  await expect(bookCard(page, new RegExp(a))).toHaveCount(0);
});
