import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsView } from "./SettingsView";
import * as api from "../services/api";
import { clearStoredKey, storeKey } from "../services/storage";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return { ...real, listKeys: vi.fn(), createKey: vi.fn(), revokeKey: vi.fn() };
});

const STORED = "xtk_ab12cd34_PRIVATEpart";

beforeEach(() => {
  storeKey(STORED);
  vi.mocked(api.listKeys).mockReset().mockResolvedValue({
    keys: [
      { id: 1, name: "laptop", key_id: "ab12cd34", created_at: "2026-10-01T00:00:00Z", revoked_at: null, last_used: null },
    ],
  });
  vi.mocked(api.createKey).mockReset();
});

afterEach(() => clearStoredKey());

describe("SettingsView", () => {
  it("shows only the stored key's public prefix and marks it as this browser's", async () => {
    render(<SettingsView onForget={vi.fn()} hostname="192.168.1.20" />);
    expect(await screen.findByText("This browser")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("PRIVATEpart");
    expect(screen.getAllByText("xtk_ab12cd34…").length).toBeGreaterThan(0);
  });

  it("labels tunnel info as configuration and reports the LAN honestly", () => {
    render(<SettingsView onForget={vi.fn()} hostname="192.168.1.20" />);
    expect(screen.getByText(/shows configuration, not whether the tunnel is up/i)).toBeInTheDocument();
    expect(screen.getByText("ebooks.culture.dev")).toBeInTheDocument();
    expect(screen.getByText("xteink.culture.dev")).toBeInTheDocument();
    expect(screen.getByText(/your local network \(192\.168\.1\.20\)/)).toBeInTheDocument();
  });

  it("recognises the tunnel hostname", () => {
    render(<SettingsView onForget={vi.fn()} hostname="ebooks.culture.dev" />);
    expect(screen.getByText(/the tunnel, through cloudflare access/i)).toBeInTheDocument();
  });

  it("shows a new API key once", async () => {
    vi.mocked(api.createKey).mockResolvedValue({
      api_key: { id: 2, name: "phone", key_id: "ffff0000", created_at: "", revoked_at: null, last_used: null },
      key: "xtk_ffff0000_NEWRAW",
    });
    render(<SettingsView onForget={vi.fn()} hostname="localhost" />);
    await userEvent.type(screen.getByLabelText("New key name"), "phone");
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByText("xtk_ffff0000_NEWRAW")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /i've saved it/i }));
    expect(screen.queryByText("xtk_ffff0000_NEWRAW")).not.toBeInTheDocument();
  });

  it("forgets the key only after confirmation", async () => {
    const onForget = vi.fn();
    render(<SettingsView onForget={onForget} hostname="localhost" />);
    await userEvent.click(screen.getByRole("button", { name: "Forget this key" }));
    expect(onForget).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Forget key" }));
    expect(onForget).toHaveBeenCalled();
  });
});
