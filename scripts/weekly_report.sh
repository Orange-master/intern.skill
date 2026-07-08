#!/usr/bin/env bash
# 生成本周工作周报，可选发布到飞书文档
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOURNAL="${JOURNAL:-${HOME}/.实习生-skill}"
DATE="${DATE:-$(date +%Y-%m-%d)}"
SUBJECT="${SUBJECT:-}"
PUBLISH="${PUBLISH:-0}"
COLLECT="${COLLECT:-1}"

args=(python3 "${SKILL_ROOT}/scripts/report.py" weekly --date "${DATE}" --journal "${JOURNAL}")
[[ -n "${SUBJECT}" ]] && args+=(--subject "${SUBJECT}")
[[ "${COLLECT}" == "1" ]] && args+=(--collect-first)
[[ "${PUBLISH}" == "1" ]] && args+=(--publish-feishu)

"${args[@]}"
