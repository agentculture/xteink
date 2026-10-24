# Kind transcript and newspaper validation (issue 8)

Evidence for plan `kind-transcript` task t9: what the live stack and the X3 did, step by
step, with actual output. Failures are recorded as failures.

## 1. Before-state on the running server (main, 0.12.1)

2026-10-24T16:44:14Z. `POST /api/library` on the live main app (`127.0.0.1:8780`) with a
10-byte text file, `title=kind probe`, `kind=transcript`:

```text
{"detail":[{"type":"literal_error","loc":["body","kind"],"msg":"Input should be 'book' or 'article'","input":"transcript","ctx":{"expected":"'book' or 'article'"}}]}
HTTP 422
```

A library search for `kind probe` afterwards returned `{"items":[]}`: nothing was stored.

On the X3, every delivered item so far sits directly in `/xteink/` (the earlier device logs
in `docs/evidence/t20-first-sync.md` and `t20-phone-upload-lan-sync.md` show
`/xteink/<article>.epub`).
