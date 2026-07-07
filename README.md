# 实习生.skill

把实习期间散落的真实工作记录——**飞书协作**、**Agent 会话**、**Git 提交**——自动沉淀成能写进简历的素材。

实习生的日常分散在三处：飞书里开会、对齐、写文档、勾任务；Claude Code / Codex 里用 Agent 写代码、改需求、解决问题；Git 里提交交付。

本项目做两件事：

1. **自动记录** — 每天后台采集飞书 + Agent + Git，写入 `daily/` 和 `events.jsonl`，你不用管
2. **手动汇总** — 快离职时你自己触发，把整段实习收成标准简历三节

全程本地运行，不上传云端，不需要 API Key。

---

## 自动 vs 手动

| 环节 | 触发方式 | 产出 |
|------|----------|------|
| **每日记录** | **自动**（下班前 + 登录时补采） | `daily/YYYY-MM-DD.md`、`events.jsonl` |
| **汇总 / 写简历** | **手动**（快离职时你跑一条命令） | `reports/intern-*.md` → Agent 精炼 → `RESUME_LOG.md` |

实习期间只需偶尔扫一眼 `daily/` 确认采集正常；**不用每周跑汇总**。

---

## 能干什么

| 能力 | 说明 |
|------|------|
| **飞书协作（核心）** | 日程、已完成任务、工作群消息、你编辑的文档 — 还原「今天干了什么」 |
| **会话采集** | Claude Code、Codex（可选 Cursor）本地会话，提取技术协作线索 |
| **Git 追踪** | 配置仓库里的 commit，作为可验证的交付证据 |
| **Mentor 蒸馏** | 导入导师文档，离职汇总时改写成第一人称简历素材 |
| **离职汇总** | `offboard.sh` / `summarize.py` 手动触发，生成整段实习简历草稿 |
| **简历素材库** | 精炼结果写入 `RESUME_LOG.md`，最终只取 **职责 / 产出 / 项目经历** |

**不能做的：** 不会自动读 Agent 改了哪些文件；不会自动每周帮你写简历；不会编造你没做过的事。

---

## 简历输出格式

最终简历统一为 **三节**（仅离职汇总 / 写简历时产出）：

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

---

## 快速开始

```bash
git clone https://github.com/YOUR_USER/实习生.skill.git
cd 实习生.skill
bash scripts/install.sh

# 飞书授权 + 首次采集（只需一次）
bash scripts/setup-feishu.sh
```

之后每天在**你设的下班时间前 30 分钟**自动采集，数据在 `~/.实习生-skill/daily/` 累积。

**先选岗位**，再编辑 `config.json` 配上 Git 仓库：

```bash
python3 scripts/setup_role.py
```

---

## 原理

```text
  实习期间（自动，每天）
  ─────────────────────
  collect.py（下班前 30 分钟，可配置）
    → events.jsonl + daily/YYYY-MM-DD.md
    你看 daily/ 即可，无需汇总

  快离职时（手动，一次）
  ─────────────────────
  offboard.sh 你的名字
    → reports/intern-*.md（简历草稿）
  Agent 读 reports/ → 按三节写入 RESUME_LOG.md / 输出简历
```

```text
┌─────────────────────────────────────────────────────────────┐
│  采集层（自动）collect.py                                    │
│  飞书 + Agent + Git → events.jsonl + daily/                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ 实习期间只累积，不汇总
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  汇总层（手动）summarize.py / offboard.sh                    │
│  用户离职前触发 → reports/intern-*.md                        │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  精炼层（手动）Claude Code / Codex + SKILL.md                │
│  输出职责 / 产出 / 项目经历三节                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 环境要求

| 依赖 | 用途 |
|------|------|
| **Python 3** | 采集/汇总脚本（标准库） |
| **lark-cli** | 飞书采集（核心，一次性授权） |
| **Claude Code** 和/或 **Codex** | 离职时精炼简历 |
| **Git** | 追踪 commit |
| **macOS**（可选） | 按 `schedule.work_end` 定时自动采集 |

---

## 安装

```bash
bash scripts/install.sh
```

1. 链接 Skill → `~/.claude/skills/`、`~/.codex/skills/`
2. 创建 `~/.实习生-skill/`
3. 复制/迁移 `config.json`
4. macOS 注册定时采集（时间见下方 `schedule`）

```bash
bash scripts/setup-feishu.sh    # 飞书授权 + 首次采集
```

```bash
INSTALL_TARGETS=claude,codex,cursor bash scripts/install.sh
INSTALL_CRON=0 bash scripts/install.sh    # 不要定时任务
```

---

## 配置

`~/.实习生-skill/config.json`，**建议先设岗位，再配 Git 仓库**：

```json
{
  "role": {
    "preset": "frontend",
    "title": "前端开发实习生"
  },
  "schedule": {
    "work_end": "18:00",
    "collect_before_minutes": 30
  },
  "repos": [
    {"path": "~/Projects/my-app", "label": "My App"}
  ],
  "feishu": {
    "enabled": true,
    "calendar": {"enabled": true},
    "tasks": {"enabled": true},
    "messages": {"enabled": true, "work_only": true},
    "docs": {"enabled": true, "mine": true}
  }
}
```

选岗位：`python3 scripts/setup_role.py`（直接说「算法工程师」「数据开发」等即可）。

| 配置块 | 作用 |
|--------|------|
| `schedule` | 下班时间；系统在下班前 30 分钟采集 |
| `role` | 岗位，影响采集侧重点 |
| `repos` | 追踪 commit（**必填**） |
| `feishu.*` | 飞书日程/任务/消息/文档（默认开） |
| `sources.*` | Claude / Codex / Cursor 会话开关 |
| `domains` | 可选，补充岗位关键词 |

---

## 自动采集

在 `config.json` 里设下班时间，默认提前 30 分钟采集：

```json
"schedule": {
  "work_end": "18:00",
  "collect_before_minutes": 30
}
```

上例 → 每天 **17:30** 自动跑 `collect.py`。改完后刷新定时任务：

```bash
INSTALL_CRON=1 bash scripts/install.sh
```

**关机 / 合盖休眠**：到点机器得开着且已登录，否则会错过；**开机登录**会自动补采，离线较久会回补期间数据。长假回来可手动 `python3 scripts/collect.py`。

---

### 实习期间：看今天干了什么（自动已采集）

```bash
cat ~/.实习生-skill/daily/$(date +%Y-%m-%d).md
```

或手动补采一次：

```bash
bash scripts/today.sh
```

不需要跑 `summarize.py`。

### 实习期间：确认自动采集正常

```bash
tail -f ~/.实习生-skill/logs/collect.log
```

### 快离职：手动汇总（核心一步）

```bash
SKILL=~/Projects/实习生.skill   # 或 ~/.claude/skills/实习生.skill

bash $SKILL/scripts/offboard.sh "你的名字"
```

等价于：

```bash
python3 $SKILL/scripts/collect.py
python3 $SKILL/scripts/summarize.py --days 90 --subject "你的名字" --mentor
```

然后在 Agent 里说：

```
读 reports/intern-*.md 和 RESUME_LOG.md，
按职责、产出、项目经历三节写简历。不确定标 [待核实]。
```

### 在 Agent 里

| 你说 | Agent 做 |
|------|----------|
| 「今天干了什么」 | 读 `daily/`，复述，**不汇总** |
| 「写简历 / 离职汇总」 | 跑 `offboard.sh` 或 `summarize.py`，按三节输出 |
| 「蒸馏 mentor 文档」 | `mentor.py add` → 离职汇总时 `--mentor` 合并 |

---

## Mentor 蒸馏（离职汇总时用）

平时可把导师文档导入积累；**汇总时**才蒸馏进简历：

```bash
python3 $SKILL/scripts/mentor.py add --project "项目名" --feishu "URL"
python3 $SKILL/scripts/mentor.py add --project "项目名" --file design.md

# 离职汇总时 --mentor 会自动合并
bash $SKILL/scripts/offboard.sh "你的名字"
```

蒸馏只改语气，写入简历前必须对照自己的 commit / 会话核对。

---

## 数据目录

```
~/.实习生-skill/
├── config.json
├── events.jsonl         # 原始事件（自动累积）
├── state.json           # 增量游标
├── daily/               # ★ 每日摘要（自动，实习期间看这个）
├── RESUME_LOG.md        # 简历素材库（离职汇总后由 Agent 写入）
├── reports/             # intern-*.md（手动 summarize 产出）
├── mentor/
└── logs/                # collect 定时任务日志
```

---

## 采集来源

| 来源 | 默认 | 说明 |
|------|------|------|
| 飞书日程/任务/消息/文档 | 开 | 核心，需 lark-cli 授权 |
| Claude Code / Codex | 开 | 本地会话 jsonl |
| Cursor | 关 | 可选 `INSTALL_TARGETS=...,cursor` |
| Git | 开 | `config.repos` |

---

## 推荐节奏

| 时机 | 做什么 |
|------|--------|
| **安装后** | `setup_role.py` → `setup-feishu.sh`，配好 `repos` |
| **实习期间** | 不用管；偶尔 `cat daily/今天.md` 确认采集正常 |
| **快离职** | `offboard.sh 你的名字` → Agent 写三节简历 |

---

## 项目结构

```
实习生.skill/
├── SKILL.md
├── README.md
├── config.example.json
└── scripts/
    ├── install.sh          # 安装；仅注册 collect 定时任务
    ├── setup-feishu.sh     # 飞书授权
    ├── setup_role.py       # ★ 配置岗位 preset
    ├── today.sh            # 手动查看今日 daily
    ├── offboard.sh         # ★ 离职前手动汇总
    ├── schedule.py         # 计算采集时间
    ├── collect.py          # 自动采集
    ├── summarize.py        # 汇总（手动）
    ├── mentor.py
    ├── lark_collect.py
    └── mentor_distill.py
```

---

## 常见问题

**Q：关机或合盖休眠怎么办？**  
到点机器得开着且已登录。开机登录后会补采；不放心手动 `collect.py`。见上文「自动采集」。

**Q：会自动帮我写简历吗？**  
不会。只自动采集；汇总和写简历要你离职前手动触发 `offboard.sh`。

**Q：飞书段落为空？**  
运行 `bash scripts/setup-feishu.sh` 完成授权。

**Q：collect 采集为 0？**  
检查 Agent 会话路径和 `repos`；删 `state.json` 可强制全量重扫。

**Q：能每周自动 summarize 吗？**  
设计上不支持，也不建议。信号在 `events.jsonl` 里累积，离职一次汇总即可。

**Q：数据会泄露吗？**  
不会上传云端，数据只在 `~/.实习生-skill/`。

---

## 许可证

MIT — 见 [LICENSE](LICENSE)。
