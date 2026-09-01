#!/usr/bin/env python3
"""Delete automated test cases from the live forensic database."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.app.core.repository import delete_cases_matching  # noqa: E402

PATTERNS = [
    re.compile(r"^M\d ", re.I),
    re.compile(r"^Smoke ", re.I),
    re.compile(r"^Custody gate$", re.I),
    re.compile(r"^Tool Verification$", re.I),
    re.compile(r"^verify_", re.I),
]


def main() -> int:
    removed = delete_cases_matching(PATTERNS)
    print(f"Removed {removed} test case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
