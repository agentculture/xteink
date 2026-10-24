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

## 2. Deploy and schema v3 migration (0.13.0)

2026-10-24, after PR #11 merged. The data volume was backed up first
(`20261024T170039Z-xteink-data.tgz`, 27,643,370 bytes). Then the stack was rebuilt
from `origin/main` (`b1d62e6`).

| | Before | After |
|---|---|---|
| `PRAGMA user_version` | 2 | 3 |
| Items | 51 (50 article, 1 book) | 51, same ids |
| Queue rows / devices / firmware | 51 / 3 / 5 | unchanged |
| `sqlite_sequence` for `items` | 54 | 54 |
| `integrity_check` / `foreign_key_check` | | ok / empty |

`library.db.v2.bak` was written beside the database, with `user_version` 2 and
51 items. New items afterwards got ids 55 and up, so ids aren't reused.

Re-kind on the live server: items 29 and 53 became `transcript`, and 54 became
`newspaper`. The device queue then reported the new kinds.

## 3. Old firmware sees `kind` and ignores it

The X3 was still on `1.6.5+xteink.2b3cbdea` when Check for updates ran. That
firmware synced before it installed the update:

```text
[XSYNC] Inventory: 50 files hashed in 6109 ms
[XSYNC] Queue: 5 items, 0 skipped, 0 deletes, 0 dropped
[XSYNC] Sync done: OK, 4 new, 0 deleted, 0 skipped, 0 failed
```

The queue carried `kind` for every entry, and nothing was dropped (honesty
condition h5). As expected for that firmware, the items landed directly in
`/xteink/`. This step was not planned. The operator was told that Check for
updates only installs the update; that wrong statement is recorded as lapse l1.

## 4. Firmware release and OTA

`xteink firmware release 5` stored image 6, `1.6.5+xteink.ef7ff339` (5,855,760
bytes), and offered it to x3-ori. On the X3:

```text
[OTA] Offer from http://192.168.1.157:8781: install (1.6.5+xteink.ef7ff339, running 1.6.5+xteink.2b3cbdea)
[OTA] Installing 1.6.5+xteink.ef7ff339 (5855760 B) from http://192.168.1.157:8781
[OTA] Update completed
[OTAHC] Health check of xteink-fw 1.6.5+xteink.ef7ff339: valid (ok, 1 attempts, 3225 ms)
```

## 5. Four kinds in one sync, plus mirror deletes

Setup:

- One test EPUB of each kind was queued: 57 book, 58 article, 59 transcript and
  60 newspaper.
- The 14 newspaper items (5, 8–10, 12–20 and 54) were deleted from the library.
- Mirror was turned on for x3-ori.

```text
[XSYNC] Inventory: 54 files hashed in 6214 ms
[XSYNC] Queue: 4 items, 0 skipped, 15 deletes, 0 dropped
[XSYNC] Sync done: OK, 4 new, 15 deleted, 0 skipped, 0 failed
```

The 15 deletes were the 14 newspapers plus one earlier-deleted item still on the
card. Afterwards the X3's library index rebuilt with the new folders:

```text
[LIBIDX] built: 51 books, 6 folders, 39 parsed, 12 metadata reused, replaced 1, 0 dup dropped, 0 unreadable, 1277ms
[LIB] reconciled: 12 unchanged, 39 added, 0 renamed, 14 removed, 43 enriched (0 dup, 0 unreadable)
```

The firmware does not log the path it writes, so placement was checked on the
device. The operator saw the `articles`, `transcripts` and `newspapers` folders
beside the earlier files in `/xteink/`.

## 6. Mirror deletes from the subfolders

The test items 55–60 were deleted from the library. Four of them (57–60) sat in
`/xteink/`, `articles/`, `transcripts/` and `newspapers/`.

```text
[XSYNC] Inventory: 43 files hashed in 3524 ms
[XSYNC] Queue: 0 items, 0 skipped, 6 deletes, 0 dropped
[XSYNC] Sync done: OK, 0 new, 6 deleted, 0 skipped, 0 failed
```

43 inventoried files is the server's 37 remaining items plus those 6, so the
card's synced files and the library matched exactly.

## 7. Clearing the recordings

The operator asked for the 33 recordings (ids 21–53) to come off the reader. All
33 are kept in culture-library with the same id and sha256, checked before
deleting. After they were deleted from xteink, with mirror on:

```text
[XSYNC] Inventory: 37 files hashed in 3468 ms
[XSYNC] Queue: 0 items, 0 skipped, 33 deletes, 0 dropped
[XSYNC] Sync done: OK, 0 new, 33 deleted, 0 skipped, 0 failed
```

Mirror was then turned off again. The reader now holds the 3 articles and 1 book
left in xteink's library.

## Open

- The operator still saw `Daily newspaper …` EPUBs in `/xteink/` after step 5.
  They were not in the sync's inventory: in step 6 it matched the library
  exactly. So the sync never delivered them, or they were changed on the device.
  Mirror leaves such files alone by design. They are deleted by hand in Browse
  files; where they came from was not determined.
- Lapse l1 (above) awaits the operator's adjudication.
