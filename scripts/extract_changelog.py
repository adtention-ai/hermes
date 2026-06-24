#!/usr/bin/env python3
"""Extract curated release notes for a version from CHANGELOG.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\b(?:TBD|TODO|PLACEHOLDER)\b", re.IGNORECASE)


def extract_release_notes(changelog: str, version: str) -> str:
    """Return the body under ``## [version]`` from a Keep-a-Changelog file."""
    normalized = version.removeprefix("v")
    heading_re = re.compile(rf"^## \[(?:v)?{re.escape(normalized)}\](?:\s+-\s+.+)?\s*$")
    next_release_re = re.compile(r"^## \[(?:v)?\d+\.\d+\.\d+\](?:\s+-\s+.+)?\s*$")

    lines = changelog.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if heading_re.match(line):
            start = index + 1
            break

    if start is None:
        raise ValueError(f"CHANGELOG.md has no section for version {normalized}")

    end = len(lines)
    for index in range(start, len(lines)):
        if next_release_re.match(lines[index]):
            end = index
            break

    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise ValueError(f"CHANGELOG.md section for version {normalized} is empty")
    if PLACEHOLDER_RE.search(body):
        raise ValueError(f"CHANGELOG.md section for version {normalized} contains placeholder text")
    return body + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: scripts/extract_changelog.py VERSION", file=sys.stderr)
        return 2

    changelog_path = Path("CHANGELOG.md")
    if not changelog_path.exists():
        print("CHANGELOG.md not found", file=sys.stderr)
        return 1

    try:
        sys.stdout.write(extract_release_notes(changelog_path.read_text(encoding="utf-8"), argv[1]))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
