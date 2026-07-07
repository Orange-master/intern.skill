#!/usr/bin/env python3
"""CLI: ingest mentor docs and distill to intern-first resume material."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from mentor_distill import (  # noqa: E402
    distill_projects,
    expand,
    ingest_document,
    journal_root,
    load_index,
    mentor_paths,
    read_local_file,
    run_lark_fetch,
    scan_inbox,
)


def load_config(journal: Path) -> dict:
    for p in (journal / "config.json", _SCRIPTS.parent / "config.example.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"journal_dir": str(journal)}


def load_events(journal: Path, days: int) -> list:
    from datetime import datetime, timedelta, timezone

    path = journal / "events.jsonl"
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw = ev.get("time")
            if raw:
                try:
                    ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
            events.append(ev)
    return events


def cmd_add(args: argparse.Namespace) -> None:
    cfg = load_config(expand(args.journal))
    content: str | None = None
    source = ""
    source_type = "local"

    if args.file:
        path = expand(args.file)
        content = read_local_file(path)
        source = str(path)
        source_type = "file"
        default_name = path.stem.replace("_", " ").replace("-", " ")
    elif args.feishu:
        content, err = run_lark_fetch(args.feishu)
        if err:
            print(f"Feishu fetch failed: {err}", file=sys.stderr)
            sys.exit(1)
        source = args.feishu
        source_type = "feishu"
        default_name = "飞书文档"
    elif args.text:
        content = args.text
        source = "stdin"
        source_type = "paste"
        default_name = "未命名项目"
    else:
        print("Provide --file, --feishu, or --text", file=sys.stderr)
        sys.exit(1)

    project = args.project or default_name
    entry = ingest_document(
        cfg, project=project, content=content or "", source=source, source_type=source_type
    )
    print(f"Ingested: {entry['project']} → {entry['raw_path']}")
    print(f"  bullets={len(entry['bullets'])} metrics={len(entry['metrics'])} stack={len(entry['stack'])}")


def cmd_list(args: argparse.Namespace) -> None:
    cfg = load_config(expand(args.journal))
    _, _, _, index_path = mentor_paths(journal_root(cfg))
    index = load_index(index_path)
    for p in index.get("projects") or []:
        print(
            f"- {p.get('project')} [{p.get('slug')}] "
            f"({p.get('source_type')}) bullets={len(p.get('bullets') or [])}"
        )
    if not index.get("projects"):
        print("(empty)")


def cmd_inbox(args: argparse.Namespace) -> None:
    cfg = load_config(expand(args.journal))
    root = journal_root(cfg)
    _, _, inbox, _ = mentor_paths(root)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "done").mkdir(exist_ok=True)
    results = scan_inbox(cfg)
    if results:
        for r in results:
            print(f"Ingested from inbox: {r['project']}")
    else:
        print(f"No files in {inbox} (.md/.txt/.json)")


def cmd_distill(args: argparse.Namespace) -> None:
    cfg = load_config(expand(args.journal))
    root = journal_root(cfg)
    events = load_events(root, args.days) if args.align else []
    report = distill_projects(
        cfg,
        subject=args.subject,
        events=events,
        align_signals=args.align,
    )
    out = expand(args.output) if args.output else root / "reports" / f"mentor-distill-{args.subject}.md"
    out = Path(str(out).replace("{subject}", args.subject))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Mentor distill → {out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest mentor/employee docs; distill to intern-first resume bullets.",
    )
    parser.add_argument("--journal", default="~/.实习生-skill")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Import a mentor document")
    p_add.add_argument("--project", "-p", help="Project name for resume")
    p_add.add_argument("--file", "-f", help="Local .md/.txt file")
    p_add.add_argument("--feishu", help="Feishu doc/wiki URL or token")
    p_add.add_argument("--text", "-t", help="Paste raw text")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List ingested mentor projects")
    p_list.set_defaults(func=cmd_list)

    p_inbox = sub.add_parser("inbox", help="Scan mentor/inbox/ for new files")
    p_inbox.set_defaults(func=cmd_inbox)

    p_distill = sub.add_parser("distill", help="Generate intern-first resume draft")
    p_distill.add_argument("--subject", default="实习生", help="Report subject name")
    p_distill.add_argument("--days", type=int, default=30, help="Days of signals for alignment")
    p_distill.add_argument("--no-align", dest="align", action="store_false", help="Skip signal alignment")
    p_distill.add_argument("--output", "-o", help="Output path")
    p_distill.set_defaults(func=cmd_distill, align=True)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
