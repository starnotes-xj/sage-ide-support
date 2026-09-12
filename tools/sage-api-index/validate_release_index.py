#!/usr/bin/env python3
"""Fail closed when a Marketplace release index is incomplete or unsanitized."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


HOST_PATH = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?<![A-Za-z0-9.-])/(?:home|users|private|tmp|var|opt|workspace|work|mnt|media|volumes|usr/local)/)",
    re.IGNORECASE,
)
MIN_FULL_INDEX_BYTES = 64 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_host_path(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            found = find_host_path(child)
            if found:
                return f"{key}: {found}"
    elif isinstance(value, list):
        for child in value:
            found = find_host_path(child)
            if found:
                return found
    elif isinstance(value, str):
        match = HOST_PATH.search(value)
        if match:
            return value[max(0, match.start() - 24) : match.end() + 96]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="expected lowercase SHA-256")
    parser.add_argument("--minimum-bytes", type=int, default=MIN_FULL_INDEX_BYTES)
    parser.add_argument("--minimum-entries", type=int, default=80_000)
    args = parser.parse_args()

    expected = args.sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("--sha256 must be a SHA-256 hex digest")
    if args.minimum_bytes < 1 or args.minimum_entries < 1:
        raise ValueError("release index minimums must be positive")
    if not args.index.is_file() or args.index.stat().st_size < args.minimum_bytes:
        raise ValueError("release index is missing or too small to be the full Sage API index")
    actual = sha256(args.index)
    if actual != expected:
        raise ValueError(f"release index SHA-256 mismatch: expected {expected}, got {actual}")

    with args.index.open(encoding="utf-8") as stream:
        index = json.load(stream)
    if not isinstance(index, dict) or index.get("schemaVersion") != 1:
        raise ValueError("release index is not schemaVersion 1")
    if index.get("sageVersion") != "10.9" or index.get("pythonVersion") != "3.13":
        raise ValueError("release index must be generated for Sage 10.9 / Python 3.13")
    if not isinstance(index.get("entries"), list) or len(index["entries"]) < args.minimum_entries:
        raise ValueError("release index does not contain the expected full API entry set")
    remaining = find_host_path(index)
    if remaining:
        raise ValueError(f"release index leaks a host-local path: {remaining!r}")

    print(json.dumps({
        "entryCount": len(index["entries"]),
        "pythonVersion": index["pythonVersion"],
        "sageVersion": index["sageVersion"],
        "sha256": actual,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
