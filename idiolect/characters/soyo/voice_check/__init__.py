"""素世语气后处理（voice_check）。

模块划分（与 tomori / taki / anon 的形态对齐，2026-09-12 拆分）：
  · `thresholds.py`  语料实测阈值 + 正则 + 称呼词表
  · `nickname.py`    **强制替换**：裸本名 → 「小X」（含全名与灯具语境排除）
  · `punctuation.py` **无损清洗**：感叹号配额降级、省略号归一、连排句号归一
  · `tone.py`        诊断：角色阈值 + 助手腔/越界（结构级检测器）

两部分设计：
  A. **角色专属语气清洗/检测**（依据金标准语料实测，n=862 条非沉默台词）
     · 感叹号出现率仅 **6%** → 一轮最多一个，多余降级为句号
     · 中位 **16** 字、p90 **30** 字 → 超长回合告警
     · 顿号 / 破折号 / 波浪号 / ♪ 基本不用 → 出现即告警
     · 称呼习惯：对同伴几乎总是加「小」（小灯 83 / 小立希 77 / 小爱音 67 / 小乐奈 38）
       → 同一轮内出现 ≥2 次**不带「小」**的同伴本名时告警
  B. **确定性助手腔/越界检测**（v41 报告 §6 的「方案 C」）
     · 2026-09-12 起与乐奈统一走**结构级**检测器 `turn_agents.assistant_tone`：
       字面黑名单对 v41 人工实例召回仅 33%，结构级 83%、真台词误报 0.34%。
     · 素世专属 canon：**不替对方命名感受**（`tone.NAMING_FEELING` 单独判）

设计原则：清洗只做无损替换，任何会改语义的一律只告警。

公开 API（外部只依赖这些）：`clean_reply` / `inspect` / `normalize_peer_nicknames` / 阈值常量。
"""
from __future__ import annotations

from typing import Any

from .nickname import normalize_peer_nicknames
from .punctuation import downgrade_exclaims, normalize_ellipsis
from .thresholds import (  # noqa: F401  （re-export，供 test / bench 按旧路径取用）
    EXCLAIM_MAX_PER_TURN,
    FIRST_PERSON_MAX,
    LEN_HARD,
    LEN_P90,
    PEERS,
    SURNAMES,
    UNUSED_MARKS,
    LAMP_CONTEXTS,
    RX_BARE_PEER,
    RX_EXCLAIM,
    RX_ELLIPSIS_RUN,
    RX_FIRST_PERSON,
    RX_FULL_NAME,
    RX_MUTSU,
)
from .tone import NAMING_FEELING, inspect  # noqa: F401

__all__ = [
    "clean_reply",
    "inspect",
    "normalize_peer_nicknames",
    "EXCLAIM_MAX_PER_TURN",
    "LEN_P90",
    "LEN_HARD",
    "UNUSED_MARKS",
    "FIRST_PERSON_MAX",
]


def clean_reply(reply: str) -> tuple[str, dict[str, Any]]:
    """素世语气清洗。

    两类变换：
      · **强制替换**（canon）：裸本名 → 「小X」（含全名与灯具语境排除）
      · **无损清洗**：超配额感叹号降级、连排句号归一、省略号归一

    诊断在**替换之前**基于原文做，这样 `violations` 反映的是模型原始输出，
    而不是被自己改过的文本（否则裸名告警永远看不到）。
    """
    text = str(reply or "")
    if not text:
        return text, {"ok": True, "violations": {}, "changed": []}
    # 先用原文诊断
    violations = inspect(text)

    changed: list[str] = []
    text, nick_changed = normalize_peer_nicknames(text)
    if nick_changed:
        changed.append(f"peer_nickname:{len(nick_changed)}")

    text, ex_done = downgrade_exclaims(text)
    if ex_done:
        changed.append("exclaim_downgraded")

    text, ell_changes = normalize_ellipsis(text)
    changed.extend(ell_changes)

    import re as _re
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()

    return text, {"ok": not violations, "violations": violations, "changed": changed}
