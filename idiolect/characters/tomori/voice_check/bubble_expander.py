"""灯专属：纯省略号 bubble 扩展为 12 中点。

规则（用户 2026-05-10 拍板 / 2026-05-18 收紧）：
  灯如果发送一条**纯** `······`（无任何字、无 ?/!）的 bubble、把它扩成 12 中点
  `············` —— 这是她的招牌「大停顿」/「在想」表达。

  2026-05-18 收紧（用户拍板）：
    带 ？/！ 的纯省略号 bubble（`······？` / `······！`）**不再扩**——
    这两种带语义 marker、语义和纯沉默不同：
      · `······` = 沉默 / 消化 / 在想 → 扩 12 中点（视觉上更沉）
      · `······？` = 无声疑问 / 注意到什么 → 保留 6 中点（语义紧凑、不该被大停顿稀释）
      · `······！` = 突然反应 / 被吓到 → 保留 6 中点（同上）

例：
  「······」      → 「············」（纯停顿、扩展）
  「······？」    → 「······？」（无声疑问、不扩）
  「······！」    → 「······！」（突然反应、不扩）
  「嗯······」   →（不动、不是纯省略号 bubble）
  「嗯，明白了。」 →（不动、和省略号无关）

注意：
  · 「bubble」 = 用 `\\n` 分隔的每一行（前端按行渲染成 chat bubble）
  · 单行 reply 整体被当成一个 bubble
  · 必须在 ellipsis normalize 之后跑、否则 12 中点会被归一回 6
  · 实际 chat 多 bubble 输出依赖 chat_server 的 chunking、那是另一层
"""
from __future__ import annotations

import re

# 6 中点 (canonical) → 12 中点 (大停顿 bubble)
_ELLIPSIS_6 = "······"
_ELLIPSIS_12 = "············"

# 2026-05-18 收紧：只匹配**纯** `······` (无 ?/!)、前后允许空白。
# 带 ?/! 的（`······？` / `······！`）有语义 marker、保留 6 中点不扩。
_ELLIPSIS_ONLY_LINE_RE = re.compile(r"^\s*······\s*$")


def expand_ellipsis_only_bubbles(text: str) -> tuple[str, int]:
    """把纯省略号 bubble 的 ······ 扩展成 ············。

    Returns:
        (new_text, fixed_count)
    """
    if not text:
        return text, 0

    lines = text.split("\n")
    fixed = 0
    new_lines: list[str] = []
    for line in lines:
        if not _ELLIPSIS_ONLY_LINE_RE.match(line):
            new_lines.append(line)
            continue
        # 提取 6 中点之后的尾巴（？！ 等）
        stripped = line.strip()
        # stripped 形如 "······" / "······？" / "······！" / "······？！" 等
        idx = stripped.find(_ELLIPSIS_6)
        if idx < 0:
            new_lines.append(line)  # 防御
            continue
        tail = stripped[idx + len(_ELLIPSIS_6):]
        # 保留前后空白（如有）+ 12 中点 + 尾巴
        leading_ws = line[: len(line) - len(line.lstrip())]
        trailing_ws = line[len(line.rstrip()):]
        new_lines.append(leading_ws + _ELLIPSIS_12 + tail + trailing_ws)
        fixed += 1
    return "\n".join(new_lines), fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # 纯 ······ 扩 12 中点（保留招牌）
        ("······", "············", 1),
        # 2026-05-18 收紧：带 ?/! 不扩、保持 6 中点（语义 marker、不该被大停顿稀释）
        ("······？", "······？", 0),
        ("······！", "······！", 0),
        ("······？！", "······？！", 0),
        # 非纯省略号、不动
        ("嗯······", "嗯······", 0),
        ("······嗯", "······嗯", 0),
        ("嗯，明白了。", "嗯，明白了。", 0),
        ("", "", 0),
        # 多 bubble: 纯 ······ 扩、带 ? 的不扩
        ("······\n嗯", "············\n嗯", 1),
        ("嗯\n······", "嗯\n············", 1),
        ("······\n······？", "············\n······？", 1),  # 第 1 扩、第 2 不扩
        ("  ······  ", "  ············  ", 1),
        ("······\n嗯，明白了。\n······！", "············\n嗯，明白了。\n······！", 1),  # 第 1 扩、第 3 不扩
        # 多 bubble 全是纯 ······ → 都扩
        ("······\n······", "············\n············", 2),
    ]
    all_pass = True
    for inp, expected, exp_count in cases:
        out, n = expand_ellipsis_only_bubbles(inp)
        ok = (out == expected) and (n == exp_count)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"[{status}] {inp!r:40} -> {out!r:50} fixed={n} (exp_count={exp_count})")
    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
