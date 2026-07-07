#!/usr/bin/env bash
# Install 实习生.skill — universal skill for Claude Code, Codex, Cursor.
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_NAME="实习生.skill"
JOURNAL="${HOME}/.实习生-skill"
LEGACY_JOURNAL="${HOME}/.resume-journal"
PLIST_LABEL="com.intern-skill.collect"
PLIST="${HOME}/Library/LaunchAgents/${PLIST_LABEL}.plist"
INSTALL_CRON="${INSTALL_CRON:-1}"
# Default: Claude Code + Codex (most users). Add ",cursor" to also link Cursor.
INSTALL_TARGETS="${INSTALL_TARGETS:-claude,codex}"

# Migrate legacy journal path
if [[ -d "$LEGACY_JOURNAL" && ! -e "$JOURNAL" ]]; then
  ln -sfn "$LEGACY_JOURNAL" "$JOURNAL"
  echo "Linked $JOURNAL → $LEGACY_JOURNAL (legacy data)"
fi

mkdir -p "$JOURNAL/daily" "$JOURNAL/logs" "$JOURNAL/reports" \
  "$JOURNAL/mentor/raw" "$JOURNAL/mentor/inbox/done"

chmod +x "$SKILL_ROOT/scripts/collect.py" "$SKILL_ROOT/scripts/install.sh" \
  "$SKILL_ROOT/scripts/lark_collect.py" "$SKILL_ROOT/scripts/summarize.py" \
  "$SKILL_ROOT/scripts/mentor.py" "$SKILL_ROOT/scripts/today.sh" \
  "$SKILL_ROOT/scripts/setup-feishu.sh" "$SKILL_ROOT/scripts/offboard.sh" \
  "$SKILL_ROOT/scripts/setup_role.py" "$SKILL_ROOT/scripts/schedule.py" 2>/dev/null || true

link_skill() {
  local skills_dir="$1"
  local label="$2"
  mkdir -p "$skills_dir"
  # Retire old names
  rm -f "${skills_dir}/resume-journal" "${skills_dir}/${SKILL_NAME}"
  ln -sfn "$SKILL_ROOT" "${skills_dir}/${SKILL_NAME}"
  echo "  ${label} → ${skills_dir}/${SKILL_NAME}"
}

echo "Linking skill package..."
IFS=',' read -ra TARGETS <<< "$INSTALL_TARGETS"
for t in "${TARGETS[@]}"; do
  t="$(echo "$t" | xargs)"
  case "$t" in
    claude)
      link_skill "${HOME}/.claude/skills" "Claude Code"
      ;;
    codex)
      link_skill "${CODEX_HOME:-${HOME}/.codex}/skills" "Codex"
      ;;
    cursor)
      link_skill "${CURSOR_SKILLS_DIR:-${HOME}/.cursor/skills}" "Cursor"
      ;;
    *)
      echo "Unknown INSTALL_TARGETS entry: $t (use claude,codex,cursor)" >&2
      exit 1
      ;;
  esac
done

# User config (do not overwrite); migrate feishu block if outdated
if [[ ! -f "$JOURNAL/config.json" ]]; then
  cp "$SKILL_ROOT/config.example.json" "$JOURNAL/config.json"
  echo "Created $JOURNAL/config.json — edit repos & domain keywords."
else
  python3 - "$JOURNAL/config.json" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
cfg = json.loads(path.read_text(encoding="utf-8"))
feishu = cfg.setdefault("feishu", {})
changed = False

defaults = {
    "enabled": True,
    "identity": "user",
    "timezone": "Asia/Shanghai",
    "lookback_days": 7,
    "calendar": {"enabled": True},
    "tasks": {"enabled": True},
    "messages": {"enabled": True, "work_only": True, "max_chats": 20},
    "docs": {"enabled": True, "mine": True, "edited_since": "7d"},
}
for key, val in defaults.items():
    if key not in feishu:
        feishu[key] = val
        changed = True
    elif isinstance(val, dict) and isinstance(feishu.get(key), dict):
        for sk, sv in val.items():
            if sk not in feishu[key]:
                feishu[key][sk] = sv
                changed = True

if feishu.get("enabled") is False:
    feishu["enabled"] = True
    changed = True

role = cfg.setdefault("role", {})
if "preset" not in role:
    role["preset"] = "general"
    changed = True
if "title" not in role:
    role["title"] = "实习生"
    changed = True

schedule = cfg.setdefault("schedule", {})
if "work_end" not in schedule:
    schedule["work_end"] = "19:00"
    changed = True
if "collect_before_minutes" not in schedule:
    schedule["collect_before_minutes"] = 30
    changed = True

if changed:
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Migrated {path} — feishu enabled as core source.")
PY
fi

# Retire old launchd job
launchctl bootout "gui/$(id -u)/com.resume-journal.collect" 2>/dev/null || true
rm -f "${HOME}/Library/LaunchAgents/com.resume-journal.collect.plist" 2>/dev/null

if [[ "$(uname -s)" == "Darwin" && "$INSTALL_CRON" == "1" ]]; then
  read -r COLLECT_HOUR COLLECT_MINUTE WORK_END COLLECT_AT <<< "$(
    python3 "${SKILL_ROOT}/scripts/schedule.py" "${JOURNAL}/config.json"
  )"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${SKILL_ROOT}/scripts/collect.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${COLLECT_HOUR}</integer>
    <key>Minute</key>
    <integer>${COLLECT_MINUTE}</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${JOURNAL}/logs/collect.log</string>
  <key>StandardErrorPath</key>
  <string>${JOURNAL}/logs/collect.err.log</string>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  launchctl enable "gui/$(id -u)/${PLIST_LABEL}"
  echo "Scheduled collect: daily ${COLLECT_AT} (下班 ${WORK_END} 前 30 分钟) + on login."
else
  echo "Skipped launchd (non-macOS or INSTALL_CRON=0)."
fi

echo ""
echo "Installed ${SKILL_NAME}"
echo "  data → $JOURNAL"
echo ""

FEISHU_SCOPE='search:message im:chat:read search:docs:read docx:document:readonly im:message.reactions:read calendar:calendar.event:read task:task:read'
if command -v lark-cli >/dev/null 2>&1; then
  echo "Feishu (core) — authorize once:"
  echo "  lark-cli auth login --scope \"${FEISHU_SCOPE}\""
else
  echo "WARN: lark-cli not found."
  echo "  Feishu is a core signal source (calendar/tasks/messages/docs)."
  echo "  Install lark-cli, then:"
  echo "  lark-cli auth login --scope \"${FEISHU_SCOPE}\""
fi

echo ""
echo "Setup (recommended order):"
echo "  1. python3 ${SKILL_ROOT}/scripts/setup_role.py     # 选岗位，采集更有针对性"
echo "  2. bash ${SKILL_ROOT}/scripts/setup-feishu.sh        # 飞书授权"
echo ""
echo "Daily (automatic):"
echo "  下班前自动采集 → ~/.实习生-skill/daily/  (时间见 config schedule.work_end)"
echo ""
echo "Before leaving (manual):"
echo "  bash ${SKILL_ROOT}/scripts/offboard.sh \"你的名字\""
echo ""
echo "In Claude Code / Codex:"
echo "  「写简历 / 离职汇总」→ offboard.sh + 三节输出"
echo "  「今天干了什么」→ 只读 daily/，不汇总"
echo ""
echo "Install Cursor too: INSTALL_TARGETS=claude,codex,cursor bash scripts/install.sh"
