# t20 evidence: paragraph scroll on the X3

Date: 2026-10-07. Fork `feat/issue-1` at `43676ff6` (deviation d6 merged),
flashed app-only at 0x10000 (esptool "Hash of data verified", firmware sha256
`0d66060e…`).

In the EPUB reader the operator pressed 4.4 (next paragraph) and 4.3 (previous
paragraph) back and forth, across page boundaries, and reported: "That's
perfect! I checked back and forth."

Open observation (follow-up, not blocking): "Sometimes I need to click twice."
Two likely causes, neither confirmed: at a page seam the next page's top line
counts as a paragraph start, so the first press can show the tail of the
current paragraph; or a press that lands while a render is in progress is
dropped by the reader's turn guard.
