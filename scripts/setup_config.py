#!/usr/bin/env python3
"""Copy companion/config.json.example to config.json if it does not exist."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "companion" / "config.json.example"
TARGET = REPO_ROOT / "companion" / "config.json"


def main() -> int:
    if not EXAMPLE.is_file():
        print(f"Missing template: {EXAMPLE}", file=sys.stderr)
        return 1
    if TARGET.is_file():
        print(f"Already exists: {TARGET}")
        return 0
    shutil.copy2(EXAMPLE, TARGET)
    print(f"Created {TARGET}")
    print("Edit user_agent in config.json before running the watcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
