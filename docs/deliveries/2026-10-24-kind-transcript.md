# Delivery Summary — kind transcript

plan: `kind-transcript` · run: `complete` · date: `2026-10-24`
baseline: `devague summary skeleton`

## Intent

> Transcripts and newspapers get their own folders on the reader: the xteink server accepts kind=transcript and kind=newspaper and sends each item's kind in its device queue entry, and the X3 firmware files articles under /xteink/articles/, transcripts under /xteink/transcripts/ and newspapers under /xteink/newspapers/, while books stay in /xteink/ (issue 8)

After: After one daily sync, a transcript sits in /xteink/transcripts/, a newspaper in /xteink/newspapers/, an article in /xteink/articles/ and a book stays in /xteink/, and an older firmware still syncs all four flat without error

## Planned Work

- `t1` — Schema v3: items-table rebuild for four kinds + pre-migration backup (xteink/core/store.py)
- `t2` — Core: KINDS gains transcript/newspaper, queue entries carry kind, library.`set_kind` (models.py, devices.py, library.py)
- `t3` — Server routes: four-kind Literal, PATCH /api/library/{id} kind, kind in device queue entries, regenerate api/openapi.json
- `t4` — CLI + MCP: four kinds, xteink library set-kind verb, client.`set_kind`, explain catalog
- `t5` — Web UI: Transcript and Newspaper kinds in the API type, library labels, filter and Add form
- `t6` — Docs: kind in the device protocol (v1 additive), API and MCP docs for four kinds and PATCH
- `t7` — Firmware protocol: QueueItem parses kind, pure kind-to-folder helper, host tests (xteink-firmware SyncProtocol)
- `t8` — Firmware placement: placeFile files by kind folder, clash rule inside it, sync.md (xteink-firmware XteinkSync)
- `t9` — Ship and verify on the X3: server PR + deploy, firmware PR + xteink firmware release, 4-kind sync, evidence file
- `t10` — Follow-up issues: culture-rules switch to kind=transcript/newspaper, and the 300-entry manifest cap

## Actual Delivery

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | Schema step 3 (six statements, `d1`) and `_backup_if_pending`; `SCHEMA_VERSION` 3. PR #11 (`b1d62e6`) |
| `t2` | delivered | KINDS of four, `QueueEntry.kind`, `library.set_kind`; the CLI KINDS line moved here (`d3`). PR #11 |
| `t3` | delivered | Four-kind Literal, `PATCH /api/library/{id}`, `kind` in device queue entries, `api/openapi.json` regenerated. PR #11 |
| `t4` | delivered | `xteink library set-kind`, `client.set_kind`, MCP `_KIND` enum, explain entry (stale `image` kind dropped). PR #11 |
| `t5` | delivered | Web Kind type, `KIND_LABELS`, Library filter and Add form options. PR #11 |
| `t6` | delivered | `docs/device-protocol.md`, `docs/api.md`, `docs/mcp.md`, prompt files. PR #11 |
| `t7` | delivered | `ItemKind`, `parseItemKind`, `kindFolder`, host tests. Fork PR #5 (`ef7ff339`) |
| `t8` | delivered | `placeFile` per kind folder (recursive mkdir, not-a-folder check), `docs/xteink/sync.md` step 4. Fork PR #5 |
| `t9` | delivered | Deploy with backup and migration, release of image 6 `1.6.5+xteink.ef7ff339`, OTA, 4-kind sync, mirror deletes; evidence steps 1-7 in `docs/evidence/kind-transcript-validation.md`. PRs #11, #12 |
| `t10` | delivered | culture-rules#89 (kind=transcript/newspaper uploads) and xteink#10 (300-entry manifest cap), posted with the operator's go-ahead |

## Mid-work Decisions

- `d1` — t1 step 3 has six statements, not the four in its instruction: two `sqlite_sequence` statements (DELETE the `items_new` row, rename the items row to `items_new`) carry the AUTOINCREMENT high-water mark across the rebuild — without them the rebuild resets `sqlite_sequence` to max(id), so an id freed by deleting the highest item would be reused, breaking t1's own criterion 'not a reused id'; guarded by `test_rebuild_keeps_the_autoincrement_high_water_mark`
- `d2` — xteink/core/firmware.py:3-4 docstring still says items.kind is CHECK-constrained to book/article; no task owns that file, so the main agent fixes the one docstring line on the integration branch — t1's instruction limited it to store.py and two test files; the stale docstring is now false
- `d3` — At the t2 merge the main agent also widens the CLI's KINDS tuple (xteink/cli/`_commands`/library.py:18) to the four kinds, a one-line change from t4's file set, so the full suite stays green after t2; t4 keeps everything else (set-kind verb, MCP, explain, client) — t2 widens core KINDS, and tests/cli/`test_nouns.py`::`test_library_kind_choices_match_the_server` requires the CLI tuple to equal it; with the plan's split the suite fails between t2 and t4, which the after-merge test gate forbids
- `d4` — t9 runs the OTA before any sync on the old firmware: the on-device old-firmware compat check (h5) is not observed; the 3 real queued items (2 Pocket transcripts, 1 daily newspaper, uploaded as article) are re-kinded and delivered by the new firmware instead — the X3's daily run already happened today (04:54Z), so the check needs a manual sync, and the old firmware would file those 3 real items flat in /xteink/ for good (c11); the operator chose to keep them for the per-kind folders. h5 rests on host evidence: parseQueue reads keys by name and the live queue already carries kind

- Not covered by a record: the 300-entry manifest cap, review fixes on fork PR #5 (folder-is-file check, logging, `kBooksDir` moved to `SyncProtocol.h`), and pinning the fork's cppcheck job to `ubuntu-24.04` after `ubuntu-latest` dropped `libpcre3`.
- After delivery, the operator decided xteink's library is the private device store, fed by culture-rules from culture-library (xteink#3, culture-rules#86, culture-library#9). Recorded in the prompt files by PR #12. It is outside this plan's tasks.

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|------------------------|-----------------|
| `t1` (`d1`) | without them the rebuild resets `sqlite_sequence` to max(id), so an id freed by deleting the highest item would be reused, breaking t1's own criterion 'not a reused id'; guarded by `test_rebuild_keeps_the_autoincrement_high_water_mark` | `acceptable` |
| `t1` (`d2`) | t1's instruction limited it to store.py and two test files; the stale docstring is now false | `acceptable` |
| `t2` (`d3`) | t2 widens core KINDS, and tests/cli/`test_nouns.py`::`test_library_kind_choices_match_the_server` requires the CLI tuple to equal it; with the plan's split the suite fails between t2 and t4, which the after-merge test gate forbids | `acceptable` |
| `t9` (`d4`) | the X3's daily run already happened today (04:54Z), so the check needs a manual sync, and the old firmware would file those 3 real items flat in /xteink/ for good (c11); the operator chose to keep them for the per-kind folders. h5 rests on host evidence: parseQueue reads keys by name and the live queue already carries kind | `risky` |
| `t9` (`l1`) | `d4` meant to skip the old-firmware sync, but Check for updates synced first, so the 5 queued items (29, 53-56) landed flat; h5 was observed on hardware after all (behavioral delta `b1`) | `acceptable` |

## Evidence

- tests: full server suite on `d5c2945` — 615 passed, 3 skipped (report-only cross-repo gaps); kind subset 56 passed
- tests: `web` vitest — 70 passed
- tests: firmware host ctest at `ef7ff339` — 711/711 passed, including `XteinkSyncQueue.ParsesKind`, `XteinkSyncQueue.AbsentUnknownOrNonStringKindIsBook`, `XteinkSyncKind.FolderPerKind`, `XteinkSyncKind.EveryFolderIsUnderTheBooksDir`
- lint and CI: PR #11 12 checks passed, PR #12 11 passed; fork PR #5 17 checks passed
- hardware: `docs/evidence/kind-transcript-validation.md` steps 2-7 (X3 serial log, operator observations)
- devague: obligations `o1`-`o13`, evidence `e1`-`e15`, delta `b1`, all approved by the operator
- commits: `f16fd66..d5c2945` (xteink main), `2b3cbdea..ef7ff339` (fork `feat/issue-1`)
- PRs / issues: #11, #12, fork #5, issue #8, #10, culture-rules#89

## Delivery Claims

| Claim | Confidence | Evidence |
|-------|------------|----------|
| `c2` — Schema step 3 in xteink/core/store.py `_MIGRATIONS` rebuilds the items table with CHECK (kind IN ('book','article','transcript','newspaper')), because SQLite can't ALTER a CHECK and `_SCHEMA` (store.py:16-18) is never edited; the rebuild keeps items.id values, `sqlite_sequence` and the queue.`item_id` FK rows (store.py:47) intact; tests/core/`test_firmware.py`::`test_firmware_never_goes_into_items` (asserts the old CHECK text, :246) is updated and a new migration test covers an issue-1/v2 DB with queue rows | high | `tests/core/test_store_v3.py (v2 migrate, v0/v1 through step 3, autoincrement high-water, foreign keys)` (run 2026-10-24) |
| `c3` — transcript and newspaper are accepted everywhere a kind is enumerated: xteink/core/models.py:7 KINDS, `routes_library.py`:40 Kind Literal (upload + list filter), cli/`_commands`/library.py:18 KINDS (kept equal by tests/cli/`test_nouns.py`:317), mcp/tools.py:12 `_KIND` enum, web/src/services/api.ts:21 Kind; api/openapi.json is regenerated (export-openapi.py --check); any other value is still refused with 422 | high | `tests/server/test_app_routes.py::test_upload_accepts_new_kinds, ::test_upload_rejects_comic_kind, ::test_kind_literal_matches_core_kinds; tests/cli/test_nouns.py::test_library_kind_choices_match_the_server; tests/core/test_store_v3.py::test_four_kinds_are_accepted` (run 2026-10-24) |
| `c4` — Each device queue entry carries kind: xteink/core/devices.py `_Q` (:12-15) selects i.kind, QueueEntry (core/models.py:50-62) gains kind, `routes_device.py` `get_queue` (:262-271) emits it, with 'book' when the item has none; tests/server/`test_device_protocol.py`::`test_queue_shape` is updated | high | `tests/server/test_device_protocol.py::test_queue_entries_carry_kind; tests/core/test_devices.py::test_queue_entries_carry_the_item_kind, ::test_set_kind_shows_in_the_queue` (run 2026-10-24) |
| `c5` — The device protocol stays v1 (`PROTOCOL_VERSION` '1', `routes_device.py`:33): kind is an additive field like the OTA additions (`routes_device.py`:12-13, docs/device-protocol.md changelog :222-231); older firmware ignores it because parseQueue (xteink-firmware SyncProtocol.cpp) reads JSON keys by name with ArduinoJson and skips unknown ones; docs/device-protocol.md gets the field and a changelog line | high | `X3 serial log on firmware 2b3cbdea, evidence step 3` |
| `c6` — Dedup by sha256 is unchanged: xteink/core/library.py:52-56 looks up by sha256 only, so re-uploading the same bytes returns the existing item (created: false) with its original kind, whatever kind the new upload names | high | `tests/core/test_library.py::test_same_bytes_as_another_kind_dedups_to_the_original` (run 2026-10-24) |
| `c7` — Clients show transcripts and newspapers as their own kinds: web/src/views/LibraryView.tsx:200 (item.kind === 'article' ? 'Article' : 'Book' would label them Book) becomes a kind-to-label map, the filter radios (:87-94) and AddView.tsx option list (:118-121) gain Transcript and Newspaper, and docs/api.md (:100,:122,:135), docs/mcp.md (:114) and xteink/explain/catalog.py:164 (whose stale 'image' kind is dropped) list book\|article\|transcript\|newspaper | high | `web/src/views/LibraryView.test.tsx, AddView.test.tsx (vitest, 70 passed)` (run 2026-10-24) |
| `c8` — Firmware QueueItem (xteink-firmware src/xteink/SyncProtocol.h:118, origin/feat/issue-1) parses an optional kind, where absent, unknown or wrong-typed means book, and a pure helper in SyncProtocol.{h,cpp} maps kind to folder (/xteink, /xteink/articles, /xteink/transcripts, /xteink/newspapers) so test/`xteink_sync`/XteinkSyncTest.cpp (host GoogleTest, no Storage) covers the per-kind path choice | high | `firmware ctest XteinkSyncQueue.ParsesKind, XteinkSyncQueue.AbsentUnknownOrNonStringKindIsBook (711/711)` (run 2026-10-24) |
| `c9` — Firmware placeFile (XteinkSync.cpp:489, origin/feat/issue-1) creates /xteink and then the kind subfolder on demand (Storage.mkdir is non-recursive), and applies the bookFileName / bookFileNameWithId clash rule and the never-overwrite-sideloaded-or-modified check inside that folder; docs/xteink/sync.md step 4 (:58-60) names the per-kind folders | high | `firmware ctest XteinkSyncKind.FolderPerKind, XteinkSyncKind.EveryFolderIsUnderTheBooksDir` (run 2026-10-24) |
| `c10` — Manifest, inventory, re-hash and mirror-delete need no change: DeliveredFile stores the full path, and every walk (XteinkSync.cpp:612 inventory, :819 deletes, origin/feat/issue-1) iterates manifest.files rather than scanning /xteink, so subfolder files work as they are | high | `X3 serial log, evidence steps 6 and 7` |
| `c12` — Files in /xteink/articles and /xteink/transcripts appear in the reader's library because LibraryBuilder.cpp:242 is described as a recursive walk and the sync marks the index dirty (XteinkSync.cpp); this is unverified on the X3 | medium | `X3 serial log + operator, evidence step 5` |
| `c17` — On the X3, 1 item of each of the 4 kinds pushed in one sync lands in its own folder (4 folders) on the first try (0 SD errors), and the full server suite plus the firmware ctest suite pass, with ≥ 1 new test per acceptance criterion in issue 8 | medium | `X3 serial log, evidence step 5; full suites 615 passed / 711 passed` |
| `c20` — PATCH /api/library/{id} accepts {kind} (any value in KINDS: book\|article\|transcript\|newspaper; 422 otherwise) and xteink library set-kind ID KIND (dry-run unless --apply, MCP not required) calls it; the item record and every queue entry then carry the new kind. Files already on a device stay where they are (c11): re-queueing to the same device does not move the file, because the firmware finds its sha256 in the manifest and acks it in place (XteinkSync.cpp alreadyHere). A re-kinded item lands in its new folder only on a device that does not already hold it | high | `tests/server/test_app_routes.py::test_patch_kind, ::test_patch_kind_errors, ::test_patch_kind_requires_auth; tests/cli/test_nouns.py::test_library_set_kind_*; tests/core/test_library.py::test_set_kind_*` (run 2026-10-24) |
| `c22` — Before applying any pending schema step, the Store copies library.db to library.db.v2.bak (named after the version being migrated from; sqlite3 backup API, same data dir), so rolling the server image back after the v3 rebuild has a restore path: an older xteink refuses a newer schema (store.py:111-115) and there is no backup of library.db today | high | `tests/core/test_store_v3.py::test_pending_step_writes_a_backup_of_the_old_db (+ v0 naming, up-to-date and new db write none)` (run 2026-10-24) |

`c12` and `c17` are `medium`: the firmware logs no per-file path, so placement rests on the operator seeing the three folders and on the subfolder mirror deletes succeeding. `c5` was observed only because of lapse `l1`.

Lapse ledger evidence:

| Lapse | Code | What |
|-------|------|------|
| `l1` | `assumption-for-measurement` | Main agent told the operator that Settings > Check for updates only installs the offered image; on the X3 it ran a full sync on the old firmware first (Queue: 5 items, Sync done: OK, 4 new) and only then installed ef7ff339, so the 5 queued items were filed flat in /xteink/, which is what deviation d4 meant to avoid |

## Remaining Work / Follow-up

- culture-rules#89: upload transcripts as `kind=transcript` and the newspaper as `kind=newspaper`. Owner: culture-rules.
- culture-rules#86: the send-to-device rule (library → xteink upload and queue) and the delete rule that follows the library feed. Owner: culture-rules. After it lands, retire `ebooks.culture.dev` (xteink#3).
- xteink#10: the 300-entry firmware manifest cap. Follow-up.
- Items delivered before ef7ff339 stay flat in `/xteink/` (c11, by design). The 33 recordings were removed from the reader, and remain in culture-library.
- Some `Daily newspaper …` EPUBs the operator saw on the X3 are not in the sync inventory. Their origin is unknown; they are deleted by hand.
- Optional: log the placed path in the firmware, so folder placement can be checked from the serial log.
