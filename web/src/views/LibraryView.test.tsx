import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LibraryView } from "./LibraryView";
import * as api from "../services/api";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return {
    ...real,
    listItems: vi.fn(),
    listDevices: vi.fn(),
    queueItem: vi.fn(),
    deleteItem: vi.fn(),
  };
});

const book: api.Item = {
  id: 7,
  sha256: "s",
  kind: "book",
  title: "Middlemarch",
  author: "George Eliot",
  format: "epub",
  size: 1_500_000,
  created_at: "2026-10-01T10:00:00Z",
};

const reader: api.Device = {
  id: 2,
  name: "Bedside",
  key_id: "k",
  mirror: false,
  created_at: "2026-10-01T10:00:00Z",
  revoked_at: null,
  last_seen: null,
  last_sync_result: null,
  free_sd_bytes: null,
  firmware_version: null,
  last_error: null,
};

beforeEach(() => {
  vi.mocked(api.listItems).mockReset().mockResolvedValue({ items: [book] });
  vi.mocked(api.listDevices).mockReset().mockResolvedValue({ devices: [reader] });
  vi.mocked(api.queueItem).mockReset();
  vi.mocked(api.deleteItem).mockReset();
});

describe("LibraryView", () => {
  it("lists items and searches through the API", async () => {
    render(<LibraryView onAddClick={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Middlemarch" })).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "eliot");
    await vi.waitFor(() =>
      expect(api.listItems).toHaveBeenLastCalledWith({ q: "eliot", kind: "", limit: 50 }),
    );
  });

  it("sends an item to a reader and shows its delivery status", async () => {
    vi.mocked(api.queueItem).mockResolvedValue({
      id: 1,
      device_id: 2,
      item_id: 7,
      title: "Middlemarch",
      size: 1,
      state: "queued",
      queued_at: "2026-10-06T10:00:00Z",
      delivered_at: null,
    });
    render(<LibraryView onAddClick={vi.fn()} />);
    const card = (await screen.findByRole("heading", { name: "Middlemarch" })).closest("article")!;
    await userEvent.click(within(card).getByRole("button", { name: "Send to reader" }));
    await userEvent.click(within(card).getByRole("button", { name: "Send" }));
    expect(api.queueItem).toHaveBeenCalledWith(2, 7);
    expect(await within(card).findByRole("status")).toHaveTextContent(
      "Sent to Bedside. It arrives on the reader's next sync.",
    );
  });

  it("deletes only after confirmation", async () => {
    vi.mocked(api.deleteItem).mockResolvedValue(undefined);
    render(<LibraryView onAddClick={vi.fn()} />);
    const card = (await screen.findByRole("heading", { name: "Middlemarch" })).closest("article")!;
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    expect(api.deleteItem).not.toHaveBeenCalled();
    await userEvent.click(within(card).getByRole("button", { name: "Delete “Middlemarch”" }));
    expect(api.deleteItem).toHaveBeenCalledWith(7);
    await vi.waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Middlemarch" })).not.toBeInTheDocument(),
    );
  });

  it("invites an upload when the library is empty", async () => {
    vi.mocked(api.listItems).mockResolvedValue({ items: [] });
    const onAdd = vi.fn();
    render(<LibraryView onAddClick={onAdd} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add books" }));
    expect(onAdd).toHaveBeenCalled();
  });
});
