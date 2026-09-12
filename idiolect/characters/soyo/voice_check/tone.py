"""素世的语气/越界**诊断**（只报不改）。

两块：
  A. 角色阈值：感叹号配额、泡长、不用符号、自称率、裸本名 ≥2 次
  B. 助手腔/越界：走结构级检测器 `idiolect.tone`（通用六条），
     外加**素世专属** `naming_feeling`（不替对方命名感受——比通用 mind_reading 更宽）
"""
from __future__ import annotations

import re
from typing import Any

from idiolect.tone import detect

from .thresholds import (
    EXCLAIM_MAX_PER_TURN,
    FIRST_PERSON_MAX,
    LEN_HARD,
    LEN_P90,
    RX_BARE_PEER,
    RX_EXCLAIM,
    RX_FIRST_PERSON,
    UNUSED_MARKS,
)

# 素世 canon 专属：不替对方命名感受（比通用 mind_reading 更宽）
NAMING_FEELING = re.compile(
    r"(你(?:现在)?(?:一定|肯定|大概)(?:很|觉得)|"
    r"你(?:是|会)(?:感到|觉得)(?:难过|孤单|委屈|害怕|不安))"
)
_NAMING_FEELING = NAMING_FEELING


def split_bubbles(text: str) -> list[str]:
    return [b.strip() for b in str(text or "").split("\n") if b.strip()]


def inspect(reply: str) -> dict[str, Any]:
    """返回 violations（规则名 → 证据列表）。空 dict = 未命中。"""
    text = str(reply or "")
    bubbles = split_bubbles(text)
    v: dict[str, list[str]] = {}

    def add(rule: str, ev: str) -> None:
        v.setdefault(rule, []).append(ev[:40])

    n_ex = len(RX_EXCLAIM.findall(text))
    if n_ex > EXCLAIM_MAX_PER_TURN:
        add("exclaim_over_quota", f"{n_ex} 个感叹号（语料仅 6% 回合有）")
    for b in bubbles:
        if len(b) > LEN_HARD:
            add("bubble_too_long", f"{len(b)} 字 > 硬上限 {LEN_HARD}")
        elif len(b) > LEN_P90:
            add("bubble_over_p90", f"{len(b)} 字 > p90 {LEN_P90}")
        for mark in UNUSED_MARKS:
            if mark in b:
                add("unused_mark", f"{mark}（语料基本不用）")
        if len(RX_FIRST_PERSON.findall(b)) >= FIRST_PERSON_MAX:
            add("first_person_overuse", f"「我」{len(RX_FIRST_PERSON.findall(b))} 次")
    # 称呼习惯：同一轮 ≥2 次裸本名
    bare = RX_BARE_PEER.findall(text)
    if len(bare) >= 2:
        add("bare_peer_name", f"裸本名 {len(bare)} 次：{'/'.join(bare[:3])}（习惯加「小」）")

    # B. 助手腔/越界：结构级检测器（通用六条）——必须传角色名，否则 canon 白名单不生效
    for rule, evs in detect(text, char="素世").items():
        for ev in evs:
            add(rule, ev)
    # 素世专属：替对方命名感受
    m = NAMING_FEELING.search(text)
    if m:
        add("naming_feeling", m.group(0))
    return v
