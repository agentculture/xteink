import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectPanel } from "./ConnectPanel";
import * as api from "../services/api";
import { clearStoredKey, getStoredKey } from "../services/storage";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return { ...real, verifyKey: vi.fn() };
});

const verifyKey = vi.mocked(api.verifyKey);

beforeEach(() => {
  verifyKey.mockReset();
  clearStoredKey();
});

describe("ConnectPanel", () => {
  it("asks for a key before calling the server", async () => {
    const onConnected = vi.fn();
    render(<ConnectPanel onConnected={onConnected} />);
    await userEvent.click(screen.getByRole("button", { name: "Connect this browser" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/paste an api key/i);
    expect(verifyKey).not.toHaveBeenCalled();
    expect(onConnected).not.toHaveBeenCalled();
  });

  it("explains a rejected key and stores nothing", async () => {
    verifyKey.mockResolvedValue(false);
    const onConnected = vi.fn();
    render(<ConnectPanel onConnected={onConnected} />);
    await userEvent.type(screen.getByLabelText("API key"), "xtk_wrong");
    await userEvent.click(screen.getByRole("button", { name: "Connect this browser" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/didn't accept that key/i);
    expect(getStoredKey()).toBeNull();
    expect(onConnected).not.toHaveBeenCalled();
  });

  it("stores an accepted key and reports the connection", async () => {
    verifyKey.mockResolvedValue(true);
    const onConnected = vi.fn();
    render(<ConnectPanel onConnected={onConnected} />);
    await userEvent.type(screen.getByLabelText("API key"), "  xtk_good  ");
    await userEvent.click(screen.getByRole("button", { name: "Connect this browser" }));
    expect(verifyKey).toHaveBeenCalledWith("xtk_good");
    expect(onConnected).toHaveBeenCalled();
    expect(getStoredKey()).toBe("xtk_good");
  });

  it("says when the server is unreachable instead of blaming the key", async () => {
    verifyKey.mockRejectedValue(new api.NetworkError());
    render(<ConnectPanel onConnected={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("API key"), "xtk_good");
    await userEvent.click(screen.getByRole("button", { name: "Connect this browser" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't be reached/i);
  });
});
