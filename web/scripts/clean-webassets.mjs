// Empty xteink/server/_webassets before a build, keeping the two tracked
// files (.gitignore, README.md). Vite's emptyOutDir would delete them too.
import { readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../../xteink/server/_webassets/", import.meta.url));
const keep = new Set([".gitignore", "README.md"]);
for (const name of readdirSync(out)) {
  if (!keep.has(name)) rmSync(join(out, name), { recursive: true, force: true });
}
