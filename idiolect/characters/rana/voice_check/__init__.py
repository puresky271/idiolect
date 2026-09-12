"""乐奈语气后处理（voice_check）。

模块划分（与 tomori / taki / anon 的形态对齐，2026-09-12 拆分）：
  · `thresholds.py`  语料实测阈值 + 正则 + 口癖禁词表
  · `punctuation.py` **无损清洗**：感叹号配额降级、省略号归一、连排句号归一
  · `tone.py`        诊断：角色阈值 + 助手腔/越界（结构级检测器）

两部分设计：
  A. **角色专属语气清洗**（依据金标准语料实测，n=389 条非沉默台词）
     · 感叹号出现率仅 **3%** → 一轮最多一个，多余降级为句号
     · 中位 **6** 字、p90 **12** 字 → 超长回合告警（不截断，只诊断）
     · 破折号 / 波浪号 / ♪ / （ 基本不用 → 出现即告警
     · 自称率仅 **16%** → 一轮内「我」出现 ≥3 次告警（她不以「我」起句）
  B. **确定性助手腔/越界检测**（结构级方案）
     · 关系承诺/存在宣言、读心式点评、替对方下心理结论、工整收束、视觉声称
     · 乐奈另有「不声称看见聊天对象」「不做心理归因」等 manifest 硬约束

设计原则：
  · **清洗只做能无损替换的**（感叹号降级、重复省略号归一），
    任何会改语义的一律只告警不修改
  · `clean_reply` 返回 (text, info)；info 里 `violations` 供上层日志与审计
  · 本模块不依赖主流程 / 运行时状态

公开 API（外部只依赖这些）：`clean_reply` / `inspect` / 阈值常量。
"""
from __future__ import annotations

import re
from typing import Any

from .opener import strip_redundant_ack
from .punctuation import downgrade_exclaims, normalize_ellipsis
from .thresholds import (  # noqa: F401  （re-export，兼容旧导入路径）
    EXCLAIM_MAX_PER_TURN,
    FIRST_PERSON_MAX,
    LEN_HARD,
    LEN_P90,
    RX_ELLIPSIS_RUN,
    RX_EXCLAIM,
    RX_FIRST_PERSON,
    TIC_FORBIDDEN,
    UNUSED_MARKS,
)
from .tone import inspect  # noqa: F401

__all__ = [
    "clean_reply",
    "inspect",
    "EXCLAIM_MAX_PER_TURN",
    "LEN_P90",
    "LEN_HARD",
    "UNUSED_MARKS",
    "FIRST_PERSON_MAX",
    "TIC_FORBIDDEN",
]


def clean_reply(reply: str) -> tuple[str, dict[str, Any]]:
    """乐奈语气清洗。只做**无损**变换，其余只诊断。

    无损变换（不改语义、不改字数分布的非标点部分）：
      1. 超配额感叹号 → 降级为句号（保留最多的那一个）
      2. 连续省略号归一：`··…` 混排统一成 `……`（两个 U+2026）

    ⚠️ 起手确认消减（`opener.strip_redundant_ack`）**故意不在这里**——
    它是风格改写（会删字），会破坏本函数的「无损」契约。
    调用方（`rana.api.post_reply_voice_check`）在清洗之后**单独**调用它。
    """
    text = str(reply or "")
    if not text:
        return text, {"ok": True, "violations": {}, "changed": []}
    changed: list[str] = []

    text, ex_done = downgrade_exclaims(text)
    if ex_done:
        changed.append("exclaim_downgraded")

    text, ell_changes = normalize_ellipsis(text)
    changed.extend(ell_changes)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    violations = inspect(text)
    return text, {"ok": not violations, "violations": violations, "changed": changed}
