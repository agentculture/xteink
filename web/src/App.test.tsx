import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";
import * as api from "./services/api";
import { clearStoredKey, getStoredKey, storeKey } from "./services/storage";

vi.mock("./services/api", async (orig) => {
  const real = await orig<typeof import("./services/api")>();
  return { ...real, listItems: vi.fn(), listDevices: vi.fn() };
});

beforeEach(() => {
  window.location.hash = "";
  vi.mocked(api.listDevices).mockReset().mockResolvedValue({ devices: [] });
  vi.mocked(api.listItems).mockReset().mockResolvedValue({ items: [] });
});

afterEach(() => {
  clearStoredKey();
});

describe("App", () => {
  it("shows the connect panel, not a login form, when no key is stored", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /connect this browser/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/password|username/i)).not.toBeInTheDocument();
  });

  it("opens the library when a key is stored", async () => {
    storeKey("xtk_ab12cd34_secret");
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute("aria-current", "page");
  });

  it("returns to the connect panel and drops the key when the server rejects it", async () => {
    storeKey("xtk_ab12cd34_revoked");
    vi.mocked(api.listItems).mockRejectedValue(new api.AuthRequiredError());
    render(<App />);
    expect(await screen.findByText(/stopped working/i)).toBeInTheDocument();
    expect(getStoredKey()).toBeNull();
  });
});
