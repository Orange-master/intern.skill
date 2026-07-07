#!/usr/bin/env python3
"""Compute daily collect time from config schedule (work_end - N minutes)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def collect_schedule(cfg: dict[str, Any]) -> tuple[int, int, str, str]:
    """
    Returns (hour, minute, work_end, collect_time HH:MM).
    Default work_end 19:00 → collect 18:30.
    """
    sched = cfg.get("schedule") or {}
    work_end = str(sched.get("work_end") or "19:00").strip()
    before = int(sched.get("collect_before_minutes") or 30)

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            end = datetime.strptime(work_end, fmt)
            break
        except ValueError:
            end = None
    if end is None:
        work_end = "19:00"
        end = datetime.strptime(work_end, "%H:%M")

    collect_at = end - timedelta(minutes=before)
    return collect_at.hour, collect_at.minute, work_end, collect_at.strftime("%H:%M")


def main() -> None:
    path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    cfg: dict[str, Any] = {}
    if path and path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    hour, minute, work_end, collect_time = collect_schedule(cfg)
    # hour minute work_end collect_time
    print(f"{hour} {minute} {work_end} {collect_time}")


if __name__ == "__main__":
    main()
