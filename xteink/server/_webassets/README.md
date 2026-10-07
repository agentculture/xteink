# Web UI build output

`npm run build` in `web/` writes the web UI here. The main app
(`xteink/server/app.py`) serves this directory at `/` when `index.html`
exists, and a placeholder page otherwise.

Everything here except this file and `.gitignore` is ignored by git.
