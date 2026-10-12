/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands in the Python package; xteink/server/app.py serves it at "/"
// when index.html exists there. The output is gitignored
// (xteink/server/_webassets/.gitignore), so the committed tree keeps the
// server's placeholder page and the build is a local/CI step.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../xteink/server/_webassets",
    // scripts/clean-webassets.mjs empties it first but keeps the tracked
    // .gitignore and README.md, which emptyOutDir would delete.
    emptyOutDir: false,
    sourcemap: false,
  },
  server: {
    // `npm run dev` talks to a locally running `python -m xteink.server serve`.
    proxy: { "/api": "http://127.0.0.1:8780" },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
