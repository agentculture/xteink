import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddView } from "./AddView";
import * as api from "../services/api";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return { ...real, uploadItem: vi.fn() };
});

const uploadItem = vi.mocked(api.uploadItem);

const item = (id: number, title: string): api.Item => ({
  id,
  title,
  sha256: "x",
  kind: "book",
  author: "",
  format: "epub",
  size: 1234,
  created_at: "2026-10-06T10:00:00Z",
});

function drop(files: File[]) {
  const zone = screen.getByTestId("drop-page");
  fireEvent.dragEnter(zone, { dataTransfer: { files, types: ["Files"] } });
  fireEvent.drop(zone, { dataTransfer: { files, types: ["Files"] } });
}

beforeEach(() => {
  uploadItem.mockReset();
});

describe("AddView", () => {
  it("uploads a dropped file and confirms it was added", async () => {
    uploadItem.mockResolvedValue({ item: item(1, "Moby Dick"), created: true });
    render(<AddView onAdded={vi.fn()} />);
    drop([new File(["x"], "moby.epub")]);
    const row = await screen.findByText("moby.epub");
    expect(uploadItem).toHaveBeenCalledWith(expect.any(File), expect.any(Object));
    expect(
      await within(row.closest("li")!).findByText(/added as “Moby Dick”/i),
    ).toBeInTheDocument();
  });

  it("says when a file was already in the library", async () => {
    uploadItem.mockResolvedValue({ item: item(1, "Moby Dick"), created: false });
    render(<AddView onAdded={vi.fn()} />);
    drop([new File(["x"], "moby.epub")]);
    expect(await screen.findByText(/already in your library/i)).toBeInTheDocument();
  });

  it.each([
    ["pdf_not_supported", 415, /pdfs aren't supported yet/i],
    ["converter_missing", 503, /pandoc isn't installed/i],
    ["too_large", 413, /size limit/i],
    ["bad_magic", 422, /don't match its extension/i],
  ])("turns %s into a readable reason", async (code, status, text) => {
    uploadItem.mockRejectedValue(new api.ApiError(status, code, "raw detail"));
    render(<AddView onAdded={vi.fn()} />);
    drop([new File(["x"], "thing.bin")]);
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("uploads several files one at a time and reports each", async () => {
    uploadItem
      .mockResolvedValueOnce({ item: item(1, "One"), created: true })
      .mockRejectedValueOnce(new api.ApiError(415, "unsupported_format", "x"));
    render(<AddView onAdded={vi.fn()} />);
    drop([new File(["1"], "one.txt"), new File(["2"], "two.docx")]);
    expect(await screen.findByText(/added as “One”/i)).toBeInTheDocument();
    expect(await screen.findByText(/none of those/i)).toBeInTheDocument();
    expect(uploadItem).toHaveBeenCalledTimes(2);
  });

  it("accepts files from the keyboard-reachable picker too", async () => {
    uploadItem.mockResolvedValue({ item: item(2, "Notes"), created: true });
    render(<AddView onAdded={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText(/choose files/i), new File(["n"], "notes.txt"));
    expect(await screen.findByText(/added as “Notes”/i)).toBeInTheDocument();
  });
});
