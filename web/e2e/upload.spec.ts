import { expect, test } from "@playwright/test";
import { API_KEY, bookCard, goTo, uniq, uploadText } from "./helpers";

test("upload: first-run connect, text file, markdown converted by pandoc, duplicate", async ({ page }) => {
  // First run: no stored key, so the connect panel shows and rejects a bad key.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Connect this browser/ })).toBeVisible();
  await page.getByLabel("API key").fill("xtk_nope_notakey");
  await page.getByRole("button", { name: "Connect this browser" }).click();
  await expect(page.getByRole("alert")).toContainText("didn't accept that key");
  await page.getByLabel("API key").fill(API_KEY);
  await page.getByRole("button", { name: "Connect this browser" }).click();
  await expect(page.getByRole("heading", { name: "Library", level: 1 })).toBeVisible();

  // Plain text is stored as-is (a book).
  const txtName = uniq("e2e-plain");
  const row = await uploadText(page, `${txtName}.txt`, `A short text ${txtName}.\nSecond line.\n`);
  await expect(row.locator(".upload-status")).toContainText("Added as");

  // Markdown goes through the server's real pandoc and becomes an EPUB article.
  const mdName = uniq("e2e-article");
  const md = `# ${mdName}\n\nSome *markdown* with a [link](https://example.com).\n\n## Part two\n\nMore words.\n`;
  const mdRow = await uploadText(page, `${mdName}.md`, md, "text/markdown");
  await expect(mdRow.locator(".upload-status")).toContainText("Added as");
  await goTo(page, "Library");
  const card = bookCard(page, new RegExp(mdName));
  await expect(card).toContainText("Article");
  await expect(card).toContainText("EPUB");

  // The same bytes again are recognised.
  const dup = await uploadText(page, `${txtName}-again.txt`, `A short text ${txtName}.\nSecond line.\n`);
  await expect(dup.locator(".upload-status")).toContainText("Already in your library");
});
