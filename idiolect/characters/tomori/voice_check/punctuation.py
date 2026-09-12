"""灯专属标点节奏强制：随机把多个 ，/。 替换成 `······`。

为什么：
  灯 SSOT 规则：几乎不用句号 / 逗号 做停顿、用 `······` 代替。
  但 LLM 即使被 prompt 提醒、还是会输出"嗯，还在想歌词的事，有点停不下来。"
  这种正常中文标点的流畅句子——句子是对的、标点错了。

策略（2026-05-17 v5 升级、解决"已有 ······ 还叠加新的导致六点轰炸"）：
  · 基础曲线（v4）：替换数随 ，/。 总数动态扩展、上限 3
      · 0-1 个 ，/。 → 0（短句保留语气松弛、e.g.「嗯。」不变「嗯······」）
      · 2-3 个     → 1（碎片化起步）
      · 4-5 个     → 2（连续短句、灯味要明显）
      · 6+ 个      → 3（排比句、上限封顶）
  · v5 关键修正：**基础数减去 reply 中已有的 ellipsis groups**——
      LLM 自带 ≥ N 个 `······` 时不再叠加新的（已经够灯味）；
      只在 LLM 输出过流畅（无 `······` 但很多标点）时才补足。

历史：
  · v1 (2026-05-09): 0 个不动、随机挑 1 个替换
  · v2 (2026-05-10): 加入「、」
  · v3 (2026-05-10 用户回退): 撤销 v2、顿号回到不替换
  · v4 (2026-05-12): 替换数随总数动态扩展、上限 3
  · **v5 (2026-05-17)**: 替换数 - 已有 ellipsis 数量、避免六点轰炸——
    用户反馈：LLM 已经自带 4 个 `······` 还要再加 2 个、一条短回复 6 个停顿、过头。

注意：
  · 顿号「、」不动（灯偶尔可用、列举名词时合理）
  · 问号 ？感叹号 ！不动（灯的疑问感叹由 ······？/······！承担、不是单 ?！）
  · 已有 ellipsis 计数包含所有变体（…/……/.../······/—— 等、与 ellipsis.py 归一化范围一致）
  · 函数名保留 `random_replace_one_punct` 兼容老调用方、实际可替换多个
"""
from __future__ import annotations

import random
import re


_TARGET_PUNCT = ("，", "。")

# 替换数量曲线：n 个 ，/。 → 替换几个
# index = n、value = 替换数；超出列表长度时用 _REPLACE_CAP
_REPLACE_CAP = 3

# 2026-05-17 v5: 计数 reply 里已有的 ellipsis groups（所有变体、和 ellipsis.py 同范围）
# 用于动态减少替换数、避免 LLM 自带 ······ 时还叠加新的
_EXISTING_ELLIPSIS_RE = re.compile(r"…+|\.{3,}|·{3,}|—{2,}")


def _count_existing_ellipsis_groups(text: str) -> int:
    """count existing ellipsis groups in text (all variants)."""
    if not text:
        return 0
    return len(_EXISTING_ELLIPSIS_RE.findall(text))


def _replace_count_for(n_punct: int, n_existing_ellipsis: int = 0) -> int:
    """n_punct 个 ，/。 + n_existing_ellipsis 个已有 ······ → 还要替换几个。

    base = 标点数对应的目标替换数（v4 曲线）
    实际 = max(0, base - existing)，保护 LLM 已经自带的 ······
    """
    if n_punct < 2:
        base = 0
    elif n_punct <= 3:
        base = 1
    elif n_punct <= 5:
        base = 2
    else:
        base = _REPLACE_CAP  # 6+ → 3 上限
    # v5: 减去 LLM 已经自带的 ellipsis 数、避免叠加爆炸
    return max(0, base - max(0, n_existing_ellipsis))


_FIRST_PUNCT_RE = re.compile(r"^([^，。]*?)([。])(?!\s*$)")


def _replace_first_sentence_period(text: str) -> tuple[str, bool]:
    """2026-05-19 用户拍板：reply 的**首句末尾**如果是「。」、强制改成「······」。

    "首句"指 reply 的开头到第一个「。」之间的内容。
    bug case：「今天没有。周三才有排练······」「嗯。记对了······」
      —— 首句用「。」做断点不符合灯的节奏 canon、应该是「······」。

    判定：
      · regex 匹配 reply 开头第 1 个「。」（前面不含「，」或「。」）
      · 该「。」**不能**是 reply 的最末字（后面还有非空白内容）—— 即它必须是"句间断点"
      · 满足则替换为「······」

    返回 (new_text, replaced_bool)。
    """
    if not text or "。" not in text:
        return text, False
    m = _FIRST_PUNCT_RE.match(text)
    if not m:
        return text, False
    # 替换匹配到的「。」为 ······
    period_start = m.start(2)
    new_text = text[:period_start] + "······" + text[period_start + 1:]
    return new_text, True


def random_replace_one_punct(text: str) -> tuple[str, int]:
    """Randomly replace N of ，/。 in text with `······`、N grows with punct count
    but is reduced by existing ellipsis groups in the text.

    Behavior:
      base = f(标点数): 0-1→0, 2-3→1, 4-5→2, 6+→3
      actual = max(0, base - existing_ellipsis_groups)

    2026-05-19 v6: 在 base 曲线之前先做"首句末尾「。」→ ······"强制替换、
                   独立于 base/existing 计数。这条计入 replaced_count。

    Returns:
        (new_text, replaced_count)
    """
    if not text:
        return text, 0

    # 2026-05-19 v6: Step 0 — 首句末尾「。」 → 「······」（独立、不计入 base 曲线扣减）
    text, first_replaced = _replace_first_sentence_period(text)
    extra = 1 if first_replaced else 0

    positions = [i for i, ch in enumerate(text) if ch in _TARGET_PUNCT]
    n_punct = len(positions)
    n_existing = _count_existing_ellipsis_groups(text)
    k = _replace_count_for(n_punct, n_existing)
    if k == 0:
        return text, extra

    # 随机挑 k 个位置、倒序替换（避免 index shift）
    chosen = sorted(random.sample(positions, k), reverse=True)
    new_text = text
    for pos in chosen:
        new_text = new_text[:pos] + "······" + new_text[pos + 1:]
    return new_text, k + extra


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    random.seed(42)  # deterministic for test
    cases = [
        ("嗯，还在想歌词的事，有点停不下来。", 1),  # 3 个 → base 1、existing 0 → 1
        ("……", 0),  # 没 ，/。
        ("嗯，", 0),  # 1 个 → 0
        ("嗯。", 0),
        ("嗯，明白了。", 1),  # 2 个 → 1
        ("嗯", 0),
        ("", 0),
        # v5: existing ellipsis 抵消逻辑 ────────────────────
        # 「嗯······，明白了······」: 标点 1 → base 0 → 0 (已 existing 2)
        ("嗯······，明白了······", 0),
        # 「嗯······，明白了，」: 标点 2 → base 1、existing 1 → max(0, 1-1)=0
        ("嗯······，明白了，", 0),
        # 用户实战 case: LLM 自带 4 个 ······、4 个标点（base=2）→ existing 4 → 0 不再叠加
        # 2026-05-19 v6 调整：首句末尾「······嗯。」「」中的「。」会被 v6 首句规则替换、count = 1
        # 实战中这种 reply 不会原样进 cleaner（chat_server compound_split 已抽走 `······嗯。`）
        ("······嗯。······谢谢。······有你这句话······感觉夜空更亮了。", 1),
        # 同 5 个标点但 existing 0 → 2
        ("嗯，蓝色不是忧郁。是水，是天空，傍晚河面亮亮的那种光。", 2),  # base 2、existing 0 → 2
        # 6 个标点 existing 0 → 3
        ("嗯，蓝色不是忧郁，是水，是天空，傍晚河面亮亮的光，温柔。", 3),
        # 6 个标点 existing 1 → max(0, 3-1) = 2
        ("嗯······，蓝色不是忧郁，是水，是天空，傍晚河面亮亮的光，温柔。", 2),
        # 6 个标点 existing 3 → max(0, 3-3) = 0 不再加
        ("嗯······，蓝色······不是忧郁，是水······，是天空，傍晚河面亮亮的光，温柔。", 0),
        # 4 个标点 existing 1 → base 2 - 1 = 1
        ("嗯，蓝色不是忧郁······。是水，是天空。", 1),
        # 顿号不动
        ("嗯、笔记本、还有创可贴", 0),
        # 问号感叹号不动
        ("？！", 0),
        # 各种 ellipsis 变体都算 existing：
        ("嗯…明白了，然后呢，", 0),  # … 算 1、existing 1、base 1（2 个标点）→ 0
        ("嗯......明白了，然后呢，", 0),  # ... 算 1、existing 1、base 1 → 0
        ("嗯——明白了，然后呢，", 0),  # —— 算 1、existing 1、base 1 → 0
        # 2026-05-19 v6：首句末尾「。」→ ······ 强制替换
        # 旧 v5 不替换、新 v6 仍替换（独立于 base 曲线、计入 replaced_count）
        # 用户实战 case
        ("今天没有。周三才有排练······", 1),  # 首「。」改、existing 1 抵消 base、所以 final count = 1 (来自首句)
        ("嗯。记对了······", 1),  # 同上
        ("没有。在教室。刚把笔记本收进书包······", 1),  # 首「。」改、第 2 个「。」由 base 决定（3 标点 base 1 - existing 1 = 0）→ count = 1 来自首句
        ("嗯······好。待会见", 1),  # 首句「嗯······好」末尾「。」改、count=1
        # 边界：单 bubble 末尾「。」（没有后续内容）→ 不动（SSOT 允许）
        ("嗯。", 0),  # 后接 EOF、不算"首句中间"
        ("好。", 0),
    ]
    for inp, exp_count in cases:
        out, n = random_replace_one_punct(inp)
        status = "PASS" if n == exp_count else "FAIL"
        print(f"[{status}] {inp!r:60} -> {out!r:60} replaced={n} (exp {exp_count})")
