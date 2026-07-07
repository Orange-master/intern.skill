#!/usr/bin/env python3
"""Set intern role preset — tailors collection keywords and summarization themes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from role_profiles import ROLE_PRESETS, list_presets, normalize_preset, resolve_role

DEFAULT_JOURNAL = Path.home() / ".实习生-skill"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_role(cfg: dict, preset: str, title: str) -> dict:
    key, err = normalize_preset(preset)
    if err or not key:
        raise SystemExit(err or f"Unknown preset: {preset}")
    cfg.setdefault("role", {})
    cfg["role"]["preset"] = key
    if title:
        cfg["role"]["title"] = title
    elif not cfg["role"].get("title"):
        cfg["role"]["title"] = ROLE_PRESETS[key].get("label", key)
    return cfg


def cmd_list(_: argparse.Namespace) -> None:
    print("可选岗位：\n")
    for key, label in list_presets():
        print(f"  {label}")
    print("\n设置：python3 scripts/setup_role.py")


def cmd_show(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser()
    if not path.exists():
        print(f"Config not found: {path}", file=sys.stderr)
        sys.exit(1)
    cfg = resolve_role(load_config(path))
    role = cfg["_role"]
    print(f"岗位：{role['title']}（{role['preset_label']}）")
    print(f"  领域标签：{', '.join(role['domains'].keys())}")
    print(f"  飞书消息关键词：{', '.join(role['work_keywords'][:8])}…")


def cmd_set(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser()
    cfg = load_config(path) if path.exists() else {}
    cfg = apply_role(cfg, args.preset, args.title or "")
    save_config(path, cfg)

    key = cfg["role"]["preset"]
    resolved = resolve_role(cfg)["_role"]
    label = ROLE_PRESETS[key].get("label", key)
    print(f"Saved → {path}")
    print(f"  岗位：{resolved['title']}（{label}）")
    print(f"  采集将侧重：{', '.join(resolved['domains'].keys())}")
    print("\n重新采集以应用：python3 scripts/collect.py")


def cmd_interactive(args: argparse.Namespace) -> None:
    print("选择实习岗位（影响飞书过滤、领域标签、汇总主题）：\n")
    presets = list_presets()
    for i, (key, label) in enumerate(presets, 1):
        print(f"  {i:2}. {label}")
    print()
    print("输入序号，或直接写岗位名（如：算法工程师、数据开发）")
    choice = input("你的岗位 [默认 1=通用研发]: ").strip() or "1"

    if choice.isdigit():
        idx = int(choice) - 1
        preset = presets[idx][0] if 0 <= idx < len(presets) else "general"
    else:
        preset, err = normalize_preset(choice)
        if err or not preset:
            print(f"\n{err}", file=sys.stderr)
            sys.exit(1)

    default_title = ROLE_PRESETS[preset].get("label", preset)
    title = input(f"简历上的岗位标题 [默认 {default_title}]: ").strip() or default_title
    ns = argparse.Namespace(preset=preset, title=title, config=args.config)
    cmd_set(ns)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure intern role. Accepts Chinese job titles or English preset keys.",
    )
    parser.add_argument("--config", default=str(DEFAULT_JOURNAL / "config.json"))
    parser.add_argument("--list", action="store_true", help="List presets")
    parser.add_argument("--show", action="store_true", help="Show current role")
    parser.add_argument(
        "--preset",
        help="岗位：中文如「算法工程师」「数据开发」，或英文 key 如 frontend",
    )
    parser.add_argument("--title", help="简历岗位标题，如「算法工程师实习生」")
    args = parser.parse_args()

    if args.list:
        cmd_list(args)
    elif args.show:
        cmd_show(args)
    elif args.preset:
        cmd_set(args)
    else:
        cmd_interactive(args)


if __name__ == "__main__":
    main()
