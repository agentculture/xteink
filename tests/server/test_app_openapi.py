"""Criterion 4: the committed api/openapi.json matches the main app (CI drift check)."""

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "api" / "openapi.json"


def test_committed_schema_matches_app():
    from xteink.server.app import render_openapi

    assert (
        COMMITTED.read_text() == render_openapi()
    ), "api/openapi.json is stale; run: uv run python scripts/export-openapi.py"


def test_schema_shape():
    schema = json.loads(COMMITTED.read_text())
    paths = set(schema["paths"])
    assert {"/api/library", "/api/devices", "/api/keys"} <= paths
    assert not any(p.startswith("/api/device/") for p in paths)
    assert "servers" not in schema
    assert "HTTPBearer" in schema["components"]["securitySchemes"]


def test_export_script_check_mode():
    proc = subprocess.run(  # nosec B603
        [sys.executable, str(ROOT / "scripts" / "export-openapi.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_export_script_writes(tmp_path):
    out = tmp_path / "o.json"
    proc = subprocess.run(  # nosec B603
        [sys.executable, str(ROOT / "scripts" / "export-openapi.py"), "--output", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.read_text() == COMMITTED.read_text()
    assert out.read_text().endswith("}\n")
