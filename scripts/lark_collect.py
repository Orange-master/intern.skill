#!/usr/bin/env python3
"""Collect Feishu IM messages and document activity via lark-cli."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_SCOPES = (
    "search:message im:chat:read im:message.reactions:read "
    "search:docs:read docx:document:readonly "
    "calendar:calendar.event:read task:task:read"
)


def expand_path(p: str) -> Path:
    return Path(p).expanduser()


def iso_range(lookback_days: int, tz_name: str = "Asia/Shanghai") -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    end = datetime.now(tz)
    start = end - timedelta(days=lookback_days)
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    return start.strftime(fmt), end.strftime(fmt)


def run_lark(args: list[str], identity: str = "user") -> dict[str, Any]:
    cmd = ["lark-cli", *args, "--as", identity, "--format", "json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"ok": False, "error": {"type": "missing_binary", "message": "lark-cli not found"}}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    blob = stdout or stderr
    if not blob:
        return {
            "ok": False,
            "error": {"type": "empty_output", "message": "lark-cli returned no output"},
        }
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": {"type": "invalid_json", "message": blob[:500]},
        }
    if isinstance(data, dict) and data.get("ok") is False:
        return data
    if proc.returncode != 0:
        return {"ok": False, "error": data.get("error") or {"message": blob[:500]}}
    return {"ok": True, "data": data}


def missing_scope_hint(resp: dict[str, Any]) -> str | None:
    err = resp.get("error") or {}
    if err.get("subtype") != "missing_scope":
        return None
    missing = err.get("missing_scopes") or []
    scopes = " ".join(missing) if missing else DEFAULT_SCOPES
    return f'lark-cli auth login --scope "{scopes}"'


def effective_lookback_days(feishu: dict[str, Any], since: datetime | None) -> int:
    """Wider window after long offline gaps (shutdown / missed schedule)."""
    default = int(feishu.get("lookback_days") or 7)
    max_gap = int(feishu.get("max_catchup_days") or 30)
    if since is None:
        return default
    delta = datetime.now(timezone.utc) - since.astimezone(timezone.utc)
    days = max(1, delta.days + (1 if delta.seconds else 0))
    return min(days, max_gap)


def flatten_events(data: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in keys:
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


def flatten_messages(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and "message_id" in data:
        return [data]
    return flatten_events(data, ("items", "messages", "message_list", "data", "chats"))


def message_text(msg: dict[str, Any]) -> str:
    body = msg.get("body") or {}
    content = body.get("content") or msg.get("content") or ""
    if isinstance(content, str):
        if content.strip().startswith("{"):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    if parsed.get("text"):
                        return str(parsed["text"]).strip()
                    if parsed.get("title"):
                        return str(parsed["title"]).strip()
            except json.JSONDecodeError:
                pass
        return content.strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("title") or "").strip()
    return str(msg.get("text") or "").strip()


def message_time(msg: dict[str, Any]) -> str:
    for key in ("create_time", "created_at", "timestamp", "time"):
        val = msg.get(key)
        if val:
            if isinstance(val, (int, float)):
                # Feishu often uses seconds or ms
                ts = float(val)
                if ts > 1e12:
                    ts /= 1000
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            return str(val)
    return datetime.now(timezone.utc).isoformat()


def flatten_docs(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in ("items", "docs", "results", "data"):
        val = data.get(key)
        if isinstance(val, list):
            return [d for d in val if isinstance(d, dict)]
    return []


def doc_title(doc: dict[str, Any]) -> str:
    for key in ("title", "name", "doc_title"):
        val = doc.get(key)
        if val:
            return str(val).strip()
    return "untitled"


def doc_token(doc: dict[str, Any]) -> str:
    for key in ("doc_token", "token", "obj_token", "file_token"):
        val = doc.get(key)
        if val:
            return str(val)
    return ""


def is_work_related(
    text: str, keywords: list[str], work_pattern: str | None = None
) -> bool:
    if not text or len(text.strip()) < 4:
        return False
    low = text.lower()
    if any(kw.lower() in low for kw in keywords):
        return True
    pattern = work_pattern or (
        r"完成|上线|修复|排查|提交|发布|对接|开发|实现|优化|调研|整理|总结|"
        r"工单|需求|bug|fix|pr|merge|deploy|review|评审|联调|接口|功能"
    )
    return bool(re.search(pattern, text, re.I))


def collect_messages(
    cfg: dict[str, Any], since: datetime | None
) -> tuple[list[dict[str, Any]], list[str]]:
    feishu = cfg.get("feishu") or {}
    if feishu.get("enabled") is False:
        return [], []
    msg_cfg = feishu.get("messages") or {}
    if msg_cfg.get("enabled") is False:
        return [], []

    identity = feishu.get("identity") or "user"
    lookback = effective_lookback_days(feishu, since)
    start, end = iso_range(lookback, feishu.get("timezone") or "Asia/Shanghai")
    role = cfg.get("_role") or {}
    work_keywords = msg_cfg.get("work_keywords") or role.get("work_keywords") or [
        "完成", "上线", "修复", "排查", "工单", "需求", "PR", "评审", "开发", "联调",
    ]
    work_pattern = role.get("work_pattern")
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    chat_ids: list[str] = list(msg_cfg.get("chat_ids") or [])
    chat_names: dict[str, str] = {}
    if not chat_ids:
        list_resp = run_lark(
            ["im", "+chat-list", "--types", "p2p,group", "--page-size", "20"],
            identity,
        )
        if not list_resp.get("ok"):
            hint = missing_scope_hint(list_resp)
            warnings.append(
                hint or f"chat-list failed: {list_resp.get('error', list_resp)}"
            )
        else:
            chats = flatten_messages(list_resp.get("data") or {})
            if not chats and isinstance(list_resp.get("data"), dict):
                chats = list_resp["data"].get("chats") or []
            for c in chats[: int(msg_cfg.get("max_chats") or 15)]:
                cid = c.get("chat_id") or c.get("id")
                if cid:
                    cid = str(cid)
                    chat_ids.append(cid)
                    chat_names[cid] = (
                        c.get("name") or c.get("chat_name") or c.get("title") or cid
                    )

    for chat_id in chat_ids:
        args = [
            "im",
            "+chat-messages-list",
            "--chat-id",
            chat_id,
            "--start",
            start,
            "--end",
            end,
            "--page-size",
            str(int(msg_cfg.get("page_size") or 50)),
            "--no-reactions",
        ]
        resp = run_lark(args, identity)
        if not resp.get("ok"):
            hint = missing_scope_hint(resp)
            warnings.append(hint or f"chat-messages-list {chat_id}: {resp.get('error')}")
            continue

        messages = flatten_messages(resp.get("data") or {})
        work_msgs: list[dict[str, Any]] = []
        for msg in messages:
            text = message_text(msg)
            if msg_cfg.get("work_only", True) and not is_work_related(
                text, work_keywords, work_pattern
            ):
                continue
            if since:
                try:
                    ts = datetime.fromisoformat(message_time(msg).replace("Z", "+00:00"))
                    if ts < since:
                        continue
                except ValueError:
                    pass
            work_msgs.append(
                {
                    "time": message_time(msg),
                    "text": text[:500],
                    "sender": msg.get("sender", {}).get("name")
                    or msg.get("sender_id")
                    or "",
                    "message_id": msg.get("message_id") or msg.get("id") or "",
                }
            )

        if work_msgs:
            events.append(
                {
                    "type": "feishu_messages",
                    "time": work_msgs[0]["time"],
                    "chat_id": chat_id,
                    "chat_name": chat_names.get(chat_id, chat_id),
                    "count": len(work_msgs),
                    "messages": work_msgs[:20],
                    "domains": ["collaboration"],
                }
            )

    # Global keyword search (optional)
    query = msg_cfg.get("search_query") or ""
    if query or msg_cfg.get("global_search"):
        search_args = [
            "im",
            "+messages-search",
            "--start",
            start,
            "--end",
            end,
            "--page-size",
            "20",
            "--no-reactions",
        ]
        if query:
            search_args.extend(["--query", query])
        resp = run_lark(search_args, identity)
        if resp.get("ok"):
            messages = flatten_messages(resp.get("data") or {})
            hits = []
            for msg in messages:
                text = message_text(msg)
                if not text:
                    continue
                hits.append({"time": message_time(msg), "text": text[:500]})
            if hits:
                events.append(
                    {
                        "type": "feishu_message_search",
                        "time": hits[0]["time"],
                        "query": query or "(browse)",
                        "count": len(hits),
                        "messages": hits[:15],
                        "domains": ["collaboration"],
                    }
                )
        else:
            hint = missing_scope_hint(resp)
            if hint:
                warnings.append(hint)

    return events, warnings


def collect_docs(cfg: dict[str, Any], since: datetime | None) -> tuple[list[dict[str, Any]], list[str]]:
    feishu = cfg.get("feishu") or {}
    if feishu.get("enabled") is False:
        return [], []
    doc_cfg = feishu.get("docs") or {}
    if doc_cfg.get("enabled") is False:
        return [], []

    identity = feishu.get("identity") or "user"
    lookback = doc_cfg.get("edited_since") or f"{feishu.get('lookback_days') or 7}d"
    warnings: list[str] = []

    role = cfg.get("_role") or {}
    doc_query = doc_cfg.get("query")
    if doc_query is None:
        doc_query = role.get("feishu_doc_query") or ""

    args = [
        "drive",
        "+search",
        "--query",
        str(doc_query),
        "--edited-since",
        str(lookback),
        "--sort",
        "edit_time",
        "--page-size",
        str(int(doc_cfg.get("page_size") or 15)),
    ]
    if doc_cfg.get("mine", True):
        args.append("--mine")
    if doc_cfg.get("created_by_me"):
        args.append("--created-by-me")
    for token in doc_cfg.get("doc_tokens") or []:
        pass  # explicit tokens handled below

    resp = run_lark(args, identity)
    events: list[dict[str, Any]] = []

    if not resp.get("ok"):
        hint = missing_scope_hint(resp)
        warnings.append(hint or f"drive +search failed: {resp.get('error')}")
        return events, warnings

    docs = flatten_docs(resp.get("data") or {})
    if not docs and isinstance(resp.get("data"), dict):
        docs = resp["data"].get("docs") or resp["data"].get("entities") or []

    entries = []
    for doc in docs:
        title = doc_title(doc)
        token = doc_token(doc)
        edit_time = (
            doc.get("edit_time")
            or doc.get("update_time")
            or doc.get("modified_time")
            or datetime.now(timezone.utc).isoformat()
        )
        entries.append(
            {
                "title": title,
                "token": token,
                "type": doc.get("type") or doc.get("doc_type") or "doc",
                "url": doc.get("url") or doc.get("link") or "",
                "edit_time": str(edit_time),
            }
        )

    if entries:
        events.append(
            {
                "type": "feishu_docs",
                "time": entries[0].get("edit_time") or datetime.now().isoformat(),
                "count": len(entries),
                "docs": entries[: int(doc_cfg.get("max_docs") or 20)],
                "domains": ["documentation"],
            }
        )

    return events, warnings


def event_start_time(ev: dict[str, Any]) -> str:
    for key in ("start_time", "start", "begin_time"):
        val = ev.get(key)
        if isinstance(val, dict):
            val = val.get("timestamp") or val.get("date_time") or val.get("time")
        if val:
            if isinstance(val, (int, float)):
                ts = float(val)
                if ts > 1e12:
                    ts /= 1000
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            return str(val)
    return ""


def collect_calendar(
    cfg: dict[str, Any], since: datetime | None
) -> tuple[list[dict[str, Any]], list[str]]:
    feishu = cfg.get("feishu") or {}
    if feishu.get("enabled") is False:
        return [], []
    cal_cfg = feishu.get("calendar") or {}
    if cal_cfg.get("enabled") is False:
        return [], []

    identity = feishu.get("identity") or "user"
    tz_name = feishu.get("timezone") or "Asia/Shanghai"
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    # Always fetch today's full agenda for「今天干了什么」
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    resp = run_lark(
        [
            "calendar",
            "+agenda",
            "--start",
            start.strftime(fmt),
            "--end",
            now.strftime(fmt),
        ],
        identity,
    )
    warnings: list[str] = []
    if not resp.get("ok"):
        hint = missing_scope_hint(resp)
        warnings.append(hint or f"calendar +agenda failed: {resp.get('error')}")
        return [], warnings

    raw = resp.get("data") or {}
    events_raw = flatten_events(raw, ("items", "events", "event_list", "data"))
    entries: list[dict[str, Any]] = []
    for ev in events_raw:
        title = str(ev.get("summary") or ev.get("title") or "").strip()
        if not title:
            continue
        start_ts = event_start_time(ev)
        entries.append(
            {
                "title": title,
                "start": start_ts,
                "end": str(ev.get("end_time") or ev.get("end") or ""),
                "location": str(ev.get("location") or ""),
            }
        )

    if not entries:
        return [], warnings
    return [
        {
            "type": "feishu_calendar",
            "time": entries[0].get("start") or now.isoformat(),
            "count": len(entries),
            "events": entries[: int(cal_cfg.get("max_events") or 30)],
            "domains": ["collaboration"],
        }
    ], warnings


def task_timestamp(task: dict[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        val = task.get(key)
        if not val:
            continue
        if isinstance(val, (int, float)):
            ts = float(val)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        text = str(val).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def collect_tasks(
    cfg: dict[str, Any], since: datetime | None
) -> tuple[list[dict[str, Any]], list[str]]:
    feishu = cfg.get("feishu") or {}
    if feishu.get("enabled") is False:
        return [], []
    task_cfg = feishu.get("tasks") or {}
    if task_cfg.get("enabled") is False:
        return [], []

    identity = feishu.get("identity") or "user"
    lookback = effective_lookback_days(feishu, since)
    warnings: list[str] = []

    args = [
        "task",
        "+get-my-tasks",
        "--complete=true",
        "--page-limit",
        str(int(task_cfg.get("page_limit") or 5)),
    ]
    if lookback:
        args.extend(["--created_at", f"-{lookback}d"])

    resp = run_lark(args, identity)
    if not resp.get("ok"):
        hint = missing_scope_hint(resp)
        warnings.append(hint or f"task +get-my-tasks failed: {resp.get('error')}")
        return [], warnings

    raw = resp.get("data") or {}
    tasks = flatten_events(raw, ("items", "tasks", "task_list", "data"))
    entries: list[dict[str, Any]] = []
    since_utc = since.astimezone(timezone.utc) if since else None

    for task in tasks:
        summary = str(task.get("summary") or task.get("title") or "").strip()
        if not summary:
            continue
        done_at = task_timestamp(
            task, "completed_at", "complete_time", "updated_at", "due"
        )
        if since_utc and done_at and done_at < since_utc:
            continue
        entries.append(
            {
                "summary": summary,
                "completed_at": done_at.isoformat() if done_at else "",
                "url": str(task.get("url") or ""),
            }
        )

    if not entries:
        return [], warnings
    return [
        {
            "type": "feishu_tasks",
            "time": entries[0].get("completed_at") or datetime.now(timezone.utc).isoformat(),
            "count": len(entries),
            "tasks": entries[: int(task_cfg.get("max_tasks") or 20)],
            "domains": ["collaboration"],
        }
    ], warnings


def collect_feishu(
    cfg: dict[str, Any], since: datetime | None
) -> tuple[list[dict[str, Any]], list[str]]:
    if (cfg.get("feishu") or {}).get("enabled") is False:
        return [], []
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for collector in (collect_calendar, collect_tasks, collect_messages, collect_docs):
        part, w = collector(cfg, since)
        events.extend(part)
        warnings.extend(w)
    return events, warnings
