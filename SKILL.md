---
name: intern-skill
description: >-
  自动采集飞书/Agent/Git 每日工作信号；支持生成日报/周报并发布飞书文档。
  用户说写简历、离职汇总、整段实习总结时使用 summarize；说日报、周报、工作汇报时使用 report.py。
  日常「今天干了什么」只读 daily/。mentor 文档蒸馏走 intern-mentor-distill skill。
metadata:
  requires:
    bins: ["python3", "lark-cli"]
---

# 实习生.skill / resume-journal

安装与运行见 [README.md](README.md)。数据目录：`~/.实习生-skill/`（兼容 `~/.resume-journal`）。

首次使用运行 `setup_role.py` 选岗位。

## 自动 vs 手动

| 环节 | 方式 | 说明 |
|------|------|------|
| **每日记录** | 自动 | `collect.py` 定时跑，写 `events.jsonl` + `daily/` |
| **日报 / 周报** | **手动** | `report.py` 或 `daily_report.sh` / `weekly_report.sh` |
| **汇总 / 写简历** | **手动** | 仅用户明确要求时跑 `summarize.py` 或 `offboard.sh` |

**禁止**在用户未要求时自动运行 `summarize.py` 或改写 `RESUME_LOG.md`。

## Agent 收到请求时

### 「今天干了什么」（日常）

1. 必要时：`collect.py`（通常已自动跑过）
2. 读 `daily/YYYY-MM-DD.md`（含岗位标注）
3. 用自然语言复述；**不汇总**，**不改** RESUME_LOG

### 「写日报 / 生成日报 / 发飞书日报」

1. `python3 <skill-root>/scripts/collect.py`（或 `--collect-first`）
2. `python3 <skill-root>/scripts/report.py daily [--date YYYY-MM-DD] [--publish-feishu]`
   或 `bash <skill-root>/scripts/daily_report.sh`（`PUBLISH=1` 发布飞书）
3. 本地产出：`reports/daily/daily-YYYY-MM-DD.md`
4. 若 `--publish-feishu`：返回飞书文档 URL；可在 `config.json → reports.feishu` 配置存放目录

### 「写周报 / 生成周报 / 发飞书周报」

1. 同上先采集（建议）
2. `python3 <skill-root>/scripts/report.py weekly [--date YYYY-MM-DD] [--publish-feishu]`
   或 `bash <skill-root>/scripts/weekly_report.sh`（`PUBLISH=1` 发布飞书）
3. 本地产出：`reports/weekly/weekly-YYYY-MM-DD.md`（周一日期）

### 「汇总 / 写简历 / 离职整理 / 更新 RESUME_LOG」

仅在用户**明确**要汇总或写简历时：

1. `python3 <skill-root>/scripts/collect.py`（拉最新数据）
2. `python3 <skill-root>/scripts/summarize.py --days 90 --subject <名字> --mentor`  
   或 `bash <skill-root>/scripts/offboard.sh <名字>`
3. 读 `reports/intern-*.md`、`RESUME_LOG.md`、必要时 `events.jsonl`
4. **追加**到 `RESUME_LOG.md`（禁止覆盖）
5. 按下方**三节结构**输出

### 「蒸馏 mentor 文档」

→ 读 **`intern-mentor-distill`** skill（`~/.cursor/skills/intern-mentor-distill/SKILL.md`）。  
离职汇总时仍可在 `summarize.py --mentor` 里合并 mentor 段，但精炼规则以该 skill 为准。

## 日报 / 周报结构

**日报**：今日完成 · 会议与协作 · 代码与交付 · Agent 协作 · 文档沉淀 · 明日计划 · 风险与阻塞

**周报**：本周概览 · 关键产出 · 会议与协作 · 代码与交付 · 文档沉淀 · 每日摘要 · 下周计划 · 风险与阻塞

不确定项标 `[待核实]`；不编造指标。

## 精炼规则（写简历时）

- 只写可核实事实；不确定标 `[待核实]`
- 最终简历**只分三块**：职责、产出、项目经历
- 不写密钥、不 dump 整份 `events.jsonl`、不编造指标

## 最终简历结构

```markdown
## 职责

- 负责 …（岗位级概括，2–4 条）

## 产出

- …（量化或可验证交付，2–5 条）

## 项目经历

### {项目名称}

- **背景**：业务/场景
- **负责**：你具体做了什么
- **产出**：结果与指标
- **技术栈**：…
```

## 追加模板（归入上述三节）

```markdown
<!-- YYYY-MM-DD · {领域} -->

职责条目:
- …

产出条目:
- …

项目经历条目:
### {项目名}
- **背景**: …
- **负责**: …
- **产出**: …
- **技术栈**: …
```
