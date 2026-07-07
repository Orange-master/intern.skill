#!/usr/bin/env python3
"""Role presets — tailor collection & summarization to intern job type."""

from __future__ import annotations

import copy
import re
from typing import Any

# preset → domains, feishu keywords, theme patterns, doc search hint
ROLE_PRESETS: dict[str, dict[str, Any]] = {
    "general": {
        "label": "通用研发",
        "domains": {
            "engineering": ["api", "bug", "feature", "refactor", "deploy", "接口", "模块"],
            "collaboration": ["需求", "评审", "联调", "文档"],
            "ai_tooling": ["agent", "skill", "mcp", "codex", "claude"],
        },
        "work_keywords": [
            "完成", "上线", "修复", "排查", "工单", "需求", "PR", "评审", "开发", "联调",
        ],
        "work_pattern": (
            r"完成|上线|修复|排查|提交|发布|对接|开发|实现|优化|调研|整理|总结|"
            r"工单|需求|bug|fix|pr|merge|deploy|review|评审|联调|接口|功能"
        ),
        "theme_patterns": [
            (r"code|代码|api|接口|模块|功能", "功能开发"),
            (r"fix|bug|修复|排查|工单", "问题排查"),
            (r"test|测试|验收", "测试验收"),
            (r"deploy|上线|发布", "交付上线"),
            (r"doc|文档|wiki|纪要", "文档沉淀"),
            (r"skill|agent|mcp|codex|claude", "AI 协作提效"),
        ],
        "feishu_doc_query": "",
    },
    "frontend": {
        "label": "前端开发",
        "domains": {
            "frontend": ["react", "vue", "css", "html", "组件", "页面", "ui", "tsx", "jsx"],
            "engineering": ["api", "联调", "性能", "兼容", "埋点"],
            "collaboration": ["需求", "评审", "设计稿", "交互"],
        },
        "work_keywords": [
            "页面", "组件", "联调", "样式", "交互", "上线", "修复", "需求", "评审", "PR",
        ],
        "work_pattern": (
            r"页面|组件|样式|交互|联调|适配|埋点|上线|修复|需求|评审|"
            r"react|vue|css|ui|bug|fix|pr|merge|deploy"
        ),
        "theme_patterns": [
            (r"react|vue|组件|页面|ui|css|tsx|jsx|前端", "前端开发"),
            (r"联调|接口|api", "前后端联调"),
            (r"性能|兼容|适配|埋点", "体验与质量"),
            (r"fix|bug|修复", "问题修复"),
            (r"设计|交互|figma", "设计协作"),
        ],
        "feishu_doc_query": "前端",
    },
    "backend": {
        "label": "后端开发",
        "domains": {
            "backend": ["api", "服务", "接口", "微服务", "数据库", "缓存", "mq"],
            "engineering": ["性能", "重构", "部署", "监控"],
            "collaboration": ["需求", "评审", "联调"],
        },
        "work_keywords": [
            "接口", "服务", "联调", "上线", "修复", "性能", "需求", "评审", "PR", "部署",
        ],
        "work_pattern": (
            r"接口|服务|联调|上线|修复|性能|需求|评审|"
            r"api|bug|fix|pr|merge|deploy|数据库|缓存"
        ),
        "theme_patterns": [
            (r"api|接口|服务|微服务|backend", "后端开发"),
            (r"数据库|sql|缓存|mq|kafka", "数据与中间件"),
            (r"性能|优化|监控", "性能与稳定性"),
            (r"fix|bug|修复|排查", "问题排查"),
            (r"deploy|上线|发布", "交付上线"),
        ],
        "feishu_doc_query": "技术方案",
    },
    "fullstack": {
        "label": "全栈开发",
        "domains": {
            "fullstack": ["api", "页面", "组件", "服务", "全栈"],
            "engineering": ["联调", "部署", "需求", "评审"],
            "ai_tooling": ["agent", "codex", "claude"],
        },
        "work_keywords": [
            "接口", "页面", "联调", "上线", "修复", "需求", "评审", "PR", "部署", "功能",
        ],
        "work_pattern": (
            r"接口|页面|组件|联调|上线|修复|需求|评审|"
            r"api|ui|bug|fix|pr|merge|deploy|功能"
        ),
        "theme_patterns": [
            (r"api|接口|服务|backend", "后端开发"),
            (r"页面|组件|ui|前端|react|vue", "前端开发"),
            (r"联调|全栈|功能", "全栈交付"),
            (r"fix|bug|修复", "问题排查"),
            (r"deploy|上线", "交付上线"),
        ],
        "feishu_doc_query": "",
    },
    "data_engineering": {
        "label": "数据开发 / 数仓",
        "domains": {
            "data_engineering": ["sql", "hive", "spark", "pipeline", "etl", "ods", "dwd", "dim"],
            "warehouse": ["数仓", "仓库", "分层", "分区", "调度"],
            "engineering": ["udf", "采集", "同步"],
        },
        "work_keywords": [
            "sql", "pipeline", "表", "分区", "调度", "上线", "ods", "dwd", "排查", "工单",
        ],
        "work_pattern": (
            r"sql|pipeline|表|分区|调度|上线|ods|dwd|数仓|仓库|etl|"
            r"hive|spark|udf|修复|排查|deploy"
        ),
        "theme_patterns": [
            (r"pipeline|etl|ods|dwd|dim|数仓|仓库", "数据 pipeline / 数仓"),
            (r"sql|hive|spark|分区|调度", "数据开发与调度"),
            (r"udf|解析|字段|同步|采集", "采集与解析"),
            (r"fix|bug|修复|排查|工单", "问题排查"),
            (r"deploy|上线", "交付上线"),
        ],
        "feishu_doc_query": "数仓",
    },
    "data_analytics": {
        "label": "数据分析 / BI",
        "domains": {
            "analytics": ["指标", "报表", "查数", "归因", "看板", "bi"],
            "data": ["sql", "excel", "metabase", "tableau"],
            "collaboration": ["需求", "复盘", "周报"],
        },
        "work_keywords": [
            "指标", "报表", "查数", "分析", "归因", "看板", "需求", "复盘", "sql", "数据",
        ],
        "work_pattern": (
            r"指标|报表|查数|分析|归因|看板|复盘|需求|"
            r"sql|bi|dashboard|数据"
        ),
        "theme_patterns": [
            (r"sql|查数|取数|presto|athena", "取数与分析"),
            (r"指标|报表|看板|bi|dashboard", "指标与报表"),
            (r"归因|复盘|洞察|ab", "分析洞察"),
            (r"需求|评审|对齐", "分析需求"),
        ],
        "feishu_doc_query": "分析",
    },
    "product": {
        "label": "产品",
        "domains": {
            "product": ["需求", "prd", "评审", "方案", "用户", "原型", "埋点"],
            "collaboration": ["会议", "对齐", "调研", "竞品"],
        },
        "work_keywords": [
            "需求", "评审", "方案", "原型", "用户", "调研", "对齐", "上线", "迭代", "PRD",
        ],
        "work_pattern": (
            r"需求|评审|方案|原型|用户|调研|对齐|上线|迭代|"
            r"prd|竞品|功能|发布"
        ),
        "theme_patterns": [
            (r"需求|prd|评审|方案", "需求与方案"),
            (r"用户|调研|竞品|访谈", "用户研究"),
            (r"原型|交互|功能", "产品设计"),
            (r"上线|迭代|发布", "版本交付"),
            (r"数据|指标|埋点", "数据驱动"),
        ],
        "feishu_doc_query": "PRD",
    },
    "design": {
        "label": "设计",
        "domains": {
            "design": ["figma", "视觉", "交互", "组件库", "规范", "ui"],
            "collaboration": ["评审", "走查", "需求", "对齐"],
        },
        "work_keywords": [
            "设计", "交互", "视觉", "走查", "评审", "figma", "规范", "组件", "对齐", "交付",
        ],
        "work_pattern": (
            r"设计|交互|视觉|走查|评审|figma|规范|组件|对齐|交付|"
            r"ui|原型|稿"
        ),
        "theme_patterns": [
            (r"figma|视觉|ui|组件库|规范", "视觉与规范"),
            (r"交互|原型|流程", "交互设计"),
            (r"评审|走查|对齐", "设计协作"),
            (r"交付|上线|迭代", "设计交付"),
        ],
        "feishu_doc_query": "设计",
    },
    "qa": {
        "label": "测试 / QA",
        "domains": {
            "qa": ["用例", "测试", "回归", "自动化", "bug", "验收"],
            "engineering": ["接口", "联调", "环境"],
        },
        "work_keywords": [
            "测试", "用例", "bug", "回归", "验收", "自动化", "联调", "修复", "上线", "冒烟",
        ],
        "work_pattern": (
            r"测试|用例|bug|回归|验收|自动化|联调|修复|上线|冒烟|"
            r"fix|缺陷|提测"
        ),
        "theme_patterns": [
            (r"用例|测试|回归|冒烟|验收", "测试执行"),
            (r"自动化|脚本|ci", "自动化测试"),
            (r"bug|缺陷|修复|排查", "缺陷跟踪"),
            (r"联调|接口|环境", "联调支持"),
        ],
        "feishu_doc_query": "测试",
    },
    "devops": {
        "label": "运维 / DevOps",
        "domains": {
            "devops": ["ci", "cd", "k8s", "docker", "部署", "监控", "告警"],
            "engineering": ["发布", "回滚", "容量", "权限"],
        },
        "work_keywords": [
            "部署", "发布", "监控", "告警", "ci", "容器", "回滚", "修复", "上线", "巡检",
        ],
        "work_pattern": (
            r"部署|发布|监控|告警|ci|容器|回滚|修复|上线|巡检|"
            r"k8s|docker|pipeline|incident"
        ),
        "theme_patterns": [
            (r"deploy|部署|发布|ci|cd", "发布交付"),
            (r"k8s|docker|容器|集群", "基础设施"),
            (r"监控|告警|巡检|容量", "稳定性"),
            (r"回滚|故障|修复|incident", "故障处理"),
        ],
        "feishu_doc_query": "运维",
    },
    "algorithm": {
        "label": "算法",
        "domains": {
            "algorithm": ["模型", "训练", "推理", "nlp", "cv", "召回", "排序"],
            "engineering": ["特征", "实验", "评估", "部署"],
        },
        "work_keywords": [
            "模型", "训练", "实验", "特征", "评估", "上线", "优化", "推理", "需求", "排查",
        ],
        "work_pattern": (
            r"模型|训练|实验|特征|评估|上线|优化|推理|需求|排查|"
            r"auc|召回|排序|badcase"
        ),
        "theme_patterns": [
            (r"模型|训练|微调|finetune", "模型训练"),
            (r"推理|部署|上线|serving", "模型部署"),
            (r"特征|样本|数据集", "特征工程"),
            (r"实验|ab|评估|auc", "实验评估"),
            (r"badcase|排查|优化", "效果优化"),
        ],
        "feishu_doc_query": "算法",
    },
}


# 中文/英文口语 → preset 内部 key。不必记英文 key，setup_role.py 会自动解析。
# 同一口语可能对应多个 preset 时（如单独「数据」），需写更具体：数据开发 / 数据分析。
PRESET_ALIASES: list[tuple[str, str]] = [
    # 算法
    ("算法工程师", "algorithm"),
    ("算法实习", "algorithm"),
    ("算法", "algorithm"),
    ("algorithm", "algorithm"),
    ("ml", "algorithm"),
    # 前端
    ("前端工程师", "frontend"),
    ("前端开发", "frontend"),
    ("前端", "frontend"),
    ("frontend", "frontend"),
    ("fe", "frontend"),
    # 后端
    ("后端工程师", "backend"),
    ("后端开发", "backend"),
    ("后端", "backend"),
    ("backend", "backend"),
    ("be", "backend"),
    ("服务端", "backend"),
    # 全栈
    ("全栈工程师", "fullstack"),
    ("全栈开发", "fullstack"),
    ("全栈", "fullstack"),
    ("fullstack", "fullstack"),
    # 数据 — 细分为开发/数仓 vs 分析
    ("数据仓库", "data_engineering"),
    ("数据开发", "data_engineering"),
    ("数仓开发", "data_engineering"),
    ("数仓", "data_engineering"),
    ("etl", "data_engineering"),
    ("data_engineering", "data_engineering"),
    ("数据分析师", "data_analytics"),
    ("数据分析", "data_analytics"),
    ("商业分析", "data_analytics"),
    ("bi", "data_analytics"),
    ("data_analytics", "data_analytics"),
    ("data", "data_engineering"),  # 旧 preset 名兼容
    # 产品 / 设计 / 测试 / 运维
    ("产品经理", "product"),
    ("产品实习", "product"),
    ("产品", "product"),
    ("product", "product"),
    ("pm", "product"),
    ("设计师", "design"),
    ("设计", "design"),
    ("交互设计", "design"),
    ("ui设计", "design"),
    ("design", "design"),
    ("测试工程师", "qa"),
    ("测试开发", "qa"),
    ("测试", "qa"),
    ("qa", "qa"),
    ("运维工程师", "devops"),
    ("运维", "devops"),
    ("devops", "devops"),
    ("sre", "devops"),
    # 通用
    ("研发", "general"),
    ("开发", "general"),
    ("通用", "general"),
    ("general", "general"),
]

_AMBIGUOUS_HINTS: dict[str, list[str]] = {
    "数据": ["data_engineering（数据开发/数仓）", "data_analytics（数据分析/BI）"],
}


def normalize_preset(raw: str) -> tuple[str | None, str | None]:
    """
    将用户输入（中文岗位名、英文 key、别名）解析为 preset key。
    返回 (key, error_message)。error 非空时 key 为 None。
    """
    text = (raw or "").strip()
    if not text:
        return "general", None

    low = text.lower()

    if low in ROLE_PRESETS:
        return low, None

    # 精确别名（忽略大小写）
    for alias, key in PRESET_ALIASES:
        if text == alias or low == alias.lower():
            return key, None

    # 歧义词：单独「数据」等
    if text in _AMBIGUOUS_HINTS:
        opts = "、".join(_AMBIGUOUS_HINTS[text])
        return None, f"「{text}」太宽泛，请明确：{opts}"

    # 子串匹配：优先最长别名
    hits: list[tuple[int, str, str]] = []
    for alias, key in PRESET_ALIASES:
        if len(alias) < 2:
            continue
        if alias in text or alias.lower() in low:
            hits.append((len(alias), key, alias))
    if hits:
        hits.sort(reverse=True)
        keys = []
        for _, key, _ in hits:
            if key not in keys:
                keys.append(key)
        if len(keys) == 1:
            return keys[0], None
        labels = [f"{ROLE_PRESETS[k].get('label', k)}({k})" for k in keys[:4]]
        return None, f"「{text}」可对应多个岗位，请写更具体：{' / '.join(labels)}"

    # 匹配 preset 中文 label
    label_hits = []
    for key, preset in ROLE_PRESETS.items():
        label = preset.get("label", "")
        if label and (label in text or text in label):
            label_hits.append(key)
    if len(label_hits) == 1:
        return label_hits[0], None

    return None, (
        f"未识别岗位「{text}」。运行 python3 scripts/setup_role.py --list 查看；"
        f"也可直接用中文，如：算法工程师、数据开发、数据分析"
    )


def list_presets() -> list[tuple[str, str]]:
    return [(k, v.get("label", k)) for k, v in ROLE_PRESETS.items()]


def merge_domains(
    user_domains: dict[str, list[str]] | None,
    preset_domains: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = copy.deepcopy(preset_domains)
    for name, kws in (user_domains or {}).items():
        existing = merged.setdefault(name, [])
        for kw in kws:
            if kw not in existing:
                existing.append(kw)
    return merged


def resolve_role(cfg: dict[str, Any]) -> dict[str, Any]:
    """Attach `_role` block and merge preset into runtime config."""
    cfg = copy.deepcopy(cfg)
    role_cfg = cfg.get("role") or {}
    raw_preset = (role_cfg.get("preset") or "general").strip()
    preset_key, preset_err = normalize_preset(raw_preset)
    if preset_err:
        preset_key = "general"
    preset = ROLE_PRESETS.get(preset_key or "general", ROLE_PRESETS["general"])
    preset_key = preset_key or "general"

    title = (role_cfg.get("title") or "").strip() or preset.get("label", "实习生")

    resolved = {
        "title": title,
        "preset": preset_key,
        "preset_label": preset.get("label", preset_key),
        "domains": merge_domains(cfg.get("domains"), preset.get("domains", {})),
        "work_keywords": role_cfg.get("work_keywords") or preset.get("work_keywords", []),
        "work_pattern": role_cfg.get("work_pattern") or preset.get("work_pattern", ""),
        "theme_patterns": role_cfg.get("theme_patterns") or preset.get("theme_patterns", []),
        "feishu_doc_query": role_cfg.get("feishu_doc_query")
        if "feishu_doc_query" in role_cfg
        else preset.get("feishu_doc_query", ""),
    }

    cfg["_role"] = resolved
    cfg["domains"] = resolved["domains"]
    return cfg


def extract_themes_for_role(queries: list[str], theme_patterns: list[tuple[str, str]]) -> list[str]:
    from collections import Counter

    themes: Counter[str] = Counter()
    for q in queries:
        for pat, label in theme_patterns:
            if re.search(pat, q, re.I):
                themes[label] += 1
    return [t for t, _ in themes.most_common(6)]
