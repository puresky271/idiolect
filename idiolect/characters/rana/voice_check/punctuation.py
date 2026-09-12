"""乐奈的**无损**标点清洗（感叹号配额降级、省略号归一、连排句号归一）。"""
from __future__ import annotations

import re

from .thresholds import EXCLAIM_MAX_PER_TURN, RX_ELLIPSIS_RUN, RX_EXCLAIM


def downgrade_exclaims(text: str) -> tuple[str, bool]:
    """超配额感叹号 → 句号（保留前 EXCLAIM_MAX_PER_TURN 个）。"""
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
    """省略号归一（`··…` 混排 → `……`）+ 连排句号归一 + 「。……」合并。"""
    changed: list[str] = []

    def _norm(m) -> str:
        return "……"

    new_text = RX_ELLIPSIS_RUN.sub(_norm, text)
    if new_text != text:
        changed.append("ellipsis_normalized")
        text = new_text
    # 降级可能产生「。。」这类连排句号 → 归一为一个
    collapsed = re.sub(r"。{2,}", "。", text)
    if collapsed != text:
        changed.append("period_collapsed")
        text = collapsed
    text = re.sub(r"。[ \t]*……", "……", text)
    return text, changed
