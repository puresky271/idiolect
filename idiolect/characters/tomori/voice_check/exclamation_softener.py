"""灯专属：短感叹/短确认句的标点软化 + 分隔符插入。

规则（用户 2026-05-10 拍板 + 2026-05-12 扩展）：

【规则 A】「啊」/「吗」后直接跟 ，/。 → 换成 `······`
  灯的 「啊」「吗」结尾绝对禁单 ，/。 收尾。
  例：
    ✗「这样啊。」 → ✓「这样啊······」
    ✗「这样吗。」 → ✓「这样吗······」
    ✗「对吗，」  → ✓「对吗······」

【规则 B（2026-05-12 新加）】「啊」后直接跟中文 → 插分隔符
  灯不会「啊+紧接其他文字」（→ 像爱音 / 普通人的起手式），
  必须在「啊」后插入 `······` (70%) 或 `，` (30%) 作为停顿。
  例：
    ✗「啊刚刷到一个小展」 → ✓「啊······刚刷到一个小展」（70%）or「啊，刚刷到一个小展」（30%）
    ✗「啊真好啊」 → ✓「啊······真好啊」（前 啊 后插）

  不动：
    · 啊 + 已有标点（，。？！～······、）→ 不动
    · 啊 + 非中文 / 空白 / 行尾 → 不动
    · 啊 出现在词中间但其后已有标点 → 不动

注：
  · 「吗」不做规则 B（吗+文字 在灯口吻里少见、保守不插）
  · 啊 + ？/！ 不动（那是 ······+？/！ 配对器的责任）
  · 顿号「、」不动（吗、 枚举罕见、保守不动）

历史：
  · v1 (2026-05-10): 啊/吗 + ，/。 → ······
  · v2 (2026-05-10): 加入顿号「、」
  · v3 (2026-05-10): 回退顿号
  · v4 (2026-05-12): 加规则 B（啊+中文）
"""
from __future__ import annotations

import random as _random_default
import re

# 规则 A：「啊」或「吗」紧跟 ，/。
_SOFTEN_RE = re.compile(r"([啊吗])([，。])")

# 规则 B：「啊」后直接跟中文字符（不是标点 / 空白 / 行尾）
# lookahead 排除：已有分隔符、感叹问号、省略号、顿号、波浪
_AFTER_AH_RE = re.compile(
    r"啊(?![，。！？!?～~、······\s\n♪・])"
    r"(?=[一-鿿])"
)

# 规则 B 内部：插哪个分隔符
_INSERT_ELLIPSIS_PROB = 0.70  # 70% ······
_ELLIPSIS = "······"
_COMMA = "，"


def soften_exclamation_endings(text: str) -> tuple[str, int]:
    """规则 A：把 啊/吗 后面的 ，/。 换成 `······`。

    Returns:
        (new_text, fixed_count)
    """
    if not text:
        return text, 0

    fixed = 0

    def _sub(m: re.Match) -> str:
        nonlocal fixed
        fixed += 1
        return m.group(1) + _ELLIPSIS

    new_text = _SOFTEN_RE.sub(_sub, text)
    return new_text, fixed


def insert_separator_after_ah(text: str, rng=None) -> tuple[str, int]:
    """规则 B：「啊」后直接跟中文 → 插 ······ (70%) 或 ， (30%)。

    Returns:
        (new_text, fixed_count)
    """
    if not text:
        return text, 0
    rng = rng or _random_default

    fixed = 0

    def _sub(m: re.Match) -> str:
        nonlocal fixed
        fixed += 1
        sep = _ELLIPSIS if rng.random() < _INSERT_ELLIPSIS_PROB else _COMMA
        return "啊" + sep

    new_text = _AFTER_AH_RE.sub(_sub, text)
    return new_text, fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Rule A: 啊/吗 + ，/。 → ······ ===")
    cases_a = [
        ("这样啊。", "这样啊······", 1),
        ("这样吗。", "这样吗······", 1),
        ("对吗，", "对吗······", 1),
        ("真的啊。", "真的啊······", 1),
        ("好啊，今天怎么样", "好啊······今天怎么样", 1),
        ("对吗，真的啊。", "对吗······真的啊······", 2),
        ("好吗？", "好吗？", 0),
        ("好啊！", "好啊！", 0),
        ("好的", "好的", 0),
        ("吗、好的", "吗、好的", 0),
        ("", "", 0),
    ]
    all_pass = True
    for inp, expected, exp_count in cases_a:
        out, n = soften_exclamation_endings(inp)
        ok = (out == expected) and (n == exp_count)
        if not ok: all_pass = False
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:35} -> {out!r:35} (exp {expected!r})")

    print()
    print("=== Rule B: 啊 + 中文 → 插 ······ / ， ===")
    # 用固定 rng 测试
    cases_b = [
        # (input, hit_count_expected, contains_either_separator)
        ("啊刚刷到一个小展", 1, True),
        ("啊真好啊", 1, True),  # 后面那个 啊 在词尾、不插
        ("啊？", 0, False),
        ("啊！", 0, False),
        ("啊，刚", 0, False),  # 已有 ，
        ("啊。刚", 0, False),
        ("啊······刚", 0, False),
        ("啊\n刚", 0, False),  # 换行
        ("啊", 0, False),  # 单字、行尾
        ("好啊", 0, False),  # 啊 在末尾、后无中文
        ("好啊吗？", 0, False),  # 啊+吗 不是中文 hanzi? 吗 是 hanzi。让我看 — actually 吗 IS 一-鿿 range
    ]
    for inp, exp_n, has_sep in cases_b:
        rng_local = _random_default.Random(42)
        out, n = insert_separator_after_ah(inp, rng_local)
        n_ok = (n == exp_n)
        has = ("······" in out) or ("，" in out) if has_sep else True
        ok = n_ok and (has if has_sep else True)
        if not ok: all_pass = False
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:25} -> {out!r:35} n={n} (exp {exp_n})")

    # 概率分布测试
    print()
    print("=== Rule B 概率分布（100 次 ······ 占比） ===")
    n_ellipsis = 0
    for k in range(100):
        rng_local = _random_default.Random(k)
        out, _ = insert_separator_after_ah("啊真好", rng_local)
        if "啊······真好" in out:
            n_ellipsis += 1
    print(f"  ······ 出现 {n_ellipsis}/100 (期望 ~70)")

    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
