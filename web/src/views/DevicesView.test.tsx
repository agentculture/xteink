import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DevicesView } from "./DevicesView";
import * as api from "../services/api";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return {
    ...real,
    listDevices: vi.fn(),
    registerDevice: vi.fn(),
    deviceQueue: vi.fn(),
    revokeDevice: vi.fn(),
  };
});

const device = (over: Partial<api.Device> = {}): api.Device => ({
  id: 4,
  name: "Bedside",
  key_id: "kid",
  mirror: false,
  created_at: "2026-10-06T10:00:00Z",
  revoked_at: null,
  last_seen: null,
  last_sync_result: null,
  free_sd_bytes: null,
  firmware_version: null,
  last_error: null,
  ...over,
});

const RAW = "xtd_SECRETDEVICEKEY0123456789";

beforeEach(() => {
  vi.mocked(api.listDevices).mockReset().mockResolvedValue({ devices: [] });
  vi.mocked(api.registerDevice).mockReset();
  vi.mocked(api.deviceQueue).mockReset().mockResolvedValue({ entries: [] });
  vi.mocked(api.revokeDevice).mockReset();
});

describe("DevicesView pairing", () => {
  it("shows the new device key once, with a QR code, then never again", async () => {
    vi.mocked(api.registerDevice).mockResolvedValue({ device: device(), key: RAW });
    render(<DevicesView />);
    await userEvent.type(await screen.findByLabelText("Device name"), "Bedside");
    vi.mocked(api.listDevices).mockResolvedValue({ devices: [device()] });
    await userEvent.click(screen.getByRole("button", { name: "Pair device" }));

    const reveal = await screen.findByRole("region", { name: /key for bedside/i });
    expect(within(reveal).getByText(RAW)).toBeInTheDocument();
    expect(within(reveal).getByRole("img", { name: /qr code/i })).toBeInTheDocument();
    expect(within(reveal).getByText(/won't be shown again/i)).toBeInTheDocument();
    expect(api.registerDevice).toHaveBeenCalledWith("Bedside", false);

    await userEvent.click(within(reveal).getByRole("button", { name: /i've saved it/i }));
    expect(screen.queryByText(RAW)).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(RAW);
    // The device list still shows the device, without any key material.
    expect(await screen.findByRole("heading", { name: "Bedside" })).toBeInTheDocument();
  });

  it("copies the key to the clipboard", async () => {
    const user = userEvent.setup();
    vi.mocked(api.registerDevice).mockResolvedValue({ device: device(), key: RAW });
    render(<DevicesView />);
    await user.type(await screen.findByLabelText("Device name"), "Bedside");
    await user.click(screen.getByRole("button", { name: "Pair device" }));
    await user.click(await screen.findByRole("button", { name: "Copy key" }));
    expect(await navigator.clipboard.readText()).toBe(RAW);
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("shows last seen and delivery status for a device", async () => {
    vi.mocked(api.listDevices).mockResolvedValue({
      devices: [
        device({ last_seen: "2026-10-06T09:00:00Z", last_sync_result: "ok", free_sd_bytes: 2_000_000_000 }),
      ],
    });
    vi.mocked(api.deviceQueue).mockResolvedValue({
      entries: [
        { id: 1, device_id: 4, item_id: 1, title: "Waiting Book", size: 10, state: "queued", queued_at: "2026-10-06T09:30:00Z", delivered_at: null },
        { id: 2, device_id: 4, item_id: 2, title: "Arrived Book", size: 10, state: "delivered", queued_at: "2026-10-05T09:30:00Z", delivered_at: "2026-10-06T09:00:00Z" },
      ],
    });
    render(<DevicesView />);
    expect(await screen.findByText("Waiting Book")).toBeInTheDocument();
    expect(screen.getByText(/waiting for next sync/i)).toBeInTheDocument();
    expect(screen.getByText(/on the device since/i)).toBeInTheDocument();
    expect(screen.getByText(/last seen/i)).toBeInTheDocument();
  });

  it("asks for confirmation before revoking", async () => {
    vi.mocked(api.listDevices).mockResolvedValue({ devices: [device()] });
    vi.mocked(api.revokeDevice).mockResolvedValue(device({ revoked_at: "2026-10-06T11:00:00Z" }));
    render(<DevicesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke key" }));
    expect(api.revokeDevice).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Revoke Bedside's key" }));
    expect(api.revokeDevice).toHaveBeenCalledWith(4);
  });
});
