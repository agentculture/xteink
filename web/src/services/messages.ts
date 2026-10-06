/**
 * Plain-language copy for API errors. Presentation only: the codes come from
 * the server (xteink/core/ingest.py and xteink/server/routes_library.py).
 */

import { ApiError, AuthRequiredError, NetworkError } from "./api";

const UPLOAD_MESSAGES: Record<string, string> = {
  too_large: "This file is over the server's size limit. Split it, or compress its images.",
  unsupported_format:
    "xteink takes EPUB, plain text (.txt), BMP images, and Markdown or HTML. This file is none of those.",
  pdf_not_supported:
    "PDFs aren't supported yet. Convert it to EPUB first (Calibre can), then add the EPUB.",
  bad_magic: "The file's contents don't match its extension. It may be damaged or misnamed.",
  zip_bomb: "This EPUB unpacks to something far larger than a book. It was refused for safety.",
  conversion_failed: "The server couldn't convert this file to EPUB. Check that it opens elsewhere.",
  conversion_timeout: "Converting this file took too long, so the server stopped.",
  converter_missing:
    "The server can't convert Markdown or HTML because pandoc isn't installed on it. Install pandoc on the server, or add an EPUB or .txt instead.",
};

export function errorMessage(err: unknown): string {
  if (err instanceof AuthRequiredError) return err.message;
  if (err instanceof NetworkError) {
    return "The xteink server can't be reached. Check that it's running and this device is on the same network.";
  }
  if (err instanceof ApiError) {
    const known = UPLOAD_MESSAGES[err.code];
    if (known) return known;
    if (err.code === "not_found") return "That no longer exists. Someone may have removed it.";
    return err.detail || `The server answered ${err.status}.`;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}
