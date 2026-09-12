"""灯专属省略号强制 normalize。

灯的 canonical 省略号 = `······`（6 个 U+00B7 中点）。
LLM 几乎不会自发产出这种形式、要把所有 ellipsis 变体清洗到这个形式：

  - `…`  (单个 U+2026 horizontal ellipsis = 视觉 3 点)
  - `……` (双 U+2026 = 视觉 6 点)、形式正确但字符不对
  - `………` (3+ U+2026)
  - `...` / `....` / `......` (3+ ASCII period)
  - `···` / `····` 等（中点数量不是 6）
  - `——` / `———` (双破折号、灯不用)
  - `~~` (波浪、不该出现在灯)

→ 全部 normalize 到 `······`（6 个 U+00B7）

设计要点：
  · 已经是 `······`（恰好 6 个 U+00B7）的不动、不计 violation
  · 中点数量不是 6 时（5 / 7 / 8 ...）也 normalize 到 6
  · 破折号 `——` 也清洗（灯 P0 禁破折号替代省略号）
  · 不动正常的单个中点 `·`（< 3 个的中点序列保留、可能是日语片假名分隔等其他用途）
  · 不动数学省略号（`a...b` 中的 ASCII 点也强制清洗、灯不会写代码）
"""
from __future__ import annotations

import re

# 灯 canonical 六点省略号 = 6 个 U+00B7 中点
TOMORI_ELLIPSIS = "······"

# 匹配所有需要被清洗的 ellipsis 变体：
#   …{1,}             - 1 个以上 horizontal ellipsis (… / …… / ……… 都匹配)
#   \.{3,}            - 3 个以上 ASCII period (... / .... / ...... 都匹配)
#   (?:·{3,}\s*)+    - 3 个以上中点、允许中间有空白连接多段
#                       (·· 不动；··· / ······ / ········ 都匹配；
#                        2026-05-18：`······ ······` 这种空白分隔的两段也作为整段归一为 ······、
#                        避免单 bubble 内出现「······ ······」结构）
#   —{2,}             - 2 个以上 em dash (—— / ——— 都匹配、灯禁破折号替代省略号)
_ELLIPSIS_VARIANTS_RE = re.compile(
    r"…+|\.{3,}|(?:·{3,}\s*)+·{3,}|·{3,}|—{2,}",
)


def normalize_ellipsis(text: str) -> tuple[str, int]:
    """把 text 中所有 ellipsis 变体清洗到 `······`。

    Returns:
        (new_text, fixed_count)
        fixed_count = 实际被改写的次数（已经是 `······` 的不计）
    """
    if not text:
        return text, 0

    fixed = 0

    def _sub(m: re.Match) -> str:
        nonlocal fixed
        matched = m.group(0)
        # 已经是 canonical form 不计 violation
        if matched == TOMORI_ELLIPSIS:
            return matched
        fixed += 1
        return TOMORI_ELLIPSIS

    new_text = _ELLIPSIS_VARIANTS_RE.sub(_sub, text)
    return new_text, fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ("嗯…，明白了…", "嗯······，明白了······", 2),
        ("嗯……明白了……", "嗯······明白了······", 2),
        ("嗯...明白了...", "嗯······明白了······", 2),
        ("嗯......明白了......", "嗯······明白了······", 2),
        ("嗯······明白了······", "嗯······明白了······", 0),  # 已是 canonical
        ("嗯···明白了····", "嗯······明白了······", 2),  # 中点数量错
        ("嗯········明白了", "嗯······明白了", 1),  # 8 个中点 → 6
        ("嗯——明白了——", "嗯······明白了······", 2),  # em dash
        ("嗯—明白了", "嗯—明白了", 0),  # 单个 em dash 不动
        ("嗯·明白了··", "嗯·明白了··", 0),  # 1-2 个中点不动
        ("", "", 0),
        ("没有省略号的句子。", "没有省略号的句子。", 0),
        ("混合：嗯…那个...还有……", "混合：嗯······那个······还有······", 3),
        # 2026-05-18：空白分隔的两段省略号合并（避免 bubble 内出现 `······ ······` 结构）
        ("它们衔泥的样子······ ······有点想写进去", "它们衔泥的样子······有点想写进去", 1),
        ("······ ······", "······", 1),  # 两段全空白分隔
        ("······\t······", "······", 1),  # tab 也算
        ("······\n······", "······", 1),  # 跨行也合并
        ("······ ······ ······", "······", 1),  # 三段合一
        ("好的······ ······呢", "好的······呢", 1),  # 文字 + 两段省略号
        ("······好的······", "······好的······", 0),  # 中间有字、各自独立、不合并
    ]
    all_pass = True
    for inp, expected, exp_count in cases:
        out, n = normalize_ellipsis(inp)
        ok = (out == expected) and (n == exp_count)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"[{status}] {inp!r:50} -> {out!r:50} fixed={n} (exp {expected!r}, exp_count={exp_count})")
    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
