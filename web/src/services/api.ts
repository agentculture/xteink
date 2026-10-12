/**
 * The only module that talks to the xteink HTTP API.
 *
 * Components call these functions and present what comes back. A request
 * carries `Authorization: Bearer <API key>` when this browser stores one.
 * Without a key it still sends the browser's same-origin cookies: behind
 * Cloudflare Access (ebooks.culture.dev) the edge turns the SSO session into a
 * signed `Cf-Access-Jwt-Assertion` header that the server verifies, so no key
 * is needed there. Every request also sends `X-Xteink-Request: 1`, which the
 * server requires on SSO-authenticated writes (CSRF guard). Errors become:
 * - AuthRequiredError on 401 (the app shows the connect panel again),
 * - ApiError with a machine-readable `code` (the server's ingest code when it
 *   sends one, otherwise derived from the status),
 * - NetworkError when the server can't be reached.
 *
 * Response shapes mirror xteink/core/models.py.
 */

import { getStoredKey } from "./storage";

export type Kind = "book" | "article";

export type Item = {
  id: number;
  sha256: string;
  kind: Kind;
  title: string;
  author: string;
  format: string;
  size: number;
  created_at: string;
};

export type Device = {
  id: number;
  name: string;
  key_id: string;
  mirror: boolean;
  created_at: string;
  revoked_at: string | null;
  last_seen: string | null;
  last_sync_result: string | null;
  free_sd_bytes: number | null;
  firmware_version: string | null;
  last_error: string | null;
};

export type QueueEntry = {
  id: number;
  device_id: number;
  item_id: number;
  title: string;
  size: number;
  sha256?: string;
  state: "queued" | "delivered";
  queued_at: string;
  delivered_at: string | null;
};

export type ApiKey = {
  id: number;
  name: string;
  key_id: string;
  created_at: string;
  revoked_at: string | null;
  last_used: string | null;
};

/** How the server authenticated this browser (`GET /api/whoami`). */
export type Whoami = { via: "access" | "key"; identity: string };

export class AuthRequiredError extends Error {
  constructor() {
    super("This browser's API key is missing or no longer valid.");
    this.name = "AuthRequiredError";
  }
}

export class NetworkError extends Error {
  constructor() {
    super("The xteink server can't be reached.");
    this.name = "NetworkError";
  }
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;

  constructor(status: number, code: string, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

type ErrorBody = { detail?: unknown; code?: unknown };

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "";
}

function codeFor(status: number, body: ErrorBody): string {
  if (typeof body.code === "string" && body.code) return body.code;
  if (status === 404) return "not_found";
  if (status === 422 && Array.isArray(body.detail)) return "validation";
  return `http_${status}`;
}

type RequestOptions = {
  method?: string;
  json?: unknown;
  form?: FormData;
  key?: string | null;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers({ "X-Xteink-Request": "1" });
  const key = opts.key !== undefined ? opts.key : getStoredKey();
  if (key) headers.set("Authorization", `Bearer ${key}`);
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method: opts.method ?? "GET",
      headers,
      body,
      credentials: "same-origin",
    });
  } catch {
    throw new NetworkError();
  }

  if (response.status === 401) throw new AuthRequiredError();
  if (!response.ok) {
    let parsed: ErrorBody = {};
    try {
      parsed = (await response.json()) as ErrorBody;
    } catch {
      // Not JSON; keep the generic message below.
    }
    const detail = detailText(parsed.detail) || `Request failed (${response.status}).`;
    throw new ApiError(response.status, codeFor(response.status, parsed), detail);
  }
  if (response.status === 204) return undefined as T;
  if (opts.method === "GET" || opts.method === undefined) {
    const type = response.headers.get("Content-Type") ?? "";
    if (!type.includes("json")) return (await response.blob()) as T;
  }
  return (await response.json()) as T;
}

// --- connection ------------------------------------------------------------

/** True when the server accepts `key`; false when it answers 401. */
export async function verifyKey(key: string): Promise<boolean> {
  try {
    await request("/api/library?limit=1", { key: key.trim() });
    return true;
  } catch (err) {
    if (err instanceof AuthRequiredError) return false;
    throw err;
  }
}

/**
 * Ask the server, without any API key, whether this browser is already signed
 * in (Cloudflare Access SSO). Resolves to the identity, or null on a 401
 * (no SSO here, e.g. on the LAN: the connect panel is needed).
 */
export async function probeSession(): Promise<Whoami | null> {
  try {
    return await request<Whoami>("/api/whoami", { key: null });
  } catch (err) {
    if (err instanceof AuthRequiredError) return null;
    throw err;
  }
}

// --- library ---------------------------------------------------------------

export type ListParams = { q?: string; kind?: Kind | ""; limit?: number; offset?: number };

export function listItems(params: ListParams = {}): Promise<{ items: Item[] }> {
  const qs = new URLSearchParams();
  if (params.q && params.q.trim()) qs.set("q", params.q.trim());
  if (params.kind) qs.set("kind", params.kind);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  if (params.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return request(`/api/library${query ? `?${query}` : ""}`);
}

export type UploadMeta = { title?: string; author?: string; kind?: Kind | "" };

export function uploadItem(
  file: File,
  meta: UploadMeta = {},
): Promise<{ item: Item; created: boolean }> {
  const form = new FormData();
  form.append("file", file, file.name);
  if (meta.title && meta.title.trim()) form.append("title", meta.title.trim());
  if (meta.author && meta.author.trim()) form.append("author", meta.author.trim());
  if (meta.kind) form.append("kind", meta.kind);
  return request("/api/library", { method: "POST", form });
}

export function deleteItem(id: number): Promise<void> {
  return request(`/api/library/${id}`, { method: "DELETE" });
}

/** The item's file. A plain link can't carry the bearer header, so fetch it. */
export function downloadItem(id: number): Promise<Blob> {
  return request(`/api/library/${id}/file`);
}

// --- devices ---------------------------------------------------------------

export function listDevices(): Promise<{ devices: Device[] }> {
  return request("/api/devices");
}

export function getDevice(id: number): Promise<Device> {
  return request(`/api/devices/${id}`);
}

/** Register a device. The raw `key` in the response is never shown again. */
export function registerDevice(
  name: string,
  mirror: boolean,
): Promise<{ device: Device; key: string }> {
  return request("/api/devices", { method: "POST", json: { name, mirror } });
}

export function revokeDevice(id: number): Promise<Device> {
  return request(`/api/devices/${id}/revoke`, { method: "POST" });
}

export function rotateDeviceKey(id: number): Promise<{ device: Device; key: string }> {
  return request(`/api/devices/${id}/rotate`, { method: "POST" });
}

export function setMirror(id: number, mirror: boolean): Promise<Device> {
  return request(`/api/devices/${id}/mirror`, { method: "PUT", json: { mirror } });
}

export function deviceQueue(
  id: number,
  state: "queued" | "delivered" | "all" = "all",
): Promise<{ entries: QueueEntry[] }> {
  return request(`/api/devices/${id}/queue?state=${state}`);
}

export function queueItem(deviceId: number, itemId: number): Promise<QueueEntry> {
  return request(`/api/devices/${deviceId}/queue`, { method: "POST", json: { item_id: itemId } });
}

// --- API keys --------------------------------------------------------------

export function listKeys(): Promise<{ keys: ApiKey[] }> {
  return request("/api/keys");
}

/** Create an API key. The raw `key` in the response is never shown again. */
export function createKey(name: string): Promise<{ api_key: ApiKey; key: string }> {
  return request("/api/keys", { method: "POST", json: { name } });
}

export function revokeKey(id: number): Promise<void> {
  return request(`/api/keys/${id}/revoke`, { method: "POST" });
}
