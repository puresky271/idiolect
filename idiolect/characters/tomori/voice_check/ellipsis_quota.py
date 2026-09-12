"""灯专属：`······` 组数配额——把超额的 `······` 降级回普通停顿。

为什么（2026-08-08 数据）：
  clean_reply 链路只会「加」`······`（punctuation 替换、exclamation_softener、
  ellipsis_pair）、从不「减」。实测 chat_sessions 最近 200 条灯回复：
  90% 消息含 `······`、平均每条 3.3 组、76% 消息 ≥2 组——
  「六点轰炸」从例外变成常态，停顿装饰失去意义、变成阅读噪音。

策略：
  · 每条 bubble 的**裸 `······`** 组数设自适应上限：≤30 字 → 2 组、更长 → 3 组
  · 保留最前 N 组（起手/停顿节奏在句首最有价值）
  · 超额组降级：句中 → 「，」、句末或与既有标点相邻 → 直接去掉
    （不制造 「，，」「，。」连撞）
  · `······？` / `······！`（语义配对）**不计入也不降级**——
    与 opening_throttle 把 PAUSE_Q/PAUSE_X 视作语义 marker 一致
  · 独立 `······` bubble（整条只有省略号）= 1 组、永远低于上限 → 招牌大停顿不受影响

调用时机：clean_reply 的 Stage 4（ellipsis 归一）之后、Stage 5（bubble_expander）之前——
  归一后所有变体都是 canonical `······`（6 中点），按字面计数即可；
  bubble_expander 只在整条纯省略号时扩成 12 中点、发生在配额之后，互不影响。
"""
from __future__ import annotations

import re

_TOMORI_ELLIPSIS_GROUP = "······"

# 裸组（后面不跟 ？/！）才算配额对象
_BARE_GROUP_RE = re.compile(re.escape(_TOMORI_ELLIPSIS_GROUP) + r"(?![？?！!])")

_PUNCT_CHARS = "，。！？、…·—~～"


def demote_excess_ellipsis(text: str, max_groups: int | None = None) -> tuple[str, int]:
    """把超过 max_groups 的裸 `······` 组降级为「，」或去掉。

    Returns:
        (new_text, demoted_count)
    """
    if not text:
        return text, 0
    positions = [m.start() for m in _BARE_GROUP_RE.finditer(text)]
    if max_groups is None:
        max_groups = 2 if len(text) <= 30 else 3
    if len(positions) <= max(0, int(max_groups)):
        return text, 0
    demote_positions = positions[int(max_groups):]
    new = text
    demoted = 0
    for pos in reversed(demote_positions):
        start = pos
        end = pos + len(_TOMORI_ELLIPSIS_GROUP)
        before = new[start - 1] if start > 0 else ""
        after = new[end] if end < len(new) else ""
        if after == "" or after == "\n":
            repl = ""  # 句末 → 去掉
        elif before in _PUNCT_CHARS or after in _PUNCT_CHARS:
            repl = ""  # 与既有标点相邻 → 去掉，避免连撞
        else:
            repl = "，"
        new = new[:start] + repl + new[end:]
        demoted += 1
    return new, demoted


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    fail = 0
    cases = [
        # (input, max_groups, expected_text, expected_demoted)
        # 低于上限不动
        ("嗯······好", None, "嗯······好", 0),
        ("······", None, "······", 0),          # 独立招牌 bubble
        ("······？", None, "······？", 0),       # 语义配对不算裸组
        # 超额降级（>30 字 → 3 组）
        ("写完一段歌词······抬头的时候，窗外的天已经变成橙色的了······你那边呢······今天过得怎么样",
         None, "写完一段歌词······抬头的时候，窗外的天已经变成橙色的了······你那边呢······今天过得怎么样", 0),  # 恰好 3 组
        ("下学期······准备工作······嗯，在想什么方向的事吗······还是在想暑假",
         None, "下学期······准备工作······嗯，在想什么方向的事吗······还是在想暑假", 0),  # 3 组 ≤ 3
        ("熊猫挂件······嗯，她好像确实很喜欢······我之前在池袋看到过一家店······当时就想到她了······嗯",
         None, "熊猫挂件······嗯，她好像确实很喜欢······我之前在池袋看到过一家店······当时就想到她了，嗯", 1),  # 4 组 → 降级最后 1 组
        # 短 bubble（≤30 字 → 2 组）
        ("嗯······那样就好······慢慢找的······",
         None, "嗯······那样就好······慢慢找的", 1),  # 27 字 → cap 2、末尾组去掉
        ("······嗯······好······", 1, "······嗯，好", 2),
        # 语义配对不计入：3 裸组 + 1 配对 → 短 text? (>30字→3) 不动
        ("······我听到了······那你也要记住······不管你在哪里······？",
         None, "······我听到了······那你也要记住······不管你在哪里······？", 0),
        # 相邻标点不连撞
        ("嗯······。好······嗯······对······", 2, "嗯······。好······嗯，对", 2),
        # 显式 max_groups
        ("a······b······c······d", 1, "a······b，c，d", 2),
        ("", None, "", 0),
    ]
    for inp, mg, exp_text, exp_n in cases:
        out, n = demote_excess_ellipsis(inp, mg)
        ok = (out == exp_text and n == exp_n)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:50} -> {out!r:50} n={n} (exp {exp_n})")
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
