# kind transcript

> Transcripts and newspapers get their own folders on the reader: the xteink server accepts kind=transcript and kind=newspaper and sends each item's kind in its device queue entry, and the X3 firmware files articles under /xteink/articles/, transcripts under /xteink/transcripts/ and newspapers under /xteink/newspapers/, while books stay in /xteink/ (issue 8)
> instruction: verify end to end on the X3; record in docs/evidence/kind-transcript-validation.md

## Audience

- The xteink operator reading on the X3, and culture-rules' Pocket-transcript workflow, which uploads one EPUB per recording and queues it on the device
  - instruction: check issue 8: culture-rules is the uploader, the operator is the reader

## Before → After

- Before: Today every delivered item lands flat in /xteink/ on the reader, and the server refuses kind=transcript (`routes_library.py`:40 Literal, store.py:23 CHECK), so dozens of daily transcripts would mix with books and the daily newspaper
  - instruction: reproduce: POST /api/library with kind=transcript returns 422 on main
- After: After one daily sync, a transcript sits in /xteink/transcripts/, a newspaper in /xteink/newspapers/, an article in /xteink/articles/ and a book stays in /xteink/, and an older firmware still syncs all four flat without error
  - instruction: X3 evidence file under docs/evidence/ showing the three paths after a sync

## Why it matters

- Transcripts arrive daily and grow without bound; without their own folder the books the operator actually reads get buried in /xteink/
  - instruction: issue 8 'Why' section

## Requirements

- Schema step 3 in xteink/core/store.py `_MIGRATIONS` rebuilds the items table with CHECK (kind IN ('book','article','transcript','newspaper')), because SQLite can't ALTER a CHECK and `_SCHEMA` (store.py:16-18) is never edited; the rebuild keeps items.id values, `sqlite_sequence` and the queue.`item_id` FK rows (store.py:47) intact; tests/core/`test_firmware.py`::`test_firmware_never_goes_into_items` (asserts the old CHECK text, :246) is updated and a new migration test covers an issue-1/v2 DB with queue rows
  - honesty: A copy of a v2 production library.db (items + queue rows) migrates to v3 with every items.id, sha256, kind and queue row unchanged, and a fresh DB gets the same columns (`test_fresh_db_gets_the_same_schema_as_a_migrated_one`)
- transcript and newspaper are accepted everywhere a kind is enumerated: xteink/core/models.py:7 KINDS, `routes_library.py`:40 Kind Literal (upload + list filter), cli/`_commands`/library.py:18 KINDS (kept equal by tests/cli/`test_nouns.py`:317), mcp/tools.py:12 `_KIND` enum, web/src/services/api.ts:21 Kind; api/openapi.json is regenerated (export-openapi.py --check); any other value is still refused with 422
  - honesty: kind=transcript is accepted by the API, CLI --kind, MCP `push_file` and the web Add form, and kind=comic still returns 422 from each
  - honesty: kind=transcript and kind=newspaper are accepted by the API, CLI --kind, MCP `push_file` and the web Add form, and kind=comic still returns 422 from each
- Each device queue entry carries kind: xteink/core/devices.py `_Q` (:12-15) selects i.kind, QueueEntry (core/models.py:50-62) gains kind, `routes_device.py` `get_queue` (:262-271) emits it, with 'book' when the item has none; tests/server/`test_device_protocol.py`::`test_queue_shape` is updated
  - honesty: GET /api/device/queue returns kind on every entry, one of book|article|transcript|newspaper, 'book' for any item without a kind, and no other entry field changes
- Clients show transcripts and newspapers as their own kinds: web/src/views/LibraryView.tsx:200 (item.kind === 'article' ? 'Article' : 'Book' would label them Book) becomes a kind-to-label map, the filter radios (:87-94) and AddView.tsx option list (:118-121) gain Transcript and Newspaper, and docs/api.md (:100,:122,:135), docs/mcp.md (:114) and xteink/explain/catalog.py:164 (whose stale 'image' kind is dropped) list book|article|transcript|newspaper
  - honesty: Transcript items are labelled Transcript (never Book) in the library view and selectable in the filter and Add form
- Firmware QueueItem (xteink-firmware src/xteink/SyncProtocol.h:118, origin/feat/issue-1) parses an optional kind, where absent, unknown or wrong-typed means book, and a pure helper in SyncProtocol.{h,cpp} maps kind to folder (/xteink, /xteink/articles, /xteink/transcripts, /xteink/newspapers) so test/`xteink_sync`/XteinkSyncTest.cpp (host GoogleTest, no Storage) covers the per-kind path choice
  - honesty: parseQueue maps absent, unknown and non-string kind to book, and the kind-to-folder helper returns /xteink, /xteink/articles, /xteink/transcripts, /xteink/newspapers, with host tests for each
- Firmware placeFile (XteinkSync.cpp:489, origin/feat/issue-1) creates /xteink and then the kind subfolder on demand (Storage.mkdir is non-recursive), and applies the bookFileName / bookFileNameWithId clash rule and the never-overwrite-sideloaded-or-modified check inside that folder; docs/xteink/sync.md step 4 (:58-60) names the per-kind folders
  - honesty: placeFile never overwrites a sideloaded or user-modified file inside /xteink/articles or /xteink/transcripts, and creates the folder when it is missing
- PATCH /api/library/{id} accepts {kind} (any value in KINDS: book|article|transcript|newspaper; 422 otherwise) and xteink library set-kind ID KIND (dry-run unless --apply, MCP not required) calls it; the item record and every queue entry then carry the new kind. Files already on a device stay where they are (c11): re-queueing to the same device does not move the file, because the firmware finds its sha256 in the manifest and acks it in place (XteinkSync.cpp alreadyHere). A re-kinded item lands in its new folder only on a device that does not already hold it
  - instruction: tests/server/`test_app_routes.py` PATCH case + tests/cli/`test_nouns.py` set-kind dry-run/apply; api/openapi.json regenerated; docs/api.md documents PATCH
  - honesty: After PATCH kind=transcript, GET /api/library/{id} and the device queue entry both report transcript, sha256 and id are unchanged, and kind=comic returns 422
- Before applying any pending schema step, the Store copies library.db to library.db.v2.bak (named after the version being migrated from; sqlite3 backup API, same data dir), so rolling the server image back after the v3 rebuild has a restore path: an older xteink refuses a newer schema (store.py:111-115) and there is no backup of library.db today
  - honesty: Opening a v2 DB with v3 code leaves a readable library.db.v2.bak whose `user_version` is 2 and whose items rows match the pre-migration DB; an up-to-date DB writes no backup

## Honesty conditions

- Both halves ship: a server release that sends kind and a firmware image (offered via xteink firmware release) that files by kind; neither half alone is announced as done
- The current X3 firmware (pre-change) syncs a queue that carries kind without dropping items (parseQueue droppedItems stays 0)
- Uploading identical bytes twice, once as article and once as transcript, returns created:false and the original item with kind article
- A file in /xteink/transcripts is re-hashed on inventory and removed by a mirror-delete exactly like a flat /xteink file
- After updating the firmware, files previously delivered to /xteink/ keep their paths and are still in the manifest
- A file placed in /xteink/transcripts shows up in the X3 library browser after the sync
- culture-rules can switch its upload from kind=article to kind=transcript with no other change to its workflow (same fields: file, title, author, kind)
- On main today, POST /api/library with kind=transcript returns 422, and every X3 delivery path starts with /xteink/ followed directly by the filename
- The operator, not the agent, confirmed that separating transcripts from books is the goal (issue 8 author)
- The three paths are observed in a real X3 sync log, not inferred from unit tests
- The X3 run and both test suites are recorded with their actual output in the evidence file, including any failure

## Success signals

- On the X3, 1 item of each of the 4 kinds pushed in one sync lands in its own folder (4 folders) on the first try (0 SD errors), and the full server suite plus the firmware ctest suite pass, with ≥ 1 new test per acceptance criterion in issue 8
  - instruction: record the device log lines naming the 3 paths in docs/evidence/kind-transcript-validation.md

## Scope / boundaries

- The device protocol stays v1 (`PROTOCOL_VERSION` '1', `routes_device.py`:33): kind is an additive field like the OTA additions (`routes_device.py`:12-13, docs/device-protocol.md changelog :222-231); older firmware ignores it because parseQueue (xteink-firmware SyncProtocol.cpp) reads JSON keys by name with ArduinoJson and skips unknown ones; docs/device-protocol.md gets the field and a changelog line
- Dedup by sha256 is unchanged: xteink/core/library.py:52-56 looks up by sha256 only, so re-uploading the same bytes returns the existing item (created: false) with its original kind, whatever kind the new upload names
- Manifest, inventory, re-hash and mirror-delete need no change: DeliveredFile stores the full path, and every walk (XteinkSync.cpp:612 inventory, :819 deletes, origin/feat/issue-1) iterates manifest.files rather than scanning /xteink, so subfolder files work as they are

## Non-goals

- Files already delivered flat into /xteink/ are not moved or re-filed: their manifest paths are kept as they are

## Assumptions

- Files in /xteink/articles and /xteink/transcripts appear in the reader's library because LibraryBuilder.cpp:242 is described as a recursive walk and the sync marks the index dirty (XteinkSync.cpp); this is unverified on the X3

## Scope exploration

- `s1` — `xteink/core/store.py`: items.kind is CHECK-constrained to book/article in the frozen v1 `_SCHEMA` (:23); later changes are appended `_MIGRATIONS` steps under PRAGMA `user_version` (:64-97), so widening needs a step-3 table rebuild; queue.`item_id` is the only FK to items (:47)
  - seeds: `c2`
- `s2` — `xteink/core/models.py + library.py + routes_library.py`: KINDS (models.py:7) is enforced by library.py:45-46 (ValidationError -> 422) and by the `routes_library.py`:40 Literal before core runs; ingest.py only picks defaults (:171,:174)
  - seeds: `c3`
- `s3` — `CLI, MCP, web, explain catalog, api/openapi.json`: kind is enumerated separately in cli/`_commands`/library.py:18, mcp/tools.py:12, web api.ts:21, AddView.tsx:121, LibraryView.tsx:92/:200, explain/catalog.py:164 (stale 'image'); api/openapi.json covers only the main app and changes with the Literal
  - seeds: `c3`, `c7`
- `s4` — `xteink/core/devices.py + server/routes_device.py`: the queue SQL `_Q` (devices.py:12-15) doesn't select i.kind, QueueEntry has no kind, and `get_queue` builds plain dicts (`routes_device.py`:262-271), with no response model; protocol '1' with additive-change precedent (:12-13)
  - seeds: `c4`, `c5`
- `s5` — `docs/device-protocol.md`: queue entry example (:147) and field bullets (:154-164) list no kind; the changelog (:222-231) already records a 'v1, additive' entry, which is the pattern for this change
  - seeds: `c5`
- `s6` — `xteink/core/library.py dedup`: re-upload is looked up by sha256 alone (:52-56, IntegrityError race :77-84) and returns the original item and kind, so interim kind=article transcripts would not move when re-sent as transcript
  - seeds: `c6`, `q1` (question, resolved)
- `s7` — `xteink-firmware SyncProtocol.{h,cpp} (origin/feat/issue-1)`: QueueItem (h:118) has no kind; parseQueue reads keys by name with ArduinoJson v7 defaults (|), so unknown keys are ignored; the pure functions here are what test/`xteink_sync` (host CMake + GoogleTest, ci.yml ctest) can cover
  - seeds: `c8`, `c5`
- `s8` — `xteink-firmware XteinkSync.cpp placeFile (origin/feat/issue-1)`: kBooksDir '/xteink' (:52) is used only by placeFile (:489-), which mkdirs one level and runs the plain-name, then (id)-name clash rule; placeFile has no host test because it touches Storage
  - seeds: `c9`
- `s9` — `xteink-firmware manifest / inventory / mirror-delete`: DeliveredFile keeps the absolute path; inventory (:612) and deletes (:819) iterate manifest.files, with no directory scan, so subfolders need no change; the manifest cap is 300 (h:23)
  - seeds: `c10`, `c11`
- `s10` — `xteink-firmware LibraryBuilder.cpp`: the library index is described as a recursive walk (:242) and is marked dirty after a sync; the walk itself wasn't read, so subfolder visibility on the X3 is an assumption
  - seeds: `c12`
- `s11` — `challenge pass / failure-mode lens: xteink-firmware XteinkSync.cpp alreadyHere (origin/feat/issue-1)`: an item whose sha256 the manifest already holds is acked at its old path, never re-placed, so re-kind + re-queue can't move a delivered file; c20 amended to say so
  - seeds: `c20`
- `s12` — `challenge pass / adjacent-systems lens: culture-rules daily newspaper spec`: the newspaper uploads kind=article (daily-newspaper.md:35), so the per-kind folders re-home it too, not only transcripts
  - seeds: `c21` (rejected)
- `s13` — `challenge pass / reversibility lens: xteink/core/store.py _migrate + repo-wide grep for backup`: an older binary fails closed on a newer `user_version` (:111-115), which is safe but leaves no rollback without a copy; no library.db backup exists (grep over core/server/compose/docs), so a pre-migration copy was proposed
  - seeds: `c22`
- `s14` — `challenge pass / migration lens: scratch probe of the items rebuild (sqlite 3.50.4, Store from this repo)`: CREATE `items_new`, INSERT SELECT \*, DROP items, RENAME inside BEGIN IMMEDIATE with `foreign_keys` off kept the queue row, the `sqlite_sequence` (the next id is 4, not reused), `foreign_key_check` is empty, and ON DELETE CASCADE works after; note the stored DDL is 'CREATE TABLE items' (no IF NOT EXISTS). Not probed: the step run through `_migrate` itself
  - seeds: `c2`
- `s15` — `challenge pass / security lens: xteink/server/routes_library.py router + app.py device router`: clean: the library router depends on `require_operator` (:22-24), so a PATCH added there inherits key/Access-JWT auth; the device app (:126, `require_device_key`) gets no write route for kind
  - seeds: `c20`
- `s16` — `challenge pass / reversibility lens: firmware OTA rollback`: clean: older firmware ignores kind (c5) and walks manifest paths verbatim (c10), so after a rollback, subfolder files stay tracked and new items land flat again; no migration on the device
  - seeds: `c5`, `c10`
- `s17` — `challenge pass / lifecycle lens: xteink-firmware lib/LibraryIndex (origin/feat/issue-1)`: the index walk is recursive (walk depth+1, `LIBRARY_MAX_DEPTH` 5) and skips only dot-names, and the folder path limit is 255 bytes (`FOLDER_PATH_BYTES`), so /xteink/transcripts (depth 2) is indexed; this narrows assumption c12 but does not replace the on-device check (h12)
  - seeds: `c12`
- `s18` — `challenge pass / concurrency lens: store.py _migrate + compose services`: clean: BEGIN IMMEDIATE serialises a migration across processes; the mcp service talks HTTP via xteink/client.py and never opens library.db
  - seeds: `c2`
- `s19` — `challenge pass / unexamined: web tests, MCP tests, culture-rules switch-over`: not read: the kind assertions in web/src/views/\*.test.tsx and tests/mcp/\*, and how culture-rules will switch kind=article to transcript; the plan must cover them

## Decisions

- Existing items can be re-kinded through the API and the CLI; re-uploading the same bytes still returns the original item unchanged (dedup semantics stay as they are)
- The 300-entry firmware manifest cap stays as it is in this work; raising or pruning it is a follow-up issue
- A fourth library kind, newspaper, is added beside book, article and transcript; the culture-rules daily newspaper switches from kind=article to kind=newspaper, and the firmware files it under /xteink/newspapers/ (issue 8's per-kind plural folder rule)

## Hard questions

- culture-rules uploads transcripts as kind=article until this ships (issue 8, 'Until this ships'); after it switches, re-uploading those same bytes as transcript returns the existing article item and so never moves it. Does this work include a way to re-kind existing items (e.g. PATCH kind, or a one-off re-kind via CLI), or are interim articles left in /xteink/ flat/articles? (resolved: Add re-kind via API + CLI; dedup itself unchanged)

## Open parks

- [follow_up] Firmware work starts from origin/feat/issue-1 (2b3cbdea); the local xteink-firmware checkout is 31 commits behind it, so the worktree must branch from the remote ref
- [follow_up] culture-rules switches the daily-newspaper upload to kind=newspaper and transcripts to kind=transcript once the server ships (a culture-rules change, to be filed via the communicate skill); existing newspaper items can be re-kinded with xteink library set-kind

## Resolved vagueness

- [unknown_nonblocking] kMaxManifestEntries is 300 (xteink-firmware SyncProtocol.h:23) and Manifest::add fails past it; books, articles and dozens of transcripts a day share that cap. Does transcript volume need a higher cap or pruning, or is it a follow-up? — resolved: Follow-up issue; cap unchanged in this work (user decision 2026-10-24)
- [unknown_nonblocking] Residual: the probe ran the rebuild outside `_migrate`; the real step-3 tuple must keep single statements (store.py:64-66) and run under the same BEGIN IMMEDIATE with `foreign_keys` off on that connection — resolved: carried to plan risk r1; t1 ran step 3 inside the store migration (merged into kind/transcript)
