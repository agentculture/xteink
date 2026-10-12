# HTTP API

The xteink server runs two apps from one process and one library:

| App | Default port | Serves | Key |
|-----|--------------|--------|-----|
| Main app | 8780 | Web UI at `/`, `/api/library*`, `/api/devices*`, `/api/keys*`, `/api/whoami`, `/docs` | API key (`xtk_`), or Cloudflare Access SSO when configured |
| Device app | 8781 | `/api/device/*` only | Device key (`xtd_`) |

The machine-readable schema of the main app is committed at
[`api/openapi.json`](../api/openapi.json) and served live at
`/openapi.json`, with interactive docs at `/docs`. The device app serves no docs
and no schema; its contract is [`device-protocol.md`](device-protocol.md).
Regenerate the committed schema with
`uv run python scripts/export-openapi.py` (`--check` fails when it is stale).

## Authentication

Every `/api/*` route needs a credential, including on the LAN. Usually that is
a key, sent as a bearer token:

```http
Authorization: Bearer <api-key>
```

- **API keys** start with `xtk_`. They guard the main app. The first one is
  minted from the host with
  `docker compose run --rm api python -m xteink.server create-key <name>`
  (or `uv run python -m xteink.server create-key <name>` for a local install).
  More keys can be created through `POST /api/keys`. A raw key is shown once,
  when it is created; only its hash is stored.
- **Device keys** start with `xtd_`. They guard the device app only, and are
  issued once per device by `POST /api/devices` (or `xteink device provision`).
  A device key does not work on the main app, and an API key does not work on
  the device app.
- A missing, malformed, unknown, revoked or wrong-kind key gets `401` with
  `WWW-Authenticate: Bearer` and `{"detail": "invalid or missing key"}`.

### Cloudflare Access SSO (main app only)

When the server is started with both `XTEINK_ACCESS_TEAM_DOMAIN` and
`XTEINK_ACCESS_AUD` set, the main app also accepts the signed
`Cf-Access-Jwt-Assertion` header that Cloudflare Access adds to every request
it proxies (the web UI on `ebooks.culture.dev`). Setting only one of the two
makes the server refuse to start. With neither set, Access auth is off and the
server never contacts Cloudflare.

The server checks the JWT itself: RS256 only, `kid` in the team's JWKS
(`https://<team>/cdn-cgi/access/certs`), a valid signature,
`iss == https://<team>`, the configured AUD in `aud`, and `nbf`/`exp` with
30 seconds of clock leeway. The JWKS is fetched lazily, the first time a
request carries an Access JWT, then cached by `kid`. That fetch is the only
outbound call it adds.

The rules, in order:

| Request | Result |
|---------|--------|
| Any `Authorization` header | Decided by the key alone, exactly as above. A bad key is `401` even if a valid Access JWT is also present. |
| No `Authorization`, valid Access JWT, Access configured | Authenticated as an operator (the Access email, or service-token name, is logged; the token never is). |
| Same, but `POST`/`PUT`/`DELETE` without `X-Xteink-Request: 1` | `403`. An SSO session is an ambient browser credential, and the custom header cannot be sent cross-site without a CORS preflight. |
| No `Authorization`, Access JWT invalid (bad signature, unknown `kid`, wrong `iss` or `aud`, expired) | `401` |
| No `Authorization`, Access JWT present, Access not configured | `401` (the JWT is ignored) |
| Only the `CF_Authorization` cookie | `401`. Only the header is read. |

The device app never accepts Access JWTs, configured or not.

### GET /api/whoami

Response `200`: `{"via": "key", "identity": "<key name>"}` or
`{"via": "access", "identity": "<email>"}`. `401` without a credential. The
web UI calls it without a key on load: a `200` means the browser is signed in
via Cloudflare Access and needs no key.

The web UI shell at `/` is static and loads without a key. Behind Cloudflare
Access it needs no key either. On the LAN, its first-run "Connect this browser"
panel stores an API key in that browser (see
[`remote-access.md`](remote-access.md)).

Errors are JSON with a `detail` field. Besides the codes listed per endpoint,
request-validation failures return `422` with FastAPI's list-shaped `detail`.

## Objects

Item:

```json
{
  "id": 1,
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "kind": "article",
  "title": "My article",
  "author": "",
  "format": "epub",
  "size": 48213,
  "created_at": "2026-10-06T12:00:00+00:00"
}
```

`kind` is `book` or `article`. `format` is `epub`, `bmp` or `txt`.
`size` is in bytes.

Device: `id`, `name`, `key_id`, `mirror`, `created_at`, `revoked_at`,
`last_seen`, `last_sync_result`, `free_sd_bytes`, `firmware_version`,
`last_error`. The raw device key is never part of this object.

Queue entry: `id`, `device_id`, `item_id`, `title`, `size`, `sha256`, `state`
(`queued` or `delivered`), `queued_at`, `delivered_at`.

API key: `id`, `name`, `key_id`, `created_at`, `revoked_at`, `last_used`.

## Library

### GET /api/library

Query parameters: `q` (search title and author), `kind` (`book` or `article`),
`limit` (1 to 1000, default 100), `offset` (default 0).

```bash
curl -H "Authorization: Bearer <api-key>" "http://localhost:8780/api/library?q=dune&kind=book"
```

Response `200`: `{"items": [Item, ...]}`.

### POST /api/library

Upload one file as `multipart/form-data`. Fields: `file` (required), `title`
(default: the filename without its extension), `author` (default empty), `kind`
(`book` or `article`; default `article` for converted Markdown/HTML, `book`
otherwise).

```bash
curl -H "Authorization: Bearer <api-key>" \
     -F "file=@article.md" -F "title=My article" -F "kind=article" \
     http://localhost:8780/api/library
```

What is accepted: EPUB, BMP and TXT are validated and stored as-is. Markdown
(`.md`, `.markdown`) and HTML (`.html`, `.htm`) are converted to EPUB with
pandoc. The size limit is 50 MiB. EPUBs are checked for zip bombs (at most 5000
entries and 500 MiB uncompressed). Content is identified by its sha256, so an
identical upload is deduplicated.

Response `201`: `{"item": Item, "created": true}`. If the same bytes were
already in the library the response is `200` with `"created": false` and the
existing item.

Ingest errors have the shape `{"detail": "<message>", "code": "<code>"}`:

| `code` | HTTP | Meaning |
|--------|------|---------|
| `too_large` | 413 | File exceeds the 50 MiB limit |
| `unsupported_format` | 415 | Extension is not EPUB, BMP, TXT, Markdown or HTML |
| `pdf_not_supported` | 415 | PDF is not supported yet |
| `bad_magic` | 422 | Content does not match its type (empty file, invalid EPUB/BMP, text that is not UTF-8) |
| `zip_bomb` | 422 | EPUB has too many entries or is too large uncompressed |
| `conversion_failed` | 422 | pandoc failed, or produced an invalid EPUB |
| `conversion_timeout` | 422 | Conversion took longer than 60 seconds |
| `converter_missing` | 503 | The host has no usable pandoc (the Docker image bundles it) |

A blank `title` or an invalid `kind` returns `422` with a plain `detail`.

### GET /api/library/{item_id}

Response `200`: an Item. `404` if it does not exist.

### GET /api/library/{item_id}/file

The stored bytes, with a media type for the format and a safe download
filename. `404` if the item does not exist.

### DELETE /api/library/{item_id}

Response `204`. `404` if it does not exist.

## Devices

### GET /api/devices

Response `200`: `{"devices": [Device, ...]}`.

### POST /api/devices

Register a device. Body: `{"name": "my-reader", "mirror": false}` (`name`
required, 1 to 200 characters). `mirror` makes the device delete server-removed
files it downloaded earlier and never edited (see the protocol doc).

Response `201`: `{"device": Device, "key": "xtd_..."}`. This is the only time
the raw device key is returned.

### GET /api/devices/{device_id}

Response `200`: the Device, including `last_seen` and the last status report.
`404` if unknown.

### POST /api/devices/{device_id}/revoke

Revoke the device key. Response `200`: the Device with `revoked_at` set. The
device gets `401` from then on. `404` if unknown.

### POST /api/devices/{device_id}/rotate

Replace the device key; the old one stops working. Response `200`:
`{"device": Device, "key": "xtd_..."}` (new raw key, shown once). `404` if
unknown.

### PUT /api/devices/{device_id}/mirror

Body: `{"mirror": true}`. Response `200`: the Device. `404` if unknown.

### GET /api/devices/{device_id}/queue

Query parameter `state`: `queued` (default), `delivered` or `all`.
Response `200`: `{"entries": [Queue entry, ...]}`. `404` if the device is
unknown.

### POST /api/devices/{device_id}/queue

Queue a library item so the device downloads it on its next sync. Body:
`{"item_id": 1}`. Idempotent while the item is queued; queueing an item the device
already has (`delivered`) queues it again, so it is re-sent on the next sync. Response `201`: the Queue entry. `404` if the
device or the item does not exist.

## API keys

### GET /api/keys

Response `200`: `{"keys": [API key, ...]}`. Raw keys are never listed.

### POST /api/keys

Body: `{"name": "mcp"}`. Response `201`:
`{"api_key": API key, "key": "xtk_..."}`. The raw key is shown once.

### POST /api/keys/{key_id}/revoke

Response `204`. `404` if unknown. Revoking the only key you have locks you out
of the API; mint a new one on the host with `create-key`.

## Device app

The device app on port 8781 serves only `/api/device/*` with `xtd_` keys and the
`X-Xteink-Protocol: 1` header: `GET /whoami`, `POST /status`, `GET /queue`,
`GET /items/{id}` (with `Range` resume) and `POST /ack`. Everything else,
including `/docs` and `/openapi.json`, is `404`. The full contract is in
[`device-protocol.md`](device-protocol.md).
