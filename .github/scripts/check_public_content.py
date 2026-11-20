"""Check the lines a change adds for content that must not be published.

Fails on:
- private IPv4 addresses (10/8, 172.16/12, 192.168/16); placeholders such
  as 192.168.x.x pass;
- names, addresses and terms on the project's block list. The list holds
  SHA-256 hashes only, so the repository never contains the terms
  themselves. A word, a dotted address or two adjacent words are hashed in
  lower case and compared.

Warns, without failing, on figures that may come from one installation and
need a human look: ISO dates outside CHANGELOG release headings and test
code, DKK amounts and kWh figures in documentation.

Usage: check_public_content.py BASE_REF   (compares BASE_REF...HEAD)
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

BLOCKED_SHA256 = {
    "c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d",
    "c70eca6b0f88f44d81a41311647e50fda1ac454ec04ffd442b0eb4743a993131",
    "cd29c5ac348a026a3ec5286890908fffb5bf6ab77f20672171be323a70c95026",
    "3538fc5a371fc3846052bab566d2a52815559824423d39181deea0505a028a55",
    "e17c76431e012011420408bc51227efe9ba118f461a8019b6d1d5c25f800951f",
}

PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3})\b"
)
ISO_DATE = re.compile(r"\b20\d\d-[01]\d-[0-3]\d\b")
DKK_AMOUNT = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:DKK|kr\b)", re.IGNORECASE)
KWH_FIGURE = re.compile(r"\b\d+(?:[.,]\d+)?\s?kWh\b")
TOKEN = re.compile(r"[a-z0-9_.+@-]+")
SELF = ".github/scripts/check_public_content.py"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def blocked(line: str) -> bool:
    words = TOKEN.findall(line.lower())
    candidates = set(words)
    candidates.update(w.strip(".,;:") for w in words)
    candidates.update(f"{a} {b}" for a, b in zip(words, words[1:]))
    return any(_sha(c) in BLOCKED_SHA256 for c in candidates)


def added_lines(base: str):
    """Yield (path, line number, text) for every line added since base."""
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    path, line_no = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            line_no = int(re.search(r"\+(\d+)", raw).group(1))
        elif raw.startswith("+") and path:
            yield path, line_no, raw[1:]
            line_no += 1


def commit_messages(base: str):
    log = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01", f"{base}..HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    for record in filter(None, (r.strip() for r in log.split("\x01"))):
        sha, _, body = record.partition("\x00")
        yield sha[:8], body


def main() -> int:
    base = sys.argv[1]
    errors = warnings = 0
    for path, line_no, text in added_lines(base):
        if path == SELF:
            continue
        where = f"file={path},line={line_no}"
        if PRIVATE_IP.search(text):
            print(f"::error {where}::Private IP address in a public file")
            errors += 1
        if blocked(text):
            print(f"::error {where}::Blocked name, address or term")
            errors += 1
        is_doc = path.endswith(".md")
        is_test = path.startswith("tests/")
        if (ISO_DATE.search(text) and not is_test
                and not (path == "CHANGELOG.md" and text.startswith("## ["))):
            print(f"::warning {where}::Date: check it is not an event from one installation")
            warnings += 1
        if is_doc and DKK_AMOUNT.search(text):
            print(f"::warning {where}::DKK amount: check it is a setting, tariff or tax, not one installation's price")
            warnings += 1
        if is_doc and KWH_FIGURE.search(text):
            print(f"::warning {where}::kWh figure: check it is not one installation's battery or result")
            warnings += 1
    for sha, body in commit_messages(base):
        for line in body.splitlines():
            if PRIVATE_IP.search(line) or blocked(line):
                print(f"::error::Commit {sha}: private IP or blocked term in the message")
                errors += 1
                break
    print(f"Public content: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
