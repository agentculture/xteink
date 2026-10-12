import type { FullConfig } from "@playwright/test";

/** Fail early, with the fix, when the stack or the seeded key is missing. */
export default async function globalSetup(config: FullConfig) {
  const key = process.env.XTEINK_E2E_KEY;
  if (!key) {
    throw new Error(
      "XTEINK_E2E_KEY is not set. Seed a key on the throwaway stack and export it:\n" +
        "  export XTEINK_E2E_KEY=$(docker compose -p xteink-e2e run --rm api " +
        "python -m xteink.server create-key e2e)",
    );
  }
  const base = config.projects[0].use.baseURL ?? "http://127.0.0.1:18780";
  let res: Response;
  try {
    res = await fetch(`${base}/api/library?limit=1`, { headers: { Authorization: `Bearer ${key}` } });
  } catch (err) {
    throw new Error(`Cannot reach the xteink stack at ${base}: ${String(err)}. Is it up?`);
  }
  if (!res.ok) {
    throw new Error(`The stack at ${base} rejected XTEINK_E2E_KEY (HTTP ${res.status}).`);
  }
}
