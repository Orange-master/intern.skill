#!/usr/bin/env python3
"""Summarize collected signals into intern resume-ready markdown."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

AGENT_TYPES = {"cursor_session", "claude_session", "codex_session"}
FEISHU_TYPES = {
    "feishu_calendar",
    "feishu_tasks",
    "feishu_messages",
    "feishu_message_search",
    "feishu_docs",
}
AGENT_LABELS = {
    "cursor_session": "Cursor",
    "claude_session": "Claude Code",
    "codex_session": "Codex",
}


def expand(p: str) -> Path:
    return Path(p).expanduser()


def load_config(journal: Path) -> dict[str, Any]:
    for cfg_path in (
        journal / "config.json",
        Path(__file__).resolve().parent.parent / "config.example.json",
    ):
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            scripts = Path(__file__).resolve().parent
            import sys

            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from role_profiles import resolve_role

            return resolve_role(cfg)
    scripts = Path(__file__).resolve().parent
    import sys

    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from role_profiles import resolve_role

    return resolve_role({})


def parse_event_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_events(journal: Path, days: int) -> list[dict[str, Any]]:
    path = journal / "events.jsonl"
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
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
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts and ts < cutoff:
                continue
            events.append(ev)
    return events


def top_projects(agent_events: list[dict[str, Any]], n: int = 8) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for ev in agent_events:
        counts[ev.get("project") or "unknown"] += ev.get("query_count") or 1
    return counts.most_common(n)


def extract_themes(queries: list[str], cfg: dict[str, Any] | None = None) -> list[str]:
    role = (cfg or {}).get("_role") or {}
    patterns = role.get("theme_patterns")
    if patterns:
        scripts = Path(__file__).resolve().parent
        import sys

        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from role_profiles import extract_themes_for_role

        return extract_themes_for_role(queries, patterns)

    themes: Counter[str] = Counter()
    patterns = [
        (r"code|代码|api|接口|组件|页面|ui|frontend|backend|模块", "功能开发"),
        (r"fix|bug|修复|排查|工单", "问题排查"),
        (r"test|测试|验收|冒烟", "测试验收"),
        (r"deploy|上线|发布|ci", "交付上线"),
        (r"doc|文档|wiki|纪要|设计|原型", "文档与设计"),
        (r"需求|评审|产品|用户|交互", "产品需求"),
        (r"skill|agent|cursor|mcp|codex|claude", "AI 协作提效"),
    ]
    for q in queries:
        for pat, label in patterns:
            if re.search(pat, q, re.I):
                themes[label] += 1
    return [t for t, _ in themes.most_common(6)]


def git_summary(git_events: list[dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    for ev in git_events:
        repo = ev.get("repo") or "repo"
        commits = ev.get("commits") or []
        for c in commits[:5]:
            bullets.append(f"- **{repo}** `{c.get('sha', '')}` {c.get('subject', '')}")
    return bullets[:15]


def feishu_summary(
    feishu_events: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    cal_lines: list[str] = []
    task_lines: list[str] = []
    msg_lines: list[str] = []
    doc_lines: list[str] = []
    for ev in feishu_events:
        if ev["type"] == "feishu_calendar":
            for item in ev.get("events") or []:
                title = item.get("title") or ""
                start = (item.get("start") or "")[:16]
                if title:
                    cal_lines.append(f"- {start} {title}")
        elif ev["type"] == "feishu_tasks":
            for t in ev.get("tasks") or []:
                summary = t.get("summary") or ""
                if summary:
                    task_lines.append(f"- {summary}")
        elif ev["type"] in ("feishu_messages", "feishu_message_search"):
            for m in ev.get("messages") or []:
                text = (m.get("text") or "").replace("\n", " ")[:120]
                if text:
                    msg_lines.append(f"- {text}")
        elif ev["type"] == "feishu_docs":
            for d in ev.get("docs") or []:
                title = d.get("title") or "untitled"
                doc_lines.append(f"- 《{title}》({d.get('type', 'doc')})")
    return cal_lines[:12], task_lines[:12], msg_lines[:12], doc_lines[:12]


def agent_query_samples(agent_events: list[dict[str, Any]], n: int = 12) -> list[str]:
    samples: list[str] = []
    for ev in agent_events:
        for q in ev.get("queries") or []:
            preview = (q.get("preview") or "").strip()
            if len(preview) >= 8:
                samples.append(preview[:160])
            if len(samples) >= n:
                return samples
    return samples


def draft_owned_bullets(
    projects: list[tuple[str, int]],
    themes: list[str],
    git_bullets: list[str],
    doc_lines: list[str],
    cal_lines: list[str],
    task_lines: list[str],
) -> list[str]:
    bullets: list[str] = []
    if cal_lines:
        bullets.append("参与团队会议与跨组协作（飞书日程可交叉验证）。")
    if task_lines:
        bullets.append(f"在飞书任务中完成 **{len(task_lines)}** 项可追踪交付。")
    if projects:
        names = ", ".join(p for p, _ in projects[:4])
        bullets.append(f"参与/负责 **{names}** 等相关模块的开发与交付工作。")
    for theme in themes[:4]:
        bullets.append(f"在 **{theme}** 方向持续投入（Agent 会话与代码提交交叉验证）。")
    if git_bullets:
        bullets.append("通过 Git 提交交付可追踪的代码/SQL/配置变更。")
    if doc_lines:
        bullets.append("在飞书文档中沉淀方案、排查记录或周报类产出。")
    return bullets or ["_待 Agent 结合 RESUME_LOG 补充可量化负责内容。_"]


def draft_outcome_bullets(
    git_bullets: list[str], themes: list[str], agent_count: int
) -> list[str]:
    bullets: list[str] = []
    if agent_count:
        bullets.append(
            f"统计周期内通过 Cursor/Claude/Codex 完成 **{agent_count}** 轮技术协作会话。"
        )
    if git_bullets:
        bullets.append(f"提交 **{len(git_bullets)}** 条可追踪 Git 变更（见下方明细）。")
    for theme in themes[:3]:
        bullets.append(f"在 {theme} 场景有明确任务推进记录。")
    return bullets or ["_待补充量化指标（覆盖率、工单数、上线项等）。_"]


def draft_project_experience(
    projects: list[tuple[str, int]],
    themes: list[str],
    git_bullets: list[str],
    doc_lines: list[str],
) -> list[str]:
    """Draft 项目经历 blocks from top agent projects."""
    if not projects:
        return ["_待结合 Agent 会话与 Git 补充具体项目。_"]

    lines: list[str] = []
    for proj, cnt in projects[:4]:
        theme_hint = themes[0] if themes else "技术协作"
        git_hint = ""
        for g in git_bullets:
            if proj.lower() in g.lower():
                git_hint = g
                break
        doc_hint = ""
        for d in doc_lines:
            if proj.lower() in d.lower():
                doc_hint = d
                break
        lines.extend(
            [
                f"### {proj}",
                "",
                f"- **背景**：{proj} 相关模块/需求（{cnt} 条 Agent 协作记录，主题含 {theme_hint}）",
                f"- **负责**：在 {proj} 中参与开发与问题排查 [待核实具体边界]",
                f"- **产出**：{git_hint or doc_hint or '有可追踪的 commit / 文档 / 飞书任务记录 [待核实]'}",
                f"- **技术栈**：{theme_hint}",
                "",
            ]
        )
    return lines


def build_report(
    events: list[dict[str, Any]],
    *,
    subject: str,
    days: int,
    cfg: dict[str, Any] | None = None,
) -> str:
    agent = [e for e in events if e.get("type") in AGENT_TYPES]
    git_ev = [e for e in events if e.get("type") == "git_commits"]
    feishu = [e for e in events if e.get("type") in FEISHU_TYPES]

    projects = top_projects(agent)
    queries = agent_query_samples(agent, 30)
    themes = extract_themes(queries, cfg)
    role = (cfg or {}).get("_role") or {}
    git_bullets = git_summary(git_ev)
    cal_lines, task_lines, msg_lines, doc_lines = feishu_summary(feishu)
    agent_sessions = len(agent)
    query_total = sum(e.get("query_count") or 0 for e in agent)

    by_agent: dict[str, int] = Counter(e.get("type", "") for e in agent)
    owned = draft_owned_bullets(projects, themes, git_bullets, doc_lines, cal_lines, task_lines)
    outcomes = draft_outcome_bullets(git_bullets, themes, agent_sessions)
    project_blocks = draft_project_experience(projects, themes, git_bullets, doc_lines)

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 实习生工作摘要 · {subject}",
        "",
        f"> 自动生成 · 统计近 **{days}** 天 · {today}",
    ]
    if role.get("title"):
        lines.append(
            f"> 岗位：{role['title']}（{role.get('preset_label', role.get('preset', ''))}）"
        )
    lines.extend(
        [
            f"> 信号源：Agent 会话 {agent_sessions} · Git 批次 {len(git_ev)} · 飞书 {len(feishu)}",
            "",
            "## 简历草稿",
            "",
            "> 最终简历只取下面三节：**职责 · 产出 · 项目经历**",
            "",
            "### 职责",
            "",
        ]
    )
    lines.extend(owned)
    lines.extend(["", "### 产出", ""])
    lines.extend(outcomes)
    lines.extend(["", "### 项目经历", ""])
    lines.extend(project_blocks)

    lines.extend(["", "---", "", "## 原始信号（核对用，不直接贴进简历）", ""])
    lines.extend(["", "### Agent 协作（Cursor / Claude / Codex）", ""])
    if by_agent:
        for t, c in sorted(by_agent.items()):
            lines.append(f"- **{AGENT_LABELS.get(t, t)}**：{c} 会话，{sum(e.get('query_count', 0) for e in agent if e.get('type')==t)} 条提问")
    else:
        lines.append("_无 Agent 会话记录。_")
    lines.extend(["", "### 主要项目/目录", ""])
    for proj, cnt in projects:
        lines.append(f"- `{proj}` — {cnt} 条相关提问")
    lines.extend(["", "### 代表性提问（简历素材线索）", ""])
    for s in agent_query_samples(agent, 10):
        lines.append(f"- {s}")
    lines.append(f"\n_合计 {query_total} 条用户提问；以下为技术主题聚类：_")
    if themes:
        lines.append("- " + " · ".join(themes))

    lines.extend(["", "## Git 交付", ""])
    if git_bullets:
        lines.extend(git_bullets)
    else:
        lines.append("_统计周期内无配置仓库的新 commit，请在 config.json → repos 添加路径。_")

    lines.extend(["", "## 飞书协作（核心 — 今天/本周干了什么）", ""])
    lines.extend(["", "### 会议 / 日程", ""])
    if cal_lines:
        lines.extend(cal_lines)
    else:
        lines.append("_未采集到日程（需 lark-cli calendar 权限）。_")
    lines.extend(["", "### 完成任务", ""])
    if task_lines:
        lines.extend(task_lines)
    else:
        lines.append("_未采集到已完成任务。_")
    lines.extend(["", "### 工作相关消息", ""])
    if msg_lines:
        lines.extend(msg_lines)
    else:
        lines.append("_未采集到飞书消息（需 lark-cli IM 权限）。_")
    lines.extend(["", "### 近期编辑文档", ""])
    if doc_lines:
        lines.extend(doc_lines)
    else:
        lines.append("_未采集到飞书文档活动。_")

    lines.extend(
        [
            "",
            "## 下一步（建议 Agent 执行）",
            "",
            "1. 核对 `[待核实]`，补真实数字或改为「参与/协助」。",
            "2. 将确认后的内容按 **职责 / 产出 / 项目经历** 三节追加到 `RESUME_LOG.md`。",
            "3. 用户要「写简历」时，只输出上述三节，不要附带原始信号。",
            "4. 删除与实习无关的个人会话条目。",
            "",
            "## 飞书 CLI 权限",
            "",
            "若飞书段落为空，执行：",
            "",
            "```bash",
            'lark-cli auth login --scope "search:message im:chat:read search:docs:read docx:document:readonly im:message.reactions:read calendar:calendar.event:read task:task:read"',
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize intern work for resume.")
    parser.add_argument("--days", type=int, default=7, help="Lookback days")
    parser.add_argument("--subject", default="实习生", help="Report subject name")
    parser.add_argument(
        "--journal",
        default="~/.实习生-skill",
        help="Journal directory",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path (default: journal/reports/intern-YYYY-MM-DD.md)",
    )
    parser.add_argument(
        "--mentor",
        action="store_true",
        help="Append mentor-distilled first-person bullets (from mentor.py add)",
    )
    args = parser.parse_args()

    journal = expand(args.journal)
    journal.mkdir(parents=True, exist_ok=True)
    cfg = load_config(journal)
    events = load_events(journal, args.days)
    subject = args.subject
    if subject == "实习生" and (cfg.get("_role") or {}).get("title"):
        subject = cfg["_role"]["title"]
    report = build_report(events, subject=subject, days=args.days, cfg=cfg)

    if args.mentor:
        import sys
        from pathlib import Path as P

        scripts = P(__file__).resolve().parent
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from mentor_distill import distill_projects, load_config as load_cfg

        cfg = load_cfg(journal)
        mentor_block = distill_projects(
            cfg, subject=args.subject, events=events, align_signals=True
        )
        report = report + "\n\n---\n\n" + mentor_block

    out = (
        expand(args.output)
        if args.output
        else journal / "reports" / f"intern-{datetime.now():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Report → {out}")
    print(f"Events in window: {len(events)}")
    if args.mentor:
        print("Included mentor distill section")


if __name__ == "__main__":
    main()
