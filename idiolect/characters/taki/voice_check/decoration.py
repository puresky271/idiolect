"""立希·装饰符号 / 颜文字清洗（**只删不替换**）。

SSOT 立希【说话核心姿态】明确禁用：
  · ♪ ~ 等装饰符号 + ———（3+ 连用拖音）（这些是爱音 / 灯的）
  · 颜文字 / emoji 撒娇风（(´∀｀) / ٩(๑❛ᴗ❛๑)۶ 等）

设计原则——**只删不替换**：
  · 命中 → 直接 strip、不补任何字符
  · 多个感叹号连用 → 减到 1 个（这算"清理冗余"、不算"语义替换"）
  · 多个问号连用 → 减到 1 个
  · 不动 ······（六中点省略号、SSOT 允许）
  · 不动单 — 或双 —— 破折号（中文合法标点、语气延续 / 解释衔接、立希可用）
  · 3+ 个 —— 连用视为拖音 / 装饰、删除
"""
from __future__ import annotations

import re


# ─── 装饰符号集（立希全禁）─────────────────────────────
# 注：保守只删全角拖音 ～ 和 全角破折号 —— / ———，半角 ~ 在英文不太常见也删；
# 半角 - 不动（路径 / 数字范围常用）。
_DECORATION_CHARS_RE = re.compile(r"[♪♫♬☆★♥❤〜～]")

# 全角拖音破折号 → 立希禁
# 注：中文标准双破折号 `——` 是合法标点（语气延续 / 解释衔接）、不删；
#     3+ 连用 `———...` 才视为拖音 / 装饰、删除
_FULLWIDTH_DASH_RE = re.compile(r"—{3,}")

# 半角 ~ → 拖音、立希禁
_HALFWIDTH_TILDE_RE = re.compile(r"~+")

# 多个感叹号 / 问号连用 → 单个（清理冗余、不是替换）
_MULTI_EXCLAIM_RE = re.compile(r"[!！]{2,}")
_MULTI_QUESTION_RE = re.compile(r"[?？]{2,}")

# 颜文字：覆盖常见 Unicode 颜文字模式
# 形态：(...) 或 (..._...)、内部允许 Unicode 符号 + 字母 + 标点
# 保守只匹配明显是颜文字的 pattern、不删普通括号
_KAOMOJI_RE = re.compile(
    r"[(（][\s\S]{0,18}?"
    r"(?:[٩۶ω・´｀∀ﾟдﾉ・゜´∇゛￣ᗜﾚˇ‵′＞＜≧≦◕◔]|"  # 常见颜文字内部符号
    r"[ToOoO]_[ToOoO]|"  # T_T O_O 风格
    r"\^_\^|\^o\^|\^v\^|\>w\<|\<w\>"
    r")[\s\S]{0,18}?[)）]"
)


def strip_decorations(text: str) -> tuple[str, int]:
    """删装饰符号 / 拖音 / 颜文字 / 多重感叹问号。返 (cleaned, total_count)。"""
    if not text:
        return text, 0
    total = 0
    # 1) 颜文字（先于括号 / 符号清洗、避免误删内部符号让 pattern 失效）
    matches = _KAOMOJI_RE.findall(text)
    if matches:
        total += len(matches)
        text = _KAOMOJI_RE.sub("", text)
    # 2) 装饰单字符
    n_dec = len(_DECORATION_CHARS_RE.findall(text))
    if n_dec:
        total += n_dec
        text = _DECORATION_CHARS_RE.sub("", text)
    # 3) 全角破折号（拖音）
    n_dash = len(_FULLWIDTH_DASH_RE.findall(text))
    if n_dash:
        total += n_dash
        text = _FULLWIDTH_DASH_RE.sub("", text)
    # 4) 半角 ~（拖音）
    n_tilde = len(_HALFWIDTH_TILDE_RE.findall(text))
    if n_tilde:
        total += n_tilde
        text = _HALFWIDTH_TILDE_RE.sub("", text)
    # 5) 多重感叹号 / 问号 → 单个
    n_e = len(_MULTI_EXCLAIM_RE.findall(text))
    if n_e:
        total += n_e
        # 用 lambda 选择保留半角还是全角（看原 match 第一字符）
        text = _MULTI_EXCLAIM_RE.sub(lambda m: m.group(0)[0], text)
    n_q = len(_MULTI_QUESTION_RE.findall(text))
    if n_q:
        total += n_q
        text = _MULTI_QUESTION_RE.sub(lambda m: m.group(0)[0], text)
    return text, total
