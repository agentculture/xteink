# t20 evidence: zoom mode on the X3

Date: 2026-10-07. Firmware `1.6.5-dev-feat/issue-1-fd17732e`.

On this build zoom mode is bound to logical Up, which the X3 key-logger
session measured as the left edge key (`docs/evidence/x3-key-mapping-serial.txt`).
The operator opened zoom mode with that key in the EPUB reader, stepped the
font size, applied it, and reported that it works as expected (the reflow
keeps the reading position).

The binding moves to a long press of 4.2 (OK) in the X3 key profile
(deviation d5); re-check zoom after that build is flashed.
