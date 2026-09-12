"""灯专属：CJK 裸空格补偿——空格当停顿 → `······`。

为什么（2026-08-25 实测 bug）：
  LLM 偶尔用 ASCII 空格代替标点写中文（「······是这样吗 被灯照着······」）、
  这种空格是两句之间**唯一的停顿**。下游出站清洗器
  （chat_server._strip_round_parenthetical_content）删 CJK 间空格时不做补偿、
  直接把两句熔成零标点的连读（「······是这样吗被灯照着······」）。

  灯的 SSOT（tomori/voice.py 省略号规则）：句中停顿用六点 `······`。
  所以这一关把裸空格确定性地补成 `······`——**补偿标点、而不是删掉**。
  voice manifest 里「✗ 嗯 你说的对 很多东西······」反例就是这类输入。

规则（只动"至少一侧是 CJK / 省略号 / CJK 标点"的空格；
Latin / 数字两侧的空格如 `RiNG 排练` 保留、那是正常排版）：
  · CJK 字 + 空格串 + CJK 字                → 一个 `······`
  · 省略号组（含 …/.../···/—— 变体）两侧空格 → 删（省略号本身已是停顿）
  · CJK + 空格 + CJK 标点（，。！？、：；）   → 删
  · CJK 标点 + 空格 + CJK / 省略号           → 删
  · 全角空格（U+3000）与连续多空格同样处理；换行符不动

调用时机：clean_reply 的 Stage 0d（ya_a 三关之后、punctuation 之前）——
  补出来的 `······` 会被 punctuation v5 的 existing-ellipsis 抵消算术计入、
  不会因此叠加出六点轰炸；后续 ellipsis_quota 按配额统一管总量。
"""
from __future__ import annotations

import re

# CJK = 汉字 + 日文假名（本项目回复以中文为主、角色名/歌词偶含假名）
_CJK = r"[\u3040-\u30ff\u4e00-\u9fff]"
# CJK 标点（空格与其相邻时无意义）
_CJK_PUNCT = "，。！？、：；"
# 空格串：ASCII 空格 / tab / 全角空格（不含换行——跨行是段落边界、不动）
_SP = r"[ \t\u3000]+"
# 省略号组变体（与 ellipsis.py 归一范围一致、此时尚未归一、需全变体覆盖）
_ELL = r"(?:…+|\.{3,}|·{3,}|—{2,})"

_CJK_SP_CJK_RE = re.compile(rf"({_CJK}){_SP}(?={_CJK})")
_SP_BEFORE_ELL_RE = re.compile(rf"{_SP}(?={_ELL})")
_ELL_SP_RE = re.compile(rf"({_ELL}){_SP}")
_SP_BEFORE_PUNCT_RE = re.compile(rf"(?<={_CJK}){_SP}(?=[{_CJK_PUNCT}])")
_PUNCT_SP_RE = re.compile(rf"([{_CJK_PUNCT}]){_SP}(?={_CJK}|…|\.|·|—)")


def compensate_cjk_space_pause(text: str) -> tuple[str, int]:
    """把 CJK 语境里的裸空格补偿成 `······` 或删掉（省略号/标点相邻）。

    Returns:
        (new_text, fixed_count)  fixed_count = 被处理的空格簇数
    """
    if not text or not re.search(r"[ \t\u3000]", text):
        return text, 0

    fixed = 0

    def _count_sub(pattern: re.Pattern, repl: str, s: str) -> str:
        nonlocal fixed
        s, n = pattern.subn(repl, s)
        fixed += n
        return s

    # 1. CJK + 空格 + CJK → 停顿 `······`（空格是两句间唯一分隔符的场景）
    text = _count_sub(_CJK_SP_CJK_RE, r"\1······", text)
    # 2. 省略号两侧的空格 → 删（省略号已承担停顿、留着会出 `······ ······`）
    text = _count_sub(_SP_BEFORE_ELL_RE, "", text)
    text = _count_sub(_ELL_SP_RE, r"\1", text)
    # 3. CJK 标点相邻的空格 → 删（空格在标点侧无停顿语义）
    text = _count_sub(_SP_BEFORE_PUNCT_RE, "", text)
    text = _count_sub(_PUNCT_SP_RE, r"\1", text)
    return text, fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # (input, expected_text, expected_fixed)
        # bug case：空格是两句间唯一停顿 → ······
        ("······是这样吗 被灯照着······", "······是这样吗······被灯照着······", 1),
        # 多个空格簇各自补偿
        ("嗯 你说的对 很多东西", "嗯······你说的对······很多东西", 2),
        # 连续多空格 / 全角空格 → 一个 ······
        ("这样吗  真的吗", "这样吗······真的吗", 1),
        ("这样吗　真的吗", "这样吗······真的吗", 1),
        # 省略号两侧空格 → 删、不叠出新组
        ("被灯照着 ······ 亮亮的", "被灯照着······亮亮的", 2),
        ("······ 嗯。", "······嗯。", 1),
        # 变体省略号两侧也算（两侧各 1 处）
        ("亮亮的 ... 好像", "亮亮的...好像", 2),
        # CJK 标点相邻空格 → 删
        ("嗯 ，好", "嗯，好", 1),
        ("好。 明天见", "好。明天见", 1),
        # Latin 相邻空格不动
        ("RiNG 今天有排练", "RiNG 今天有排练", 0),
        ("在 RiNG 排练 嗯", "在 RiNG 排练······嗯", 1),
        # 换行不动
        ("嗯\n好", "嗯\n好", 0),
        # 无空格 / 空串不动
        ("······好像······是这样吧", "······好像······是这样吧", 0),
        ("", "", 0),
    ]
    all_pass = True
    for inp, exp_text, exp_n in cases:
        out, n = compensate_cjk_space_pause(inp)
        ok = (out == exp_text) and (n == exp_n)
        if not ok:
            all_pass = False
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:40} -> {out!r:40} fixed={n} (exp {exp_text!r}, exp_n={exp_n})")
    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
