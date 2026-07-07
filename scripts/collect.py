#!/usr/bin/env python3
"""Collect work signals from Claude/Codex/Cursor transcripts + git + Feishu."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOURNAL = Path.home() / ".实习生-skill"
STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
DAILY_DIR = "daily"
RESUME_LOG = "RESUME_LOG.md"

SESSION_TYPES = {
    "cursor_session",
    "claude_session",
    "codex_session",
    "git_commits",
    "feishu_calendar",
    "feishu_tasks",
    "feishu_messages",
    "feishu_message_search",
    "feishu_docs",
}

SESSION_LABELS = {
    "cursor_session": "Cursor",
    "claude_session": "Claude Code",
    "codex_session": "Codex",
    "feishu_calendar": "飞书日程",
    "feishu_tasks": "飞书任务",
    "feishu_messages": "飞书消息",
    "feishu_message_search": "飞书搜索",
    "feishu_docs": "飞书文档",
}

FEISHU_TYPES = {
    "feishu_calendar",
    "feishu_tasks",
    "feishu_messages",
    "feishu_message_search",
    "feishu_docs",
}


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


def config_candidates() -> list[Path]:
    return [
        DEFAULT_JOURNAL / "config.json",
        SKILL_ROOT / "config.json",
        SKILL_ROOT / "config.example.json",
    ]


def load_config() -> dict[str, Any]:
    for cfg_path in config_candidates():
        if cfg_path.exists():
            with cfg_path.open(encoding="utf-8") as f:
                cfg = json.load(f)
            scripts_dir = Path(__file__).resolve().parent
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            from role_profiles import resolve_role

            return resolve_role(cfg)
    raise FileNotFoundError(
        "No config found. Copy config.example.json to ~/.实习生-skill/config.json"
    )


def load_state(journal: Path) -> dict[str, Any]:
    path = journal / STATE_FILE
    if not path.exists():
        return {"last_run": None, "transcripts": {}, "repos": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(journal: Path, state: dict[str, Any]) -> None:
    (journal / STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def source_roots(cfg: dict[str, Any], name: str, default: str) -> list[str]:
    """Resolve roots from `sources.<name>.roots`."""
    sources = cfg.get("sources") or {}
    block = sources.get(name) or {}
    if block.get("enabled") is False:
        return []
    return block.get("roots") or [default]


def parse_cursor_timestamp(line: str) -> datetime | None:
    m = re.search(r"<timestamp>([^<]+)</timestamp>", line)
    if not m:
        return None
    raw = m.group(1).strip()
    for fmt in (
        "%A, %b %d, %Y, %I:%M %p (UTC%z)",
        "%A, %B %d, %Y, %I:%M %p (UTC%z)",
    ):
        try:
            return datetime.strptime(raw.replace(" (UTC+8)", "+0800"), fmt)
        except ValueError:
            continue
    return None


def parse_iso_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def slug_to_project(slug: str) -> str:
    slug = re.sub(r"^-Users-[^-]+-", "", slug, flags=re.I)
    slug = re.sub(r"^Users-[^-]+-", "", slug, flags=re.I)
    slug = slug.lstrip("-")
    return slug.replace("-", " ").strip() or slug


def infer_project_from_path(transcript_path: Path, marker: str) -> str:
    parts = transcript_path.parts
    if marker in parts:
        idx = parts.index(marker)
        if idx + 1 < len(parts):
            return slug_to_project(parts[idx + 1])
        if idx > 0:
            return slug_to_project(parts[idx - 1])
    return transcript_path.parent.name.replace("-", " ")


def tag_domains(text: str, domains: dict[str, list[str]]) -> list[str]:
    low = text.lower()
    hits = []
    for name, kws in domains.items():
        if any(kw.lower() in low for kw in kws):
            hits.append(name)
    return hits or ["general"]


def should_skip_user_text(text: str) -> bool:
    if not text or text.startswith("[Image]"):
        return True
    if "Briefly inform the user" in text:
        return True
    if text.startswith("<environment_context>"):
        return True
    return False


def extract_cursor_user_text(obj: dict) -> str:
    msg = obj.get("message") or {}
    parts = msg.get("content") or []
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            t = p.get("text") or ""
            t = re.sub(r"<timestamp>.*?</timestamp>", "", t, flags=re.S)
            t = re.sub(r"<user_query>\s*", "", t)
            t = re.sub(r"\s*</user_query>", "", t)
            texts.append(t.strip())
    return "\n".join(texts).strip()


def extract_claude_user_text(obj: dict) -> str:
    if obj.get("type") != "user":
        return ""
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                texts.append((p.get("text") or "").strip())
            elif isinstance(p, str):
                texts.append(p.strip())
        return "\n".join(texts).strip()
    return ""


def extract_codex_user_text(obj: dict) -> str:
    if obj.get("type") == "event_msg":
        payload = obj.get("payload") or {}
        if payload.get("type") == "user_message":
            return normalize_codex_request(payload.get("message") or "")

    if obj.get("type") != "response_item":
        return ""
    payload = obj.get("payload") or {}
    if payload.get("type") != "message" or payload.get("role") != "user":
        return ""
    parts = payload.get("content") or []
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "input_text":
            texts.append((p.get("text") or "").strip())
    return normalize_codex_request("\n".join(texts))


def normalize_codex_request(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    m = re.search(r"## My request for Codex:\s*(.+)", text, flags=re.S)
    if m:
        return m.group(1).strip()
    if "<environment_context>" in text and "## My request" not in text:
        return ""
    return text


def make_query_entry(
    text: str,
    ts: datetime,
    domains: dict[str, list[str]],
) -> dict[str, Any]:
    preview = text[:500].replace("\n", " ")
    return {
        "time": ts.isoformat(),
        "preview": preview,
        "domains": tag_domains(text, domains),
    }


def scan_jsonl_files(
    cfg: dict[str, Any],
    state: dict[str, Any],
    since: datetime | None,
    *,
    roots: list[str],
    glob_pattern: str,
    event_type: str,
    session_id_from: Callable[[Path], str],
    project_from: Callable[[Path, list[dict]], str],
    extract_text: Callable[[dict, str], str],
    parse_ts: Callable[[dict, str, float], datetime],
    skip_path: Callable[[Path], bool] | None = None,
) -> list[dict[str, Any]]:
    domains = cfg.get("domains") or {}
    events: list[dict[str, Any]] = []
    seen_paths: dict[str, Any] = state.setdefault("transcripts", {})

    for root_s in roots:
        root = expand(root_s)
        if not root.exists():
            continue
        for path in root.glob(glob_pattern):
            if skip_path and skip_path(path):
                continue
            rel = str(path)
            mtime = path.stat().st_mtime
            prev_mtime = seen_paths.get(rel, 0)
            if mtime <= prev_mtime:
                continue

            session_id = session_id_from(path)
            user_queries: list[dict[str, Any]] = []
            seen_texts: set[str] = set()
            cwd_hint = ""

            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not cwd_hint:
                        cwd_hint = obj.get("cwd") or ""
                        if not cwd_hint and obj.get("type") == "session_meta":
                            cwd_hint = (obj.get("payload") or {}).get("cwd") or ""

                    text = extract_text(obj, line)
                    if should_skip_user_text(text):
                        continue
                    dedupe_key = text[:200]
                    if dedupe_key in seen_texts:
                        continue
                    seen_texts.add(dedupe_key)

                    ts = parse_ts(obj, line, mtime)
                    if since and ts < since:
                        continue
                    user_queries.append(make_query_entry(text, ts, domains))

            if user_queries:
                if cwd_hint:
                    project = Path(cwd_hint).name
                else:
                    project = project_from(path, user_queries)
                events.append(
                    {
                        "type": event_type,
                        "time": user_queries[0]["time"],
                        "project": project,
                        "session_id": session_id,
                        "path": rel,
                        "query_count": len(user_queries),
                        "queries": user_queries[:8],
                        "domains": sorted(
                            {d for q in user_queries for d in q["domains"]}
                        ),
                    }
                )
            seen_paths[rel] = mtime

    return events


def scan_cursor_sessions(
    cfg: dict[str, Any], state: dict[str, Any], since: datetime | None
) -> list[dict[str, Any]]:
    roots = source_roots(cfg, "cursor", "~/.cursor/projects")

    def parse_ts(obj: dict, line: str, mtime: float) -> datetime:
        return parse_cursor_timestamp(line) or datetime.fromtimestamp(
            mtime, tz=timezone.utc
        )

    return scan_jsonl_files(
        cfg,
        state,
        since,
        roots=roots,
        glob_pattern="**/agent-transcripts/**/*.jsonl",
        event_type="cursor_session",
        session_id_from=lambda p: p.parent.name,
        project_from=lambda p, _: infer_project_from_path(p, "projects"),
        extract_text=lambda obj, line: extract_cursor_user_text(obj)
        if obj.get("role") == "user"
        else "",
        parse_ts=parse_ts,
        skip_path=lambda p: "/subagents/" in str(p),
    )


def scan_claude_sessions(
    cfg: dict[str, Any], state: dict[str, Any], since: datetime | None
) -> list[dict[str, Any]]:
    roots = source_roots(cfg, "claude", "~/.claude/projects")

    def parse_ts(obj: dict, line: str, mtime: float) -> datetime:
        return (
            parse_iso_timestamp(obj.get("timestamp"))
            or datetime.fromtimestamp(mtime, tz=timezone.utc)
        )

    def project_from(path: Path, _: list[dict]) -> str:
        return infer_project_from_path(path, "projects")

    return scan_jsonl_files(
        cfg,
        state,
        since,
        roots=roots,
        glob_pattern="**/*.jsonl",
        event_type="claude_session",
        session_id_from=lambda p: p.stem,
        project_from=project_from,
        extract_text=lambda obj, _: extract_claude_user_text(obj),
        parse_ts=parse_ts,
    )


def scan_codex_sessions(
    cfg: dict[str, Any], state: dict[str, Any], since: datetime | None
) -> list[dict[str, Any]]:
    roots = source_roots(cfg, "codex", "~/.codex/sessions")

    def parse_ts(obj: dict, line: str, mtime: float) -> datetime:
        return (
            parse_iso_timestamp(obj.get("timestamp"))
            or datetime.fromtimestamp(mtime, tz=timezone.utc)
        )

    def project_from(path: Path, _: list[dict]) -> str:
        # rollout-2026-06-04T...-uuid.jsonl → use parent date folder or sessions
        return path.parent.name if path.parent.name != "sessions" else "codex"

    return scan_jsonl_files(
        cfg,
        state,
        since,
        roots=roots,
        glob_pattern="**/rollout-*.jsonl",
        event_type="codex_session",
        session_id_from=lambda p: p.stem.split("-")[-1] if "-" in p.stem else p.stem,
        project_from=project_from,
        extract_text=lambda obj, _: extract_codex_user_text(obj),
        parse_ts=parse_ts,
    )


def git_events(
    cfg: dict[str, Any], state: dict[str, Any], since: datetime | None
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    repo_state: dict[str, str] = state.setdefault("repos", {})
    since_str = since.strftime("%Y-%m-%d") if since else "1970-01-01"

    for item in cfg.get("repos") or []:
        repo = expand(item["path"])
        label = item.get("label") or repo.name
        if not (repo / ".git").exists():
            continue
        last_sha = repo_state.get(str(repo), "")
        try:
            log = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "log",
                    f"--since={since_str}",
                    "--pretty=format:%H|%ai|%an|%s",
                    "-n",
                    "50",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            continue

        commits = []
        for line in log.stdout.splitlines():
            if not line.strip():
                continue
            sha, dt, author, subject = line.split("|", 3)
            if last_sha and sha == last_sha:
                break
            commits.append(
                {"sha": sha[:8], "time": dt, "author": author, "subject": subject}
            )

        if commits:
            events.append(
                {
                    "type": "git_commits",
                    "time": commits[0]["time"],
                    "repo": label,
                    "path": str(repo),
                    "count": len(commits),
                    "commits": commits[:15],
                }
            )
            repo_state[str(repo)] = commits[0]["sha"]

    return events


def append_events(journal: Path, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    journal.mkdir(parents=True, exist_ok=True)
    with (journal / EVENTS_FILE).open("a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def parse_event_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def load_events_for_day(journal: Path, day: datetime | None = None) -> list[dict[str, Any]]:
    """All event groups whose timestamp falls on the given local day."""
    path = journal / EVENTS_FILE
    if not path.exists():
        return []
    if day is None:
        day = datetime.now()
    target = day.date()
    local_tz = day.astimezone().tzinfo or timezone.utc
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
            if ts.astimezone(local_tz).date() == target:
                events.append(ev)
    return events


def merge_events_for_digest(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge multiple incremental collects into one daily view."""
    merged: dict[str, dict[str, Any]] = {}
    others: list[dict[str, Any]] = []

    def upsert(key: str, ev: dict[str, Any]) -> None:
        merged[key] = ev

    for ev in events:
        t = ev.get("type")
        if t == "feishu_calendar":
            key = "feishu_calendar"
            if key not in merged:
                upsert(key, {**ev, "events": list(ev.get("events") or [])})
                continue
            seen = {e.get("title") for e in merged[key].get("events") or []}
            for item in ev.get("events") or []:
                title = item.get("title")
                if title and title not in seen:
                    merged[key]["events"].append(item)
                    seen.add(title)
            merged[key]["count"] = len(merged[key]["events"])
        elif t == "feishu_tasks":
            key = "feishu_tasks"
            if key not in merged:
                upsert(key, {**ev, "tasks": list(ev.get("tasks") or [])})
                continue
            seen = {x.get("summary") for x in merged[key].get("tasks") or []}
            for item in ev.get("tasks") or []:
                summary = item.get("summary")
                if summary and summary not in seen:
                    merged[key]["tasks"].append(item)
                    seen.add(summary)
            merged[key]["count"] = len(merged[key]["tasks"])
        elif t == "feishu_messages":
            key = f"feishu_messages:{ev.get('chat_id')}"
            if key not in merged:
                upsert(key, {**ev, "messages": list(ev.get("messages") or [])})
                continue
            seen = {m.get("message_id") or m.get("text") for m in merged[key].get("messages") or []}
            for item in ev.get("messages") or []:
                ident = item.get("message_id") or item.get("text")
                if ident not in seen:
                    merged[key]["messages"].append(item)
                    seen.add(ident)
            merged[key]["count"] = len(merged[key]["messages"])
        elif t == "feishu_docs":
            key = "feishu_docs"
            if key not in merged:
                upsert(key, {**ev, "docs": list(ev.get("docs") or [])})
                continue
            seen = {d.get("token") or d.get("title") for d in merged[key].get("docs") or []}
            for item in ev.get("docs") or []:
                ident = item.get("token") or item.get("title")
                if ident not in seen:
                    merged[key]["docs"].append(item)
                    seen.add(ident)
            merged[key]["count"] = len(merged[key]["docs"])
        elif t in SESSION_LABELS:
            key = f"{t}:{ev.get('session_id') or ev.get('path')}"
            prev = merged.get(key)
            if not prev or (ev.get("query_count") or 0) >= (prev.get("query_count") or 0):
                upsert(key, ev)
        elif t == "git_commits":
            key = f"git:{ev.get('repo')}"
            if key not in merged:
                upsert(key, {**ev, "commits": list(ev.get("commits") or [])})
                continue
            seen = {c.get("sha") for c in merged[key].get("commits") or []}
            for item in ev.get("commits") or []:
                sha = item.get("sha")
                if sha and sha not in seen:
                    merged[key]["commits"].append(item)
                    seen.add(sha)
            merged[key]["count"] = len(merged[key]["commits"])
        else:
            others.append(ev)

    return list(merged.values()) + others


def write_daily_digest(journal: Path, role: dict[str, Any] | None = None) -> Path:
    journal.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    daily_dir = journal / DAILY_DIR
    daily_dir.mkdir(exist_ok=True)
    out = daily_dir / f"{day}.md"

    events = merge_events_for_digest(load_events_for_day(journal))

    lines = [
        f"# 工作记录 {day}",
        "",
        f"> 自动生成于 {datetime.now().isoformat(timespec='seconds')}",
        f"> 汇总今日全部采集信号（非仅本次增量）",
        "",
    ]
    if role and role.get("title"):
        lines.insert(3, f"> 岗位：{role['title']}（{role.get('preset_label', role.get('preset', ''))}）")
        lines.insert(4, "")

    if not events:
        lines.append("_今日无新信号。_")
    else:
        feishu_items = [e for e in events if e["type"] in FEISHU_TYPES]
        other_items = [e for e in events if e["type"] not in FEISHU_TYPES]

        if feishu_items:
            lines.extend(["## 飞书（今天干了什么）", ""])
            for it in feishu_items:
                if it["type"] == "feishu_calendar":
                    lines.append(f"- **日程** · {it['count']} 场会议/安排")
                    for ev in (it.get("events") or [])[:8]:
                        title = ev.get("title") or ""
                        start = ev.get("start") or ""
                        lines.append(f"  - {start[:16]} {title}")
                elif it["type"] == "feishu_tasks":
                    lines.append(f"- **完成任务** · {it['count']} 项")
                    for t in (it.get("tasks") or [])[:8]:
                        lines.append(f"  - {t.get('summary', '')[:120]}")
                elif it["type"] == "feishu_messages":
                    lines.append(
                        f"- **消息** · {it.get('chat_name', it.get('chat_id', ''))} · "
                        f"{it['count']} 条"
                    )
                    for m in (it.get("messages") or [])[:4]:
                        lines.append(f"  - {m.get('text', '')[:120]}")
                elif it["type"] == "feishu_docs":
                    lines.append(f"- **文档** · 编辑 {it['count']} 篇")
                    for d in (it.get("docs") or [])[:5]:
                        lines.append(f"  - 《{d.get('title', '')}》")
                elif it["type"] == "feishu_message_search":
                    lines.append(
                        f"- **搜索** · `{it.get('query', '')}` · {it['count']} 条"
                    )
            lines.append("")

        lines.append("## 其他信号")
        lines.append("")
        by_domain: dict[str, list[dict]] = defaultdict(list)
        for e in other_items:
            if e["type"] in SESSION_TYPES - {"git_commits"}:
                for d in e.get("domains") or ["general"]:
                    by_domain[d].append(e)
            elif e["type"] == "git_commits":
                by_domain["git"].append(e)

        if not other_items:
            lines.append("_无 Agent / Git 新信号。_")
            lines.append("")
        else:
            for domain, items in sorted(by_domain.items()):
                lines.append(f"### {domain}")
                lines.append("")
                for it in items:
                    if it["type"] in SESSION_LABELS:
                        label = SESSION_LABELS[it["type"]]
                        lines.append(
                            f"- **{label}** · `{it['project']}` · "
                            f"{it['query_count']} queries"
                        )
                        for q in (it.get("queries") or [])[:3]:
                            lines.append(f"  - {q['preview'][:120]}")
                    elif it["type"] == "git_commits":
                        lines.append(f"- **Git** · {it['repo']} · {it['count']} commits")
                        for c in (it.get("commits") or [])[:3]:
                            lines.append(f"  - `{c['sha']}` {c['subject']}")
                lines.append("")

        lines.extend(
            [
                "## 待补充（写简历用）",
                "",
                "### 职责",
                "- ",
                "",
                "### 产出",
                "- ",
                "",
                "### 项目经历",
                "#### 项目名称",
                "- **背景**：",
                "- **负责**：",
                "- **产出**：",
                "- **技术栈**：",
                "",
            ]
        )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def ensure_resume_log(journal: Path) -> None:
    path = journal / RESUME_LOG
    if path.exists():
        return
    path.write_text(
        """# 简历素材库

> 由 实习生.skill 采集 + Agent 精炼。写简历时**只取下面三节**。

## 职责

- _待补充：岗位级概括，2–4 条_

## 产出

- _待补充：量化或可验证交付，2–5 条_

## 项目经历

### 项目名称

- **背景**：
- **负责**：
- **产出**：
- **技术栈**：

---

## 原始索引

核对用：`events.jsonl`、`daily/`、`reports/`。不直接贴进简历。

""",
        encoding="utf-8",
    )


def collect_all(
    cfg: dict[str, Any], state: dict[str, Any], since: datetime | None
) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    events.extend(scan_claude_sessions(cfg, state, since))
    events.extend(scan_codex_sessions(cfg, state, since))
    events.extend(scan_cursor_sessions(cfg, state, since))
    events.extend(git_events(cfg, state, since))

    try:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from lark_collect import collect_feishu

        feishu_events, feishu_warnings = collect_feishu(cfg, since)
        events.extend(feishu_events)
        warnings.extend(feishu_warnings)
    except ImportError:
        pass

    events.sort(key=lambda e: e.get("time") or "")
    return events, warnings


def main() -> None:
    cfg = load_config()
    journal = expand(cfg.get("journal_dir") or str(DEFAULT_JOURNAL))
    state = load_state(journal)
    since = None
    if state.get("last_run"):
        try:
            since = datetime.fromisoformat(state["last_run"])
        except ValueError:
            pass

    events, warnings = collect_all(cfg, state, since)

    if since:
        gap_h = (datetime.now(timezone.utc) - since.astimezone(timezone.utc)).total_seconds() / 3600
        if gap_h > 24:
            print(f"Catch-up: last collect {gap_h:.0f}h ago, pulling signals since then.")

    append_events(journal, events)
    daily = write_daily_digest(journal, cfg.get("_role"))
    ensure_resume_log(journal)

    state["last_run"] = datetime.now(timezone.utc).astimezone().isoformat()
    save_state(journal, state)

    counts: dict[str, int] = defaultdict(int)
    for e in events:
        counts[e["type"]] += 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"Collected {len(events)} event groups ({summary}) → {journal}")
    role = cfg.get("_role") or {}
    if role.get("preset"):
        print(f"Role: {role.get('title')} — 改岗位: scripts/setup_role.py")
    if warnings:
        print("Feishu setup (core — 授权后才有「今天干了什么」):")
        for w in dict.fromkeys(warnings):
            print(f"  - {w}")
    print(f"Daily digest → {daily}")
    print("（采集自动；汇总请离职前手动运行 summarize.py 或 scripts/offboard.sh）")


if __name__ == "__main__":
    main()
