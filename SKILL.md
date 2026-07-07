---
name: intern-skill
description: >-
  自动采集飞书/Agent/Git 每日工作信号；用户主动要求汇总、写简历、离职整理时才运行 summarize。
  用户说写简历、离职汇总、整段实习总结、蒸馏 mentor 时使用；日常「今天干了什么」只读 daily/。
metadata:
  requires:
    bins: ["python3", "lark-cli"]
---

# 实习生.skill

安装与运行见 [README.md](README.md)。数据目录：`~/.实习生-skill/`。

首次使用运行 `setup_role.py` 选岗位。

## 自动 vs 手动

| 环节 | 方式 | 说明 |
|------|------|------|
| **每日记录** | 自动 | `collect.py` 定时跑，写 `events.jsonl` + `daily/` |
| **汇总 / 写简历** | **手动** | 仅用户明确要求时跑 `summarize.py` 或 `offboard.sh` |

**禁止**在用户未要求时自动运行 `summarize.py` 或改写 `RESUME_LOG.md`。

## Agent 收到请求时

### 「今天干了什么」（日常）

1. 必要时：`collect.py`（通常已自动跑过）
2. 读 `daily/YYYY-MM-DD.md`（含岗位标注）
3. 用自然语言复述；**不汇总**，**不改** RESUME_LOG

### 「汇总 / 写简历 / 离职整理 / 更新 RESUME_LOG」

仅在用户**明确**要汇总或写简历时：

1. `python3 <skill-root>/scripts/collect.py`（拉最新数据）
2. `python3 <skill-root>/scripts/summarize.py --days 90 --subject <名字> --mentor`  
   或 `bash <skill-root>/scripts/offboard.sh <名字>`
3. 读 `reports/intern-*.md`、`RESUME_LOG.md`、必要时 `events.jsonl`
4. **追加**到 `RESUME_LOG.md`（禁止覆盖）
5. 按下方**三节结构**输出

### 「蒸馏 mentor 文档」

1. 若无文档：`mentor.py add --file` 或 `--feishu`
2. `mentor.py distill --subject <名字>`（可与 `summarize.py --mentor` 一起在离职汇总时用）
3. 读 `reports/mentor-distill-*.md`
4. 与本人会话 / Git **交叉核对**
5. 按三节追加 `RESUME_LOG.md`

## 精炼规则

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
