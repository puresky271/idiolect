"""灯专属：`······` + ？/！ 配对强制。

规则（来自用户 2026-05-10 拍板）：
  灯的 ？ 和 ！ 几乎都以 `······？` / `······！` 形式出现、不是单独 ？/！。
  LLM 不太可能遵守这点、需要后置清洗。

匹配 ？ 或 ！、检查前面是否已是 `······`（6 个 U+00B7 中点）：
  · 已是 `······` → 跳过
  · 不是 `······` → 在 ？/！ 前补 `······`

例：
  ✗「真的吗？」 → ✓「真的吗······？」
  ✗「明白了！」 → ✓「明白了······！」
  ✓「真的吗······？」 → ✓「真的吗······？」（不动）

注：
  · 半角 ?/! 也补 `······`（但 ······? 不是 canonical 形式、仍然先补再 ellipsis 兜底归一）
  · 多个 ？！ 各自独立判断（连续 ？？？ 各自加 `······`）
  · 只针对中文 ？！；英文 ?! 转中文是 sanitize_no_markdown 的责任、不在此处
"""
from __future__ import annotations

# 灯 canonical 六点
_ELLIPSIS = "······"
_ELLIPSIS_LEN = len(_ELLIPSIS)


def pair_ellipsis_with_question_excl(text: str) -> tuple[str, int]:
    """在 ？/！ 前补 `······`、除非已经有了。

    Returns:
        (new_text, fixed_count)
    """
    if not text:
        return text, 0

    fixed = 0
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in ("？", "！"):
            # 检查前面 6 个字符是否是 `······`
            already_paired = (
                i >= _ELLIPSIS_LEN
                and text[i - _ELLIPSIS_LEN: i] == _ELLIPSIS
            )
            if not already_paired:
                # 也要检查 out 末尾——可能上一步刚加进 out 的也是 `······`
                prev_in_out = "".join(out[-_ELLIPSIS_LEN:]) if len(out) >= _ELLIPSIS_LEN else ""
                if prev_in_out != _ELLIPSIS:
                    out.append(_ELLIPSIS)
                    fixed += 1
            out.append(ch)
        else:
            out.append(ch)
    return "".join(out), fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ("真的吗？", "真的吗······？", 1),
        ("明白了！", "明白了······！", 1),
        ("这样吗？", "这样吗······？", 1),
        ("真的吗······？", "真的吗······？", 0),  # 已配对
        ("明白了······！", "明白了······！", 0),  # 已配对
        ("？", "······？", 1),  # 单独 ？
        ("！", "······！", 1),  # 单独 ！
        ("？！", "······？······！", 2),  # 连续 ？！ 各自补
        ("······？！", "······？······！", 1),  # 第一个已配对、第二个补
        ("没有问号感叹号", "没有问号感叹号", 0),
        ("", "", 0),
        ("嗯，明白了", "嗯，明白了", 0),  # 没 ？ ！
        ("好吗？这样吧。", "好吗······？这样吧。", 1),  # 中间一个 ？
    ]
    all_pass = True
    for inp, expected, exp_count in cases:
        out, n = pair_ellipsis_with_question_excl(inp)
        ok = (out == expected) and (n == exp_count)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"[{status}] {inp!r:30} -> {out!r:35} fixed={n} (exp {expected!r}, exp_count={exp_count})")
    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
