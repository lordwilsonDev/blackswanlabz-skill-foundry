"""Shared verdict vocabulary and the exit-code contract.

The exit code IS part of the result. A consumer that only reads the exit code
must never see success for a result that is not success.

    0  PASS / FAITHFUL / ROUTED                    safe to consume
    1  FAIL / UNFAITHFUL                           defect found
    2  BLOCKED / UNKNOWN / UNVERIFIED /            not consumable yet
       NO_MATCH / NEEDS_QUESTION
    3  INPUT_ERROR                                 the harness could not run
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXIT_CODES = {
    "PASS": 0,
    "FAITHFUL": 0,
    "ROUTED": 0,
    "FAIL": 1,
    "UNFAITHFUL": 1,
    "BLOCKED": 2,
    "UNKNOWN": 2,
    "UNVERIFIED": 2,
    "NO_MATCH": 2,
    "NEEDS_QUESTION": 2,
    "PENDING": 2,
    "INPUT_ERROR": 3,
}


def exit_code(verdict: str) -> int:
    """Unknown verdict labels fail closed (2), never open (0)."""
    return EXIT_CODES.get(verdict, 2)


def stable_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp to an aware UTC datetime; None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def default_registry_path() -> Path:
    """One registry for every project, so a question id cannot mean different
    things in different folders. HARNESS_REGISTRY overrides. The default lives in
    PZS (committed and pushed by pzs-autocommit) when it exists."""
    override = os.environ.get("HARNESS_REGISTRY")
    if override:
        return Path(override).expanduser()
    pzs = Path.home() / "FREEBUFF_PZS"
    base = pzs / "state" if pzs.is_dir() else Path.home() / ".harness"
    return base / "qe-registry.json"


def now_utc() -> datetime:
    """Current time; HARNESS_NOW (ISO) pins it for reproducible runs and tests."""
    pinned = parse_ts(os.environ.get("HARNESS_NOW", ""))
    return pinned or datetime.now(timezone.utc)
