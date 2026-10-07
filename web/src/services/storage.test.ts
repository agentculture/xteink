import { afterEach, describe, expect, it, vi } from "vitest";
import { clearStoredKey, getStoredKey, keyIdOf, keyPrefix, storeKey } from "./storage";

afterEach(() => {
  vi.restoreAllMocks();
  clearStoredKey();
});

describe("key storage", () => {
  it("round-trips a key and trims whitespace", () => {
    storeKey("  xtk_abc  ");
    expect(getStoredKey()).toBe("xtk_abc");
    clearStoredKey();
    expect(getStoredKey()).toBeNull();
  });

  it("treats throwing storage as no key and never throws itself", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(() => storeKey("xtk_abc")).not.toThrow();
    expect(getStoredKey()).toBeNull();
    expect(() => clearStoredKey()).not.toThrow();
  });
});

describe("keyPrefix", () => {
  it("shows only a short prefix, never the whole key", () => {
    const shown = keyPrefix("xtk_ab12cd34_SECRETPARTxyz");
    expect(shown).toBe("xtk_ab12cd34…");
    expect(shown).not.toContain("SECRET");
    expect(keyPrefix("weirdkeywithoutparts")).toBe("weir…");
  });
});

describe("keyIdOf", () => {
  it("extracts the public id", () => {
    expect(keyIdOf("xtk_ab12cd34_secret_with_underscores")).toBe("ab12cd34");
    expect(keyIdOf("nounderscores")).toBeNull();
  });
});
