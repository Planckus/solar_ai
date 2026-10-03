"""README 'Supported inverters' section matches supported_inverters.json."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _renderer():
    spec = importlib.util.spec_from_file_location("render_readme", ROOT / "scripts" / "render_readme.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readme_inverter_table_is_current():
    mod = _renderer()
    assert mod.updated_readme() == (ROOT / "README.md").read_text(encoding="utf-8"), (
        "Run scripts/render_readme.py after editing supported_inverters.json"
    )
