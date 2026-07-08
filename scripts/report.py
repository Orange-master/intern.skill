#!/usr/bin/env python3
"""Generate daily/weekly work reports and optionally publish to Feishu docs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from collect import (  # noqa: E402
    FEISHU_TYPES,
    SESSION_LABELS,
    load_events_for_day,
    merge_events_for_digest,
    parse_event_time,
)
from summarize import (  # noqa: E402
    AGENT_LABELS,
    AGENT_TYPES,
    extract_themes,
    feishu_summary,
    git_summary,
    load_config,
    load_events,
    top_projects,
)


def expand(p: str) -> Path:
    return Path(p).expanduser()


def week_bounds(
    anchor: datetime, tz_name: str = "Asia/Shanghai"
) -> tuple[datetime, datetime]:
    """Monday 00:00 through Sunday 23:59:59 in local tz."""
    tz = ZoneInfo(tz_name)
    local = anchor.astimezone(tz)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def load_events_between(
    journal: Path, start: datetime, end: datetime, tz_name: str = "Asia/Shanghai"
) -> list[dict[str, Any]]:
    path = journal / "events.jsonl"
    if not path.exists():
        return []
    tz = ZoneInfo(tz_name)
    start_local = start.astimezone(tz)
    end_local = end.astimezone(tz)
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_event_time(ev.get("time"))
            if not ts:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            local_date = ts.astimezone(tz).date()
            if start_local.date() <= local_date <= end_local.date():
                events.append(ev)
    return events


def pending_tasks(limit: int = 8) -> list[str]:
    """Best-effort fetch of incomplete Feishu tasks via lark-cli."""
    try:
        proc = subprocess.run(
            [
                "lark-cli",
                "task",
                "+get-my-tasks",
                "--complete=false",
                "--format",
                "json",
                "--as",
                "user",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    blob = (proc.stdout or proc.stderr or "").strip()
    if not blob:
        return []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    tasks = data.get("data") or data.get("tasks") or []
    if isinstance(tasks, dict):
        tasks = tasks.get("items") or tasks.get("tasks") or []
    lines: list[str] = []
    for t in tasks[:limit]:
        if not isinstance(t, dict):
            continue
        summary = (t.get("summary") or t.get("title") or "").strip()
        due = t.get("due") or t.get("due_time") or t.get("due_date") or ""
        if isinstance(due, dict):
            due = due.get("timestamp") or due.get("date") or ""
        due_text = f"（截止：{str(due)[:10]}）" if due else ""
        if summary:
            lines.append(f"- [ ] {summary}{due_text}")
    return lines


def agent_bullets(agent_events: list[dict[str, Any]], limit: int = 6) -> list[str]:
    lines: list[str] = []
    for ev in agent_events:
        label = AGENT_LABELS.get(ev.get("type", ""), "Agent")
        project = ev.get("project") or "unknown"
        queries = ev.get("queries") or []
        if queries:
            preview = (queries[0].get("preview") or "").strip()[:120]
            lines.append(f"- **{label}** · `{project}` · {preview}")
        else:
            lines.append(f"- **{label}** · `{project}` · {ev.get('query_count', 0)} 条协作")
        if len(lines) >= limit:
            break
    return lines


def build_daily_report(
    events: list[dict[str, Any]],
    *,
    subject: str,
    day: datetime,
    cfg: dict[str, Any] | None = None,
) -> str:
    cfg = cfg or {}
    role = cfg.get("_role") or {}
    tz_name = (cfg.get("feishu") or {}).get("timezone", "Asia/Shanghai")
    day_str = day.strftime("%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][day.weekday()]

    agent = [e for e in events if e.get("type") in AGENT_TYPES]
    git_ev = [e for e in events if e.get("type") == "git_commits"]
    feishu = [e for e in events if e.get("type") in FEISHU_TYPES]

    cal_lines, task_lines, msg_lines, doc_lines = feishu_summary(feishu)
    git_bullets = git_summary(git_ev)
    themes = extract_themes(
        [q.get("preview", "") for e in agent for q in (e.get("queries") or [])],
        cfg,
    )
    pending = pending_tasks()

    lines = [
        f"# 工作日报 · {subject} · {day_str}（{weekday}）",
        "",
        f"> 自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if role.get("title"):
        lines.append(f"> 岗位：{role['title']}")
    lines.extend(["", "## 今日完成", ""])

    done: list[str] = []
    if task_lines:
        done.extend(task_lines[:8])
    if git_bullets:
        done.extend(git_bullets[:6])
    if doc_lines:
        done.extend([f"- 文档：{d.lstrip('- ')}" for d in doc_lines[:4]])
    if not done:
        done.append("- _今日暂无可自动归纳的完成项，请手动补充。_")
    lines.extend(done)

    lines.extend(["", "## 会议与协作", ""])
    if cal_lines:
        lines.extend(cal_lines[:10])
    elif msg_lines:
        lines.extend(msg_lines[:6])
    else:
        lines.append("- _未采集到会议/协作记录。_")

    lines.extend(["", "## 代码与交付", ""])
    if git_bullets:
        lines.extend(git_bullets)
    else:
        lines.append("- _今日无 Git 提交记录。_")

    lines.extend(["", "## Agent 协作摘要", ""])
    agent_lines = agent_bullets(agent)
    if agent_lines:
        lines.extend(agent_lines)
        if themes:
            lines.append(f"- 主题聚类：{' · '.join(themes[:4])}")
    else:
        lines.append("- _今日无 Agent 协作记录。_")

    lines.extend(["", "## 文档沉淀", ""])
    if doc_lines:
        lines.extend(doc_lines)
    else:
        lines.append("- _今日未编辑飞书文档。_")

    lines.extend(["", "## 明日计划", ""])
    if pending:
        lines.extend(pending)
    else:
        lines.append("- _（待补充，或运行 `lark-cli auth login --domain task` 后自动拉取待办）_")

    lines.extend(["", "## 风险与阻塞", "", "- _无_", ""])
    return "\n".join(lines)


def build_weekly_report(
    events: list[dict[str, Any]],
    *,
    subject: str,
    start: datetime,
    end: datetime,
    cfg: dict[str, Any] | None = None,
) -> str:
    cfg = cfg or {}
    role = cfg.get("_role") or {}
    tz_name = (cfg.get("feishu") or {}).get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name)

    agent = [e for e in events if e.get("type") in AGENT_TYPES]
    git_ev = [e for e in events if e.get("type") == "git_commits"]
    feishu = [e for e in events if e.get("type") in FEISHU_TYPES]

    cal_lines, task_lines, msg_lines, doc_lines = feishu_summary(feishu)
    git_bullets = git_summary(git_ev)
    projects = top_projects(agent)
    themes = extract_themes(
        [q.get("preview", "") for e in agent for q in (e.get("queries") or [])],
        cfg,
    )
    pending = pending_tasks(12)

    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    lines = [
        f"# 工作周报 · {subject} · {start_str} ~ {end_str}",
        "",
        f"> 自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if role.get("title"):
        lines.append(f"> 岗位：{role['title']}")
    lines.extend(
        [
            "",
            "## 本周概览",
            "",
            f"- Agent 协作 **{len(agent)}** 次 · Git 批次 **{len(git_ev)}** · 飞书信号 **{len(feishu)}** 组",
        ]
    )
    if themes:
        lines.append(f"- 主要方向：{' · '.join(themes[:5])}")
    if projects:
        names = "、".join(p for p, _ in projects[:5])
        lines.append(f"- 活跃项目/目录：{names}")

    lines.extend(["", "## 关键产出", ""])
    highlights: list[str] = []
    if task_lines:
        highlights.append(f"- 飞书任务完成 **{len(task_lines)}** 项")
    if git_bullets:
        highlights.append(f"- Git 提交 **{len(git_bullets)}** 条")
    if doc_lines:
        highlights.append(f"- 编辑文档 **{len(doc_lines)}** 篇")
    lines.extend(highlights or ["- _本周暂无可自动归纳的关键产出，请手动补充。_"])

    lines.extend(["", "## 会议与协作", ""])
    lines.extend(cal_lines[:15] or ["- _未采集到会议记录。_"])

    lines.extend(["", "## 代码与交付", ""])
    lines.extend(git_bullets[:20] or ["- _本周无 Git 提交。_"])

    lines.extend(["", "## 文档沉淀", ""])
    lines.extend(doc_lines[:15] or ["- _本周未编辑飞书文档。_"])

    lines.extend(["", "## 每日摘要", ""])
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        ts = parse_event_time(ev.get("time"))
        if not ts:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        day_key = ts.astimezone(tz).strftime("%Y-%m-%d")
        by_day[day_key].append(ev)

    if not by_day:
        lines.append("_本周无按日分布的信号。_")
    else:
        for day_key in sorted(by_day):
            day_events = merge_events_for_digest(by_day[day_key])
            bits: list[str] = []
            for ev in day_events:
                t = ev.get("type")
                if t == "feishu_calendar":
                    bits.append(f"{ev.get('count', 0)} 场会议")
                elif t == "feishu_tasks":
                    bits.append(f"{ev.get('count', 0)} 项任务")
                elif t == "git_commits":
                    bits.append(f"{ev.get('count', 0)} commits")
                elif t in AGENT_TYPES:
                    bits.append(f"{AGENT_LABELS.get(t, 'Agent')} {ev.get('query_count', 0)} 问")
            weekday = datetime.strptime(day_key, "%Y-%m-%d").weekday()
            wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]
            summary = " · ".join(bits) if bits else "无显著信号"
            lines.append(f"### {day_key}（{wd}）")
            lines.append("")
            lines.append(f"- {summary}")
            lines.append("")

    lines.extend(["", "## 下周计划", ""])
    if pending:
        lines.extend(pending)
    else:
        lines.append("- _（待补充）_")

    lines.extend(["", "## 风险与阻塞", "", "- _无_", ""])
    return "\n".join(lines)


def publish_to_feishu(content: str, cfg: dict[str, Any]) -> dict[str, Any]:
    feishu_cfg = (cfg.get("reports") or {}).get("feishu") or {}
    identity = feishu_cfg.get("identity") or (cfg.get("feishu") or {}).get("identity", "user")
    args = [
        "lark-cli",
        "docs",
        "+create",
        "--api-version",
        "v2",
        "--doc-format",
        "markdown",
        "--content",
        content,
        "--as",
        identity,
        "--format",
        "json",
    ]
    parent_token = feishu_cfg.get("parent_token") or ""
    parent_position = feishu_cfg.get("parent_position") or ""
    if parent_token:
        args.extend(["--parent-token", parent_token])
    elif parent_position:
        args.extend(["--parent-position", parent_position])

    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False, timeout=60)
    except FileNotFoundError:
        return {"ok": False, "error": "lark-cli not found — install and run setup-feishu.sh"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "lark-cli timed out"}

    blob = (proc.stdout or proc.stderr or "").strip()
    if not blob:
        return {"ok": False, "error": "empty response from lark-cli"}
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {"ok": False, "error": blob[:500]}
    if proc.returncode != 0 and not data.get("ok"):
        err = data.get("error") or {"message": blob[:300]}
        return {"ok": False, "error": err}
    doc = (data.get("data") or {}).get("document") or data.get("document") or {}
    url = doc.get("url") or data.get("url")
    return {"ok": True, "url": url, "document_id": doc.get("document_id"), "raw": data}


def maybe_collect(skill_root: Path) -> None:
    collect_py = skill_root / "scripts" / "collect.py"
    if collect_py.exists():
        subprocess.run([sys.executable, str(collect_py)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily/weekly work reports.")
    parser.add_argument(
        "period",
        choices=["daily", "weekly"],
        help="Report period: daily or weekly",
    )
    parser.add_argument("--date", default="", help="Anchor date YYYY-MM-DD (default: today)")
    parser.add_argument("--subject", default="", help="Report subject / author name")
    parser.add_argument("--journal", default="~/.实习生-skill", help="Journal directory")
    parser.add_argument("--output", default="", help="Output markdown path")
    parser.add_argument(
        "--collect-first",
        action="store_true",
        help="Run collect.py before generating report",
    )
    parser.add_argument(
        "--publish-feishu",
        action="store_true",
        help="Create a Feishu doc from the report (requires lark-cli doc write scope)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip writing local markdown (only useful with --publish-feishu)",
    )
    args = parser.parse_args()

    skill_root = SCRIPTS.parent
    journal = expand(args.journal)
    journal.mkdir(parents=True, exist_ok=True)
    cfg = load_config(journal)

    if args.collect_first:
        maybe_collect(skill_root)

    tz_name = (cfg.get("feishu") or {}).get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name)
    if args.date:
        anchor = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        anchor = datetime.now(tz)

    subject = args.subject
    if not subject:
        subject = (cfg.get("_role") or {}).get("title") or cfg.get("reports", {}).get("subject", "工作汇报")

    if args.period == "daily":
        events = merge_events_for_digest(load_events_for_day(journal, anchor))
        report = build_daily_report(events, subject=subject, day=anchor, cfg=cfg)
        default_name = f"daily-{anchor.strftime('%Y-%m-%d')}.md"
        out_dir = journal / "reports" / "daily"
    else:
        start, end = week_bounds(anchor, tz_name)
        events = load_events_between(journal, start, end, tz_name)
        report = build_weekly_report(
            events, subject=subject, start=start, end=end, cfg=cfg
        )
        default_name = f"weekly-{start.strftime('%Y-%m-%d')}.md"
        out_dir = journal / "reports" / "weekly"

    out_path = expand(args.output) if args.output else out_dir / default_name
    if not args.no_save:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Report → {out_path}")

    if args.publish_feishu:
        result = publish_to_feishu(report, cfg)
        if result.get("ok"):
            print(f"Feishu doc → {result.get('url') or result.get('document_id')}")
        else:
            print(f"Feishu publish failed: {result.get('error')}", file=sys.stderr)
            sys.exit(1)

    if not args.no_save:
        print(f"Events used: {len(events)}")


if __name__ == "__main__":
    main()
