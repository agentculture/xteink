import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  AuthRequiredError,
  NetworkError,
  createKey,
  deleteItem,
  listItems,
  probeSession,
  queueItem,
  registerDevice,
  uploadItem,
  verifyKey,
} from "./api";
import { clearStoredKey, storeKey } from "./storage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  storeKey("xtk_testkey123456");
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearStoredKey();
});

function lastCall(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(url), init: init ?? {} };
}

describe("auth header", () => {
  it("sends the stored API key as a bearer token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await listItems();
    const { init } = lastCall();
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer xtk_testkey123456");
  });

  it("sends no Authorization header when no key is stored", async () => {
    clearStoredKey();
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "invalid or missing key" }));
    await expect(listItems()).rejects.toBeInstanceOf(AuthRequiredError);
    expect(new Headers(lastCall().init.headers).has("Authorization")).toBe(false);
  });

  it("verifyKey uses the candidate key, not the stored one", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await expect(verifyKey("xtk_candidate")).resolves.toBe(true);
    const { url, init } = lastCall();
    expect(url).toBe("/api/library?limit=1");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer xtk_candidate");
  });

  it("verifyKey reports a rejected key as false", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "invalid or missing key" }));
    await expect(verifyKey("xtk_wrong")).resolves.toBe(false);
  });
});

describe("SSO session (Cloudflare Access)", () => {
  it("sends same-origin credentials and the CSRF header on every request", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { api_key: {}, key: "xtk_x" }));
    await createKey("phone");
    const { init } = lastCall();
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-Xteink-Request")).toBe("1");
  });

  it("probeSession asks whoami without a key, even when one is stored", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { via: "access", identity: "me@example.com" }));
    await expect(probeSession()).resolves.toEqual({ via: "access", identity: "me@example.com" });
    const { url, init } = lastCall();
    expect(url).toBe("/api/whoami");
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
    expect(init.credentials).toBe("same-origin");
  });

  it("probeSession resolves null on 401 (no SSO, e.g. on the LAN)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "invalid or missing key" }));
    await expect(probeSession()).resolves.toBeNull();
  });

  it("probeSession surfaces a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(probeSession()).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("query building", () => {
  it("passes search, kind and paging as query parameters", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await listItems({ q: "moby dick", kind: "book", limit: 20, offset: 40 });
    expect(lastCall().url).toBe("/api/library?q=moby+dick&kind=book&limit=20&offset=40");
  });

  it("omits empty search", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await listItems({ q: "  " });
    expect(lastCall().url).toBe("/api/library");
  });
});

describe("error mapping", () => {
  it.each([
    [413, "too_large"],
    [415, "unsupported_format"],
    [415, "pdf_not_supported"],
    [422, "bad_magic"],
    [422, "zip_bomb"],
    [422, "conversion_failed"],
    [503, "converter_missing"],
  ])("maps %i %s to an ApiError carrying the code", async (status, code) => {
    fetchMock.mockResolvedValue(jsonResponse(status, { detail: "server says no", code }));
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    const err = await uploadItem(file).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status, code, detail: "server says no" });
  });

  it("keeps a usable detail for FastAPI validation errors (array detail)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, { detail: [{ loc: ["body", "name"], msg: "Field required" }] }),
    );
    const err = await registerDevice("", false).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("validation");
    expect((err as ApiError).detail).toContain("Field required");
  });

  it("falls back to a generic message for a non-JSON error body", async () => {
    fetchMock.mockResolvedValue(new Response("Internal Server Error", { status: 500 }));
    const err = await listItems().catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 500, code: "http_500" });
  });

  it("maps 404 to code not_found", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: "item 9 not found" }));
    const err = await deleteItem(9).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 404, code: "not_found", detail: "item 9 not found" });
  });

  it("turns a failed fetch into a NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(listItems()).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("requests", () => {
  it("uploads multipart form data with optional metadata", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, { item: { id: 1, title: "A" }, created: true }),
    );
    const file = new File(["hello"], "a.txt", { type: "text/plain" });
    const res = await uploadItem(file, { title: "A", author: "", kind: "article" });
    expect(res.created).toBe(true);
    const { url, init } = lastCall();
    expect(url).toBe("/api/library");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body.get("file")).toBeInstanceOf(File);
    expect(body.get("title")).toBe("A");
    expect(body.get("kind")).toBe("article");
    expect(body.has("author")).toBe(false);
    // The browser must set the multipart boundary itself.
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("treats a 200 upload as a duplicate", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { item: { id: 1 }, created: false }));
    const res = await uploadItem(new File(["x"], "a.txt"));
    expect(res.created).toBe(false);
  });

  it("returns undefined for 204 responses", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteItem(3)).resolves.toBeUndefined();
    expect(lastCall()).toMatchObject({ url: "/api/library/3", init: { method: "DELETE" } });
  });

  it("posts JSON for device registration, queueing and key creation", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { device: { id: 2 }, key: "xtd_raw" }));
    await registerDevice("Kitchen", true);
    let call = lastCall();
    expect(call.url).toBe("/api/devices");
    expect(JSON.parse(call.init.body as string)).toEqual({ name: "Kitchen", mirror: true });
    expect(new Headers(call.init.headers).get("Content-Type")).toBe("application/json");

    fetchMock.mockResolvedValue(jsonResponse(201, { id: 1, state: "queued" }));
    await queueItem(2, 7);
    call = lastCall();
    expect(call.url).toBe("/api/devices/2/queue");
    expect(JSON.parse(call.init.body as string)).toEqual({ item_id: 7 });

    fetchMock.mockResolvedValue(jsonResponse(201, { api_key: { id: 3 }, key: "xtk_raw" }));
    await createKey("laptop");
    call = lastCall();
    expect(call.url).toBe("/api/keys");
    expect(JSON.parse(call.init.body as string)).toEqual({ name: "laptop" });
  });
});
