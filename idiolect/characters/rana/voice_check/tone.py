"""乐奈的语气/越界**诊断**（只报不改）。

  A. 角色阈值：感叹号配额、泡长（p90/硬上限）、不用符号、自称率、口癖禁词
  B. 助手腔/越界：结构级检测器 `idiolect.tone`
     （与 persona card 的【反客服腔硬约束】同源；prompt 让模型不写，这里兜住漏网的）
"""
from __future__ import annotations

from typing import Any

from idiolect.tone import detect

from .thresholds import (
    EXCLAIM_MAX_PER_TURN,
    LEN_HARD,
    LEN_P90,
    RX_EXCLAIM,
    RX_FIRST_PERSON,
    TIC_FORBIDDEN,
    UNUSED_MARKS,
)


def split_bubbles(text: str) -> list[str]:
    """按换行切气泡（本项目的显示单位）。"""
    return [b.strip() for b in str(text or "").split("\n") if b.strip()]


def inspect(reply: str) -> dict[str, Any]:
    """只诊断、不修改。返回 violations（规则名 → 证据列表）。

    助手腔部分走**结构级检测器** `idiolect.tone`（2026-09-11 换）：
    字面黑名单对人工标注实例的召回只有 33%，漏掉「我在。」这类最基本形态
    与全部变体；结构级检测器在同一评测集上召回 83%、真台词误报 0.34%。
    """
    text = str(reply or "")
    bubbles = split_bubbles(text)
    v: dict[str, list[str]] = {}

    # A. 角色专属（乐奈自己的阈值）
    n_ex = len(RX_EXCLAIM.findall(text))
    if n_ex > EXCLAIM_MAX_PER_TURN:
        v.setdefault("exclaim_over_quota", []).append(f"{n_ex} 个感叹号（语料仅 3% 回合有）")
    for b in bubbles:
        if len(b) > LEN_HARD:
            v.setdefault("bubble_too_long", []).append(f"{len(b)} 字 > 硬上限 {LEN_HARD}")
        elif len(b) > LEN_P90:
            v.setdefault("bubble_over_p90", []).append(f"{len(b)} 字 > p90 {LEN_P90}")
        for mark in UNUSED_MARKS:
            if mark in b:
                v.setdefault("unused_mark", []).append(f"{mark}（语料基本不用）")
        fp = len(RX_FIRST_PERSON.findall(b))
        if fp >= 3:
            v.setdefault("first_person_overuse", []).append(f"「我」{fp} 次")
        for word, why in TIC_FORBIDDEN.items():
            if word in b:
                v.setdefault("forbidden_tic", []).append(f"{word}（{why}）")

    # B. 助手腔/越界：结构级检测器——必须传角色名，否则 canon 白名单不生效
    for rule, evs in detect(text, char="乐奈").items():
        v.setdefault(rule, []).extend(evs)
    return v
