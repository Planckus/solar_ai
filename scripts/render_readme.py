#!/usr/bin/env python3
"""Render the 'Supported inverters' section of README.md from supported_inverters.json.

Usage:
    python3 scripts/render_readme.py          # rewrite the section in place
    python3 scripts/render_readme.py --check  # exit 1 if README.md is out of date
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "supported_inverters.json"
README = ROOT / "README.md"
START = "<!-- supported-inverters:start -->"
END = "<!-- supported-inverters:end -->"
STATUS = {
    "tested": "Tested",
    "supported": "Supported",
    "untested": "Untested",
    "planned": "Planned, not available",
    "not supported": "Not supported",
}


def _cell(text: str) -> str:
    return (text or "—").replace("|", "\\|").replace("\n", " ")


def render() -> str:
    rows = json.loads(DATA.read_text(encoding="utf-8"))["inverters"]
    out = [
        START,
        "<!-- Generated from supported_inverters.json by scripts/render_readme.py. Do not edit by hand. -->",
        "",
        "| Status | Brand | Model | Connection | Firmware | Verified with | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        status = STATUS.get(r["status"], r["status"])
        version = f"v{r['verified_with']}" if r.get("verified_with") else ""
        out.append(
            f"| {status} | {_cell(r['brand'])} | {_cell(r['model'])} | {_cell(r.get('connection'))} "
            f"| {_cell(r.get('firmware'))} | {_cell(version)} | {_cell(r.get('notes'))} |"
        )
    out.append(END)
    return "\n".join(out)


def updated_readme() -> str:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        sys.exit(f"README.md is missing the {START} / {END} markers")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return head + render() + tail


def main() -> int:
    new = updated_readme()
    if "--check" in sys.argv[1:]:
        if new != README.read_text(encoding="utf-8"):
            print("README.md 'Supported inverters' section is out of date; run scripts/render_readme.py")
            return 1
        return 0
    README.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
