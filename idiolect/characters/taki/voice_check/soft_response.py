"""立希·软回应起手词清洗（**只删不替换**）。

SSOT 反例（爱音/素世/灯式撒娇应答、立希绝对禁）：
  · 「嗯嗯」「嗯嗯！」「嗯嗯哦」  → 应只「嗯」或不答
  · 「好的呀」「好的啦」「好的哦」  → 应「行」「嗯」
  · 「真棒哦」「真好啊」「好厉害」  → 应不答 / 短句吐槽
  · 「诶嘿」「嘿嘿」「呐呐」      → 是爱音口癖、立希不说
  · 「对呀」「对呀对呀」          → 应「嗯」

设计原则——**只删不替换**：
  · 命中起手软词 → 整词 strip、不补
  · 不强制改成 立希式（不写成「嗯」），让 LLM 自然处理 strip 后的剩余文本
  · 只删句首位置（避免误删句中的「嗯」）
"""
from __future__ import annotations

import re


# 句首软回应起手词 + 可选后跟的语气词 / 标点尾
# 注：用 lookahead 确保是句首位置（行首 + 可选空白）
_SOFT_RESPONSE_HEADS = [
    r"嗯嗯+",                  # 嗯嗯 / 嗯嗯嗯
    r"对呀对呀",
    r"对呀",
    r"好的呀",
    r"好的啦",
    r"好的哦",
    r"好的~?",                # 好的 / 好的~
    r"诶嘿+",                 # 诶嘿 / 诶嘿嘿
    r"嘿嘿+",                 # 嘿嘿 / 嘿嘿嘿
    r"呐呐+",                 # 呐呐 / 呐呐呐
    r"哎呀+",
    r"哎呦+",
    r"哇哦+",
    r"哇塞+",
    r"真棒哦+",
    r"真棒呀+",
    r"真厉害+",
    r"好棒哦+",
    r"好棒呀+",
    r"好厉害+",
]

# 起手匹配模式：
#   行首（多行 mode）→ 可选空白 → 软词 → 可选语气词 → 可选标点（，。！？!?~～） → 可选空白
_SOFT_HEAD_RE = re.compile(
    r"(?m)^[ \t]*(?:" + "|".join(_SOFT_RESPONSE_HEADS) + r")"
    r"(?:啊|呀|哦|啦|哒|呢)?"            # 可选附加语气词（也一起删）
    r"[，。！？!?~～\s]*",
)


def strip_soft_response(text: str) -> tuple[str, int]:
    """删句首软回应起手词。返 (cleaned, count)。"""
    if not text:
        return text, 0
    count = len(_SOFT_HEAD_RE.findall(text))
    if count == 0:
        return text, 0
    cleaned = _SOFT_HEAD_RE.sub("", text)
    return cleaned, count
