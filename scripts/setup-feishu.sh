#!/usr/bin/env bash
# One-time Feishu setup for 实习生.skill (core signal source).
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FEISHU_SCOPE='search:message im:chat:read search:docs:read docx:document:readonly docx:document im:message.reactions:read calendar:calendar.event:read task:task:read'

if ! command -v lark-cli >/dev/null 2>&1; then
  echo "lark-cli not found. Install it first, then re-run:" >&2
  echo "  bash ${SKILL_ROOT}/scripts/setup-feishu.sh" >&2
  exit 1
fi

echo "Authorizing Feishu scopes (core — calendar / tasks / messages / docs)..."
lark-cli auth login --scope "${FEISHU_SCOPE}"

echo ""
echo "Running first collect..."
python3 "${SKILL_ROOT}/scripts/collect.py"

echo ""
echo "Done. View today:"
echo "  bash ${SKILL_ROOT}/scripts/today.sh"
