"""Correlate fastapi and mcp logs by request_id.

Usage:
    conda run -n A2A python scripts/correlate_logs.py [logs/fastapi.log logs/mcp.log ...]

Reads each log file, extracts lines containing a request_id, groups them by
request_id, and prints a table showing which layer saw each request and its
status. Helps verify the three-layer correlation required in phase 5.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

LINE_RE = re.compile(
    r"^(?P<ts>[^|]+)\s*\|\s*(?P<layer>[^|]+)\s*\|\s*(?P<rid>[^|]+)\s*\|\s*"
    r"(?P<tool>[^|]+)\s*\|\s*(?P<status>[^|]+)\s*\|\s*(?P<dur>[^|]+)"
)


def main(paths: list[str]) -> None:
    events: dict[str, list[dict]] = defaultdict(list)
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = LINE_RE.search(line)
                    if not m:
                        continue
                    d = m.groupdict()
                    rid = d["rid"].strip()
                    if not rid:
                        continue
                    events[rid].append(d)
        except FileNotFoundError:
            print(f"[warn] missing log file: {path}", file=sys.stderr)

    print(f"{'request_id':<28} {'layer':<8} {'tool':<12} {'status':<8} {'dur':<10}")
    print("-" * 70)
    for rid, evs in events.items():
        for e in evs:
            print(
                f"{rid:<28} {e['layer'].strip():<8} {e['tool'].strip():<12} "
                f"{e['status'].strip():<8} {e['dur'].strip():<10}"
            )
        print()


if __name__ == "__main__":
    paths = sys.argv[1:] or ["logs/fastapi.log", "logs/mcp.log"]
    main(paths)
