"""素世的**无损**标点清洗。

只做不改语义的变换（超配额感叹号降级、省略号归一、连排句号归一）。
任何会改语义的一律只告警（见 `tone.py`）。
"""
from __future__ import annotations

import re

from .thresholds import EXCLAIM_MAX_PER_TURN, RX_ELLIPSIS_RUN, RX_EXCLAIM


def downgrade_exclaims(text: str) -> tuple[str, bool]:
    """超过配额的感叹号降级为句号（保留前 N 个）。"""
    hits = list(RX_EXCLAIM.finditer(text))
    if len(hits) <= EXCLAIM_MAX_PER_TURN:
        return text, False
    keep = {m.start() for m in hits[:EXCLAIM_MAX_PER_TURN]}
    chars = list(text)
    for m in hits:
        if m.start() not in keep:
            chars[m.start()] = "。"
    return "".join(chars), True


def normalize_ellipsis(text: str) -> tuple[str, list[str]]:
    """省略号归一 + 连排句号归一 + 「。……」合并。返回 (文本, 变更标签)。"""
    changed: list[str] = []
    new_text = RX_ELLIPSIS_RUN.sub("……", text)
    if new_text != text:
        changed.append("ellipsis_normalized")
        text = new_text
    collapsed = re.sub(r"。{2,}", "。", text)
    if collapsed != text:
        changed.append("period_collapsed")
        text = collapsed
    text = re.sub(r"。\s*……", "……", text)
    return text, changed
