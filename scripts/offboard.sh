#!/usr/bin/env bash
# 离职前手动汇总 — 不会自动运行。先采集最新数据，再生成整段实习期简历草稿。
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${HOME}/.实习生-skill/config.json"
SUBJECT="${1:-}"
if [[ -z "$SUBJECT" && -f "$CONFIG" ]]; then
  SUBJECT="$(python3 -c "
import json
from pathlib import Path
c = json.loads(Path('$CONFIG').read_text(encoding='utf-8'))
print((c.get('role') or {}).get('title') or '实习生')
" 2>/dev/null || echo "实习生")"
fi
SUBJECT="${SUBJECT:-实习生}"
DAYS="${OFFBOARD_DAYS:-90}"

echo "采集最新信号..."
python3 "${SKILL_ROOT}/scripts/collect.py"

echo ""
echo "汇总近 ${DAYS} 天 → reports/intern-$(date +%Y-%m-%d).md"
python3 "${SKILL_ROOT}/scripts/summarize.py" --days "${DAYS}" --subject "${SUBJECT}" --mentor

REPORT="${HOME}/.实习生-skill/reports/intern-$(date +%Y-%m-%d).md"
echo ""
echo "Report → ${REPORT}"
echo ""
echo "下一步：在 Claude Code / Codex 里说 —"
echo "  读 ${REPORT} 和 RESUME_LOG.md，按职责/产出/项目经历三节写简历，不确定标 [待核实]。"
