#!/usr/bin/env python3
"""Ingest mentor/employee docs and distill into intern-first resume material."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

MENTOR_DIR = "mentor"
INDEX_FILE = "index.json"
RAW_DIR = "raw"
INBOX_DIR = "inbox"

# Lines that look like resume-worthy content in mentor docs
BULLET_MARKERS = re.compile(
    r"^[\s]*[-*•·]\s+|^[\s]*\d+[.)]\s+|^#{1,4}\s+"
)
METRIC_RE = re.compile(
    r"(\d[\d,.]*(?:\.\d+)?)\s*(%|×|x|倍|万|亿|M|K|条|个|张|次|ms|s)?"
)
STACK_KEYWORDS = [
    "spark", "hive", "sql", "python", "java", "flink", "kafka", "airflow",
    "athena", "presto", "trino", "docker", "k8s", "git", "cursor", "agent",
    "mcp", "udf", "etl", "ods", "dwd", "dwm", "ads", "metabase", "dolphin",
    "tiktok", "amazon", "shopee", "飞书", "lark",
]
ACTION_VERBS = (
    "负责", "参与", "完成", "实现", "开发", "搭建", "优化", "设计", "排查",
    "修复", "上线", "交付", "维护", "编写", "重构", "接入", "落地", "推动",
)


def expand(p: str) -> Path:
    return Path(p).expanduser()


def load_config(journal: Path | None = None) -> dict[str, Any]:
    candidates = []
    if journal:
        candidates.append(journal / "config.json")
    candidates.append(Path(__file__).resolve().parent.parent / "config.example.json")
    for p in candidates:
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8"))
            scripts = Path(__file__).resolve().parent
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from role_profiles import resolve_role

            return resolve_role(cfg)
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from role_profiles import resolve_role

    return resolve_role({"journal_dir": str(journal or "~/.实习生-skill")})


def journal_root(cfg: dict[str, Any]) -> Path:
    return expand(cfg.get("journal_dir") or "~/.实习生-skill")


def mentor_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    base = root / MENTOR_DIR
    return base, base / RAW_DIR, base / INBOX_DIR, base / INDEX_FILE


def load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"projects": []}
    return json.loads(index_path.read_text(encoding="utf-8"))


def save_index(index_path: Path, data: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "project"


def run_lark_fetch(doc_ref: str) -> tuple[str | None, str | None]:
    cmd = [
        "lark-cli", "docs", "+fetch", "--api-version", "v2",
        "--doc", doc_ref, "--as", "user", "--format", "json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None, "lark-cli not found"
    blob = (proc.stdout or proc.stderr or "").strip()
    if not blob:
        return None, "empty lark-cli output"
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return blob[:50000], None
    if isinstance(data, dict) and data.get("ok") is False:
        err = data.get("error") or {}
        return None, err.get("message") or str(data)[:300]
    # Common shapes: content in data.content, data.body, or markdown field
    if isinstance(data, dict):
        for key in ("content", "body", "markdown", "text", "doc"):
            val = data.get(key)
            if isinstance(val, str) and len(val) > 20:
                return val, None
            if isinstance(val, dict):
                inner = val.get("content") or val.get("markdown") or val.get("text")
                if isinstance(inner, str):
                    return inner, None
        # nested under data
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("content", "markdown", "body"):
                if isinstance(inner.get(key), str):
                    return inner[key], None
    return blob[:50000], None


def read_local_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".json",):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "content" in obj:
                return str(obj["content"])
        except json.JSONDecodeError:
            pass
    return text


def extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines()[:30]:
        line = line.strip()
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip() or fallback
        m = re.match(r"<title>([^<]+)</title>", line, re.I)
        if m:
            return m.group(1).strip()
    return fallback


def extract_bullets(content: str, max_items: int = 40) -> list[str]:
    bullets: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if not raw or len(raw) < 6:
            continue
        if BULLET_MARKERS.match(raw):
            text = re.sub(r"^[\s#*-•·\d.)]+", "", raw).strip()
            # Skip title-only markdown headers
            if raw.lstrip().startswith("#") and not any(
                v in text for v in ACTION_VERBS
            ):
                continue
            if len(text) >= 8:
                bullets.append(text[:500])
        elif raw.startswith("#"):
            continue
        elif any(v in raw for v in ACTION_VERBS) and len(raw) < 300:
            bullets.append(raw[:500])
        if len(bullets) >= max_items:
            break
    return bullets


def extract_metrics(content: str, max_items: int = 20) -> list[str]:
    hits: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if raw.startswith("#") or len(raw) < 8:
            continue
        if not METRIC_RE.search(raw):
            continue
        clean = re.sub(r"^[-*•·\d.)]+\s*", "", raw)[:200]
        if clean and clean not in hits:
            hits.append(clean)
        if len(hits) >= max_items:
            break
    return hits


def extract_stack(content: str) -> list[str]:
    low = content.lower()
    found = []
    for kw in STACK_KEYWORDS:
        if kw.lower() in low or kw in content:
            found.append(kw)
    return sorted(set(found))[:15]


def to_intern_voice(text: str, project: str) -> str:
    """Rewrite mentor/team phrasing into first-person intern resume voice."""
    t = text.strip().rstrip("。.")
    # Strip mentor attribution
    t = re.sub(r"^(mentor|导师|正式员工|负责人|owner)[:：]\s*", "", t, flags=re.I)
    t = re.sub(r"^由.+?[负责主导]", "", t)
    # Team → I (bounded replacements)
    t = re.sub(r"^我们(?=[负责参与完成开发实现搭建优化])", "我", t)
    t = re.sub(r"^团队(?=[负责参与完成开发实现搭建优化])", "我", t)
    t = re.sub(r"^团队完成", "我完成", t)
    t = re.sub(r"同学们|团队成员", "我", t)
    # Passive team descriptions
    t = re.sub(r"在(.+?)项目中，?", rf"在{project}中，", t, count=1)
    if project not in t and not any(t.startswith(v) for v in ACTION_VERBS):
        t = f"在{project}中，{t}"
    if not (t.startswith(ACTION_VERBS) or t.startswith("我")):
        t = f"负责{t.lstrip('，,')}"
    if not t.endswith(("。", ".", "）", ")")):
        t += "。"
    return t


def align_with_signals(
    project: str, bullets: list[str], events: list[dict[str, Any]]
) -> list[str]:
    """Keep bullets that overlap with intern agent/git activity keywords."""
    if not events:
        return bullets
    proj_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", project.lower()))
    signal_text = " ".join(
        str(e.get("project", ""))
        + " "
        + " ".join(
            q.get("preview", "")
            for q in (e.get("queries") or [])
        )
        + " "
        + " ".join(c.get("subject", "") for c in (e.get("commits") or []))
        for e in events
    ).lower()
    if not signal_text.strip():
        return bullets

    scored: list[tuple[int, str]] = []
    for b in bullets:
        tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", b.lower()))
        overlap = len(tokens & proj_tokens)
        for tok in tokens:
            if len(tok) > 2 and tok in signal_text:
                overlap += 1
        scored.append((overlap, b))
    scored.sort(key=lambda x: -x[0])
    # Prefer aligned bullets; if none align, still return mentor bullets (user intent)
    return [b for _, b in scored]


def ingest_document(
    cfg: dict[str, Any],
    *,
    project: str,
    content: str,
    source: str,
    source_type: str,
) -> dict[str, Any]:
    root = journal_root(cfg)
    base, raw_dir, inbox_dir, index_path = mentor_paths(root)
    raw_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(project)
    title = extract_title(content, project)
    bullets = extract_bullets(content)
    metrics = extract_metrics(content)
    stack = extract_stack(content)

    raw_path = raw_dir / f"{slug}.md"
    header = (
        f"---\n"
        f"project: {project}\n"
        f"title: {title}\n"
        f"source: {source}\n"
        f"source_type: {source_type}\n"
        f"ingested_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"---\n\n"
    )
    raw_path.write_text(header + content, encoding="utf-8")

    journal = journal_root(cfg)
    rel_raw = raw_path.relative_to(journal).as_posix()

    entry = {
        "slug": slug,
        "project": project,
        "title": title,
        "source": source,
        "source_type": source_type,
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
        "raw_path": rel_raw,
        "bullets": bullets[:25],
        "metrics": metrics[:15],
        "stack": stack,
    }

    index = load_index(index_path)
    projects: list[dict] = index.setdefault("projects", [])
    projects = [p for p in projects if p.get("slug") != slug]
    projects.append(entry)
    index["projects"] = projects
    save_index(index_path, index)
    return entry


def distill_projects(
    cfg: dict[str, Any],
    *,
    subject: str,
    events: list[dict[str, Any]] | None = None,
    align_signals: bool = True,
) -> str:
    root = journal_root(cfg)
    _, _, _, index_path = mentor_paths(root)
    index = load_index(index_path)
    projects: list[dict] = index.get("projects") or []

    mentor_cfg = cfg.get("mentor") or {}
    voice = mentor_cfg.get("distill_voice") or "intern_first"

    lines = [
        f"# Mentor 蒸馏 · {subject}",
        "",
        f"> 由正式员工/导师文档提炼为**第一人称**简历素材 · {datetime.now():%Y-%m-%d}",
        "> 请 Agent 核对与本人实际 commit/会话后再写入 RESUME_LOG。",
        "> 最终只归入三节：**职责 · 产出 · 项目经历**",
        "",
    ]

    if not projects:
        lines.append("_暂无 mentor 文档。先用 `python3 scripts/mentor.py add ...` 导入。_")
        return "\n".join(lines)

    all_duty: list[str] = []
    all_outcome: list[str] = []
    project_sections: list[str] = []

    for proj in projects:
        name = proj.get("project") or proj.get("title") or "项目"
        if proj.get("source"):
            project_sections.append(f"_来源：{proj['source']}_")
            project_sections.append("")

        raw_bullets = proj.get("bullets") or []
        if align_signals and events:
            raw_bullets = align_with_signals(name, raw_bullets, events)

        if voice == "intern_first":
            voiced = [to_intern_voice(b, name) for b in raw_bullets[:12]]
        else:
            voiced = raw_bullets[:12]

        for v in voiced[:6]:
            all_duty.append(f"- {v.rstrip('。')}")

        metrics = proj.get("metrics") or []
        for m in metrics[:8]:
            line = f"- 在{name}中，{m.strip().rstrip('。')}。" if voice == "intern_first" else f"- {m}"
            all_outcome.append(line)

        stack = proj.get("stack") or []
        stack_text = ", ".join(stack[:8]) if stack else "待补充"
        project_sections.extend(
            [
                f"### {name}",
                "",
                f"- **背景**：{name} 业务背景（见 mentor 文档 `{proj.get('slug', '')}`）",
                f"- **负责**：{voiced[0].rstrip('。') if voiced else '待补充'}",
                f"- **产出**：{metrics[0].rstrip('。') if metrics else '待补充量化指标 [待核实]'}",
                f"- **技术栈**：{stack_text}",
                "",
            ]
        )

    lines.extend(["## 职责", ""])
    lines.extend(all_duty[:10] or ["_待从 mentor 文档提炼职责描述。_"])
    lines.extend(["", "## 产出", ""])
    lines.extend(all_outcome[:10] or ["_待补充可量化产出 [待核实]。_"])
    lines.extend(["", "## 项目经历", ""])
    lines.extend(project_sections)

    lines.extend([
        "",
        "## Agent 下一步",
        "",
        "1. 对照 `events.jsonl` / Git commit，删掉未参与的部分。",
        "2. 把 `[待核实]` 换成真实数字或改为「参与/协助」。",
        "3. 按 **职责 / 产出 / 项目经历** 三节追加到 `RESUME_LOG.md`。",
        "",
    ])
    return "\n".join(lines)


def scan_inbox(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    root = journal_root(cfg)
    _, _, inbox_dir, _ = mentor_paths(root)
    if not inbox_dir.exists():
        return []
    results = []
    for path in sorted(inbox_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in (".md", ".txt", ".markdown", ".json"):
            continue
        project = path.stem.replace("_", " ").replace("-", " ")
        content = read_local_file(path)
        entry = ingest_document(
            cfg,
            project=project,
            content=content,
            source=str(path),
            source_type="inbox",
        )
        archive = inbox_dir / "done" / path.name
        archive.parent.mkdir(exist_ok=True)
        path.rename(archive)
        results.append(entry)
    return results
