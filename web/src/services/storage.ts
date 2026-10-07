/**
 * Where this browser keeps its xteink API key.
 *
 * Every /api route needs a key, even on the LAN, so the browser holds one in
 * localStorage. Storage can be unavailable or throw (private windows, blocked
 * site data), so every access is wrapped and a failure reads as "no key".
 */

const STORAGE_KEY = "xteink.apiKey";

export function getStoredKey(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? value : null;
  } catch {
    return null;
  }
}

export function storeKey(key: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, key.trim());
  } catch {
    // Best effort: without storage the browser asks again on the next visit.
  }
}

export function clearStoredKey(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored that we could reach.
  }
}

/** The public key id inside a raw key (`xtk_<key_id>_<secret>`), if it has one. */
export function keyIdOf(key: string): string | null {
  const parts = key.split("_");
  return parts.length >= 3 && parts[1] ? parts[1] : null;
}

/** A key as the UI may show it: its type and public id, never the secret part. */
export function keyPrefix(key: string): string {
  const id = keyIdOf(key);
  if (id) return `${key.split("_")[0]}_${id}…`;
  return `${key.slice(0, 4)}…`;
}
