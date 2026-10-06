# MCP server

`xteink.mcp` lets an MCP client (Claude Code, an agent on the Culture mesh, any
MCP-capable tool) push files into the library and queue them for a reader. It is
a thin client of the [HTTP API](api.md): it holds no data of its own and calls
the main app with an API key. It is built on the official `mcp` Python SDK.

## Running it

The server needs the `server` extra (`pip install 'xteink[server]'`, or
`uv sync --extra server` in a checkout). The Docker image already has it.

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `XTEINK_URL` | `http://127.0.0.1:8780` | Main app URL |
| `XTEINK_API_KEY` | none | API key (`xtk_...`). Required; the server exits with code 2 and a message if it is missing |
| `XTEINK_MCP_BIND` | `0.0.0.0` | Bind address for `--http` |
| `XTEINK_MCP_PORT` | `8782` | Port for `--http` |
| `XTEINK_MCP_TRANSPORT` | `stdio` | Set to `http` to act like `--http` |

Mint a dedicated key for it so you can revoke it independently:

```bash
docker compose run --rm api python -m xteink.server create-key mcp
```

### stdio (local agents)

The default. The MCP client starts the process and talks over stdin/stdout:

```bash
XTEINK_URL=http://localhost:8780 XTEINK_API_KEY=<api-key> \
  uv run --extra server python -m xteink.mcp
```

`uv run xteink mcp serve` does the same through the CLI.

### streamable-http (LAN, tailnet, mesh)

```bash
python -m xteink.mcp --http --bind 0.0.0.0 --port 8782
```

In the compose stack this is the `mcp` service, published on host port 8782
(`XTEINK_PUBLISH_MCP_PORT`). The endpoint is `http://<host>:8782/mcp/`. Put the
service key in `.env` as `XTEINK_API_KEY` and run `docker compose up -d`; see
the README.

The MCP server has no authentication of its own: whoever can reach the port can
use the library through its key. The path is `/mcp/`; `/mcp` answers with a
307 redirect to it. Keep it on a LAN, a tailnet or the mesh.

### Scope: not over the internet

Remote MCP over the internet is out of scope. The compose `remote` profile
tunnels only the web UI (behind Cloudflare Access) and the device app. It never
exposes the MCP port. Reach MCP from elsewhere over Tailscale or the mesh.

## Client configuration

A `.mcp.json` for Claude Code, stdio, started from a checkout:

```json
{
  "mcpServers": {
    "xteink": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/xteink", "--extra", "server",
               "python", "-m", "xteink.mcp"],
      "env": {
        "XTEINK_URL": "http://localhost:8780",
        "XTEINK_API_KEY": "<api-key>"
      }
    }
  }
}
```

Or against the HTTP service on another machine:

```json
{
  "mcpServers": {
    "xteink": {
      "type": "http",
      "url": "http://<host-or-tailnet-name>:8782/mcp/"
    }
  }
}
```

Keep real keys out of any file you commit.

## Tools

### push_file

Add a file to the library. EPUB, BMP and TXT are stored as-is; Markdown and HTML
are converted to EPUB. Give **exactly one** of `path`, `content` or
`content_base64`. Optionally queue it for a device in the same call.

| Argument | Type | Notes |
|----------|------|-------|
| `path` | string | File on the MCP host |
| `content` | string | File text, e.g. a Markdown article. Needs `filename` |
| `content_base64` | string | Binary file, base64. Needs `filename` |
| `filename` | string | e.g. `article.md`; the extension picks the format |
| `title`, `author` | string | Optional metadata |
| `kind` | `book` or `article` | Optional |
| `device` | string or integer | Device id or name; queues the item for it |

Push a Markdown article and queue it for a reader called `my-reader`:

```json
{
  "name": "push_file",
  "arguments": {
    "filename": "why-local-first.md",
    "title": "Why local-first",
    "kind": "article",
    "content": "# Why local-first\n\nYour library stays on hardware you own.\n",
    "device": "my-reader"
  }
}
```

Result (JSON text): `{"item": {"id": 7, "title": "...", "kind": "article",
"format": "epub", "size": 18422}, "created": true, "queued": {...queue entry...}}`. `created`
is `false` when identical bytes were already in the library.

### list_library

List or search items. Arguments: `q` (searches title and author), `kind`,
`limit` (1 to 1000, default 100).

```json
{"name": "list_library", "arguments": {"q": "local-first", "kind": "article"}}
```

Result: `{"items": [{"id": 7, "title": "...", ...}]}`.

### send_to_device

Queue an existing item so the device downloads it on its next sync. Both
arguments are required.

```json
{"name": "send_to_device", "arguments": {"device": "my-reader", "item_id": 7}}
```

Result: the queue entry. `device` may be an id or a unique name.

### Errors

A failed call returns an MCP tool error whose message starts with a short code,
for example `unknown_device`, `ambiguous_device`, `invalid_arguments`,
`unreadable_path`, `missing_key`, or an API error such as
`too_large (HTTP 413)`. The codes for rejected uploads are the ones in
[`api.md`](api.md#post-apilibrary).
