"""``xteink learn`` — the learnability affordance.

Prints a structured self-teaching prompt. Must satisfy the agent-first rubric:
>=200 chars and mention purpose, command map, exit codes, --json, and explain.
"""

from __future__ import annotations

import argparse

from xteink import __version__
from xteink.cli._output import emit_result

_TEXT = """\
xteink — private, local-first control for Xteink e-ink readers.

Purpose
-------
Keep your e-book library on hardware you own: a local book server, optional
remote access through a Cloudflare Tunnel, and custom reader firmware that syncs
books over Wi-Fi so reading works fully offline. xteink is also an AgentCulture
mesh agent. The library server (HTTP API, device-only sync app, web UI), the MCP
server and this CLI ship today; the reader firmware lives in the
agentculture/xteink-firmware fork and is pending hardware verification.

Commands
--------
  xteink whoami             Identity from culture.yaml.
  xteink learn              This self-teaching prompt.
  xteink explain <path>...  Markdown docs for any noun/verb path.
  xteink overview           Descriptive snapshot of the agent.
  xteink doctor             Check the agent-identity invariants.
  xteink cli overview       Describe the CLI surface itself.
  xteink server status      Is the API reachable and the key valid?
  xteink library ...        list | add PATH | rm ID  (writes need --apply)
  xteink device ...         list | queue | revoke | backup | provision
  xteink tunnel ...         status | plan  (prints cultureflare commands)
  xteink mcp serve          Run the MCP server (needs xteink[server])

Writes are dry-run by default: they print what would happen and change nothing
until you pass --apply. The CLI talks to the API at XTEINK_URL with
XTEINK_API_KEY.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr never mix.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  xteink explain xteink
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "xteink",
        "version": __version__,
        "purpose": "Private, local-first control for Xteink e-ink readers.",
        "commands": [
            {"path": ["whoami"], "summary": "Identity probe from culture.yaml."},
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {"path": ["overview"], "summary": "Descriptive snapshot of the agent."},
            {"path": ["doctor"], "summary": "Check the agent-identity invariants."},
            {"path": ["cli", "overview"], "summary": "Describe the CLI surface."},
            {"path": ["server", "status"], "summary": "API reachability and key check."},
            {"path": ["library"], "summary": "List, add (--apply) and remove (--apply) items."},
            {"path": ["device"], "summary": "Readers: list, queue, revoke, backup, provision."},
            {"path": ["tunnel"], "summary": "Remote access status and cultureflare plan."},
            {"path": ["mcp", "serve"], "summary": "Run the MCP server."},
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "xteink explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
