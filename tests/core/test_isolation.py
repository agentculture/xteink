import subprocess
import sys
from pathlib import Path

import xteink.core


def test_import_core_without_extras():
    code = (
        "import sys; import xteink.core; "
        "bad=[m for m in ('fastapi','uvicorn','mcp','multipart') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0  # nosec


def test_pyproject_extra_and_empty_base_deps():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    proj = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    assert proj["dependencies"] == []
    extra = " ".join(proj["optional-dependencies"]["server"])
    for dep in ("fastapi", "uvicorn", "mcp>=1.2,<2", "python-multipart"):
        assert dep in extra


def test_core_source_has_no_network_imports():
    banned = ("socket", "urllib", "http", "requests", "httpx", "asyncio")
    for py in Path(xteink.core.__file__).parent.glob("*.py"):
        for line in py.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("import", "from"):
                assert parts[1].split(".")[0] not in banned, (py.name, line)
