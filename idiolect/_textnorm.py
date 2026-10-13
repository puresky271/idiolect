"""匹配用文本归一化：声明过的表示算子在这里一次性抹平，其余一律不碰。

为什么单独成模块：证据合同（检查隐藏值是否进了 messages）与 grounding 评分
（检查回复里的主张）必须用**同一个**归一化口径；两处各写一份，迟早一边改了另一边
没改，于是同一个值在输入侧算「没泄漏」、在输出侧算「说出来了」。

已认证的表示算子（`CERTIFIED_OPERATORS`，自测会逐个跑成对探针确认判决不变）：

  · fullwidth   —— 全角数字/字母/标点 → 半角（NFKC）
  · case        —— ASCII 大小写
  · spaces      —— ASCII 空格、制表、换行、全角空格（U+3000）一律删除
  · digit_group —— 数字分组逗号（`1,200` / `1，200` → `1200`）
  · ellipsis    —— `……` / `...` / `⋯` / `···` 统一删除（省略号不承载事实）

未列出的变换（同义改写、繁简转换、日文假名与汉字互换、数字的中文读法）**不在认证
范围内**：遇到它们，机械匹配可能判不出来，评分侧要给 needs_review 而不是假装读懂。
"""
from __future__ import annotations

import re
import unicodedata

CERTIFIED_OPERATORS = ("fullwidth", "case", "spaces", "digit_group", "ellipsis")

_SPACE_RE = re.compile(r"[\s　]+")
_DIGIT_GROUP_RE = re.compile(r"(?<=\d)[,，](?=\d{3}(?!\d))")
_ELLIPSIS_RE = re.compile(r"(?:…|⋯|\.{2,}|·{2,}|・{2,}|。{3,})")


def normalize_for_match(text: str) -> str:
    """把文本归一到匹配口径。只做 `CERTIFIED_OPERATORS` 列出的变换。"""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.lower()
    value = _DIGIT_GROUP_RE.sub("", value)
    value = _ELLIPSIS_RE.sub("", value)
    value = _SPACE_RE.sub("", value)
    return value


__all__ = ["CERTIFIED_OPERATORS", "normalize_for_match"]
