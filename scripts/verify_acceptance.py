#!/usr/bin/env python3
"""Check the sealed acceptance CSV against the fingerprint Alex received independently.

Reads the file only as raw bytes to hash it. It never decodes, parses or prints the contents.
Standard library only, so it runs on any machine with Python 3 (no Docker needed).

Usage:  python3 scripts/verify_acceptance.py eval/acceptance_v1.csv eval/acceptance_v1.sha256
Exit codes: 0 = match, 2 = mismatch, 3 = a file is missing or the fingerprint file is malformed.
"""
import hashlib
import re
import sys
from pathlib import Path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def expected_sha256(path: Path) -> str | None:
    # Accepts a bare hash or the "hash  filename" output of shasum / sha256sum.
    m = re.search(r"\b[0-9a-fA-F]{64}\b", path.read_text(encoding="ascii", errors="ignore"))
    return m.group(0).lower() if m else None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[-2])
        return 3
    data, sha_file = Path(argv[1]), Path(argv[2])
    for p in (data, sha_file):
        if not p.is_file():
            print(f"MISSING: {p}")
            return 3
    expected = expected_sha256(sha_file)
    if expected is None:
        print(f"MALFORMED: no 64-character SHA-256 found in {sha_file}")
        return 3
    actual = file_sha256(data)
    print(f"File:     {data} ({data.stat().st_size} bytes)")
    print(f"Expected: {expected}")
    print(f"Actual:   {actual}")
    if actual != expected:
        print("RESULT: MISMATCH. Do not run and do not modify the file. Escalate to Alex.")
        return 2
    print("RESULT: MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
