"""素世的称呼归一（裸本名 → 「小X」）。

素世的 canon 称呼习惯：对同伴几乎总是加「小」
（金标准 cn train：小灯 83 / 小立希 77 / 小爱音 67 / 小乐奈 38；裸本名只 6 次）。
这里做**强制替换**；诊断（同一轮 ≥2 次裸本名）在 `tone.py` 里、基于原文做。
"""
from __future__ import annotations

from .thresholds import (
    LAMP_CONTEXTS,
    RX_BARE_PEER,
    RX_FULL_NAME,
    RX_MUTSU,
)


def normalize_peer_nicknames(text: str) -> tuple[str, list[str]]:
    """把裸本名强制替换为「小X」（素世的 canon 称呼习惯）。

    顺序很重要：**先换全名，再换裸名**——否则「高松灯」会被先改成「高松小灯」。
    返回 (新文本, 替换记录)。不做替换的场合：
      · 「灯」出现在灯具/灯光类复合词里
      · 已经是「小X」
    """
    if not text:
        return text, []
    out = str(text)
    changed: list[str] = []

    # 1) 姓氏全名 → 小名（高松灯 → 小灯）
    def _full(m) -> str:
        changed.append(f"{m.group(0)}→小{m.group(2)}")
        return f"小{m.group(2)}"

    out = RX_FULL_NAME.sub(_full, out)

    # 2) 裸本名 → 小名；「灯」额外排除灯具语境
    def _bare(m) -> str:
        name = m.group(1)
        if name == "灯":
            window = out[max(0, m.start() - 4): min(len(out), m.end() + 4)]
            if any(ctx in window for ctx in LAMP_CONTEXTS):
                return m.group(0)
        changed.append(f"{name}→小{name}")
        return f"小{name}"

    out = RX_BARE_PEER.sub(_bare, out)

    # 3) 睦 → 小睦
    def _mutsu(m) -> str:
        changed.append("睦→小睦")
        return "小睦"

    out = RX_MUTSU.sub(_mutsu, out)
    return out, changed
