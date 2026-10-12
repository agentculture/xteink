# xteink web UI

The browser front end for the xteink library server: add books, browse and
search the library, send items to a reader, pair and revoke readers, and manage
API keys. Vite 6, React 18, TypeScript and vitest. It is laid out like the
`reterminal-cli` `web/` app.

The UI calls the HTTP API and nothing else. All requests go through
`src/services/api.ts`. Components only present results.

## Scripts

```bash
npm ci              # install from package-lock.json
npm run dev         # dev server; proxies /api to http://127.0.0.1:8780
npm test            # vitest run
npm run typecheck   # tsc -b --force
npm run build       # typecheck, then build into ../xteink/server/_webassets
```

The main app (`xteink/server/app.py`) serves `xteink/server/_webassets/` at `/`
when `index.html` exists there. The build output is gitignored, so a fresh
checkout serves the placeholder page until you run `npm run build`.

## API key in the browser

Every `/api` route needs an API key, including on the LAN. On first visit the UI
shows a "Connect this browser" panel. You paste a key made with
`python -m xteink.server create-key NAME`, the UI checks it with
`GET /api/library?limit=1`, and then keeps it in `localStorage`. This is not a
login. Behind the tunnel, Cloudflare Access handles identity. After that, the UI
shows only the key's public part (`xtk_<id>…`). Settings has "Forget this key".
A 401 from any call clears the key and returns to the connect panel.

Device keys and new API keys appear once, at pairing, rotation or creation. A
device key also gets a QR code. The UI drops the raw key from state as soon as
you confirm you saved it.

## Design

It looks like e-paper. The palette is the greyscale an e-ink panel can show,
with no hue. Selection, focus and errors are inverted (light on black), the way
e-reader menus highlight. Strokes are 2px, because thin lines ghost on e-paper.
The type is Literata, which was designed for long-form screen reading. It is
self-hosted through `@fontsource-variable/literata`, so the UI makes no
third-party requests and works offline. The one decorative element is the drop
area's ordered-dither frame, the pattern a panel uses to fake grey. Dark mode is
the reader's inverted mode.

Screenshots from a run against a real local server are in `docs/screens/`.

## Dependencies

- `qrcode.react` draws the device-key QR code. It is a widely used, MIT-licensed
  React component with no runtime dependencies. It renders crisp SVG, which
  suits the high-contrast look, and it is small next to React itself.
- `@fontsource-variable/literata` provides the font files, bundled into the
  build output.
