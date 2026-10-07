import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import * as api from "./services/api";
import { clearStoredKey, getStoredKey, storeKey } from "./services/storage";

vi.mock("./services/api", async (orig) => {
  const real = await orig<typeof import("./services/api")>();
  return {
    ...real,
    listItems: vi.fn(),
    listDevices: vi.fn(),
    listKeys: vi.fn(),
    probeSession: vi.fn(),
  };
});

const SSO = { via: "access", identity: "owner@example.com" } as const;

beforeEach(() => {
  window.location.hash = "";
  vi.mocked(api.listDevices).mockReset().mockResolvedValue({ devices: [] });
  vi.mocked(api.listItems).mockReset().mockResolvedValue({ items: [] });
  vi.mocked(api.listKeys).mockReset().mockResolvedValue({ keys: [] });
  vi.mocked(api.probeSession).mockReset().mockResolvedValue(null);
});

afterEach(() => {
  clearStoredKey();
});

describe("App", () => {
  it("shows the connect panel, not a login form, when no key is stored and there's no SSO", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: /connect this browser/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/password|username/i)).not.toBeInTheDocument();
    expect(api.probeSession).toHaveBeenCalledTimes(1);
  });

  it("checks for an SSO session before showing the connect panel", () => {
    vi.mocked(api.probeSession).mockReturnValue(new Promise(() => {}));
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent(/checking/i);
    expect(screen.queryByRole("heading", { name: /connect this browser/i })).not.toBeInTheDocument();
  });

  it("opens the library without a key when signed in via Cloudflare Access", async () => {
    vi.mocked(api.probeSession).mockResolvedValue(SSO);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /connect this browser/i })).not.toBeInTheDocument();
    expect(getStoredKey()).toBeNull();
  });

  it("says who is signed in via Cloudflare Access in Settings", async () => {
    vi.mocked(api.probeSession).mockResolvedValue(SSO);
    window.location.hash = "#/settings";
    render(<App />);
    expect(await screen.findByText(/signed in via cloudflare access/i)).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /forget this key/i })).not.toBeInTheDocument();
  });

  it("shows the connect panel when the SSO probe can't reach the server", async () => {
    vi.mocked(api.probeSession).mockRejectedValue(new api.NetworkError());
    render(<App />);
    expect(await screen.findByRole("heading", { name: /connect this browser/i })).toBeInTheDocument();
  });

  it("opens the library with a stored key and skips the SSO probe", async () => {
    storeKey("xtk_ab12cd34_secret");
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute("aria-current", "page");
    expect(api.probeSession).not.toHaveBeenCalled();
  });

  it("returns to the connect panel and drops the key when the server rejects it", async () => {
    storeKey("xtk_ab12cd34_revoked");
    vi.mocked(api.listItems).mockRejectedValue(new api.AuthRequiredError());
    render(<App />);
    expect(await screen.findByText(/stopped working/i)).toBeInTheDocument();
    expect(getStoredKey()).toBeNull();
  });

  it("falls back to the SSO session when a stored key is rejected", async () => {
    storeKey("xtk_ab12cd34_revoked");
    vi.mocked(api.listItems)
      .mockRejectedValueOnce(new api.AuthRequiredError())
      .mockResolvedValue({ items: [] });
    vi.mocked(api.probeSession).mockResolvedValue(SSO);
    render(<App />);
    await waitFor(() => expect(api.probeSession).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(getStoredKey()).toBeNull();
    expect(screen.queryByText(/stopped working/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /connect this browser/i })).not.toBeInTheDocument();
  });
});
