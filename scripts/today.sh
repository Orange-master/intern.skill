#!/usr/bin/env bash
# 查看今日 daily（采集通常已由 18:30 自动完成；此脚本可手动补采）
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOURNAL="${HOME}/.实习生-skill"
DAY="$(date +%Y-%m-%d)"

python3 "${SKILL_ROOT}/scripts/collect.py"

DIGEST="${JOURNAL}/daily/${DAY}.md"
if [[ -f "$DIGEST" ]]; then
  echo ""
  cat "$DIGEST"
else
  echo "No digest at ${DIGEST}" >&2
  exit 1
fi
