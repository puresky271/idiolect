"""立希·句末撒娇词清洗。

SSOT（taki.voice.VOICE_MANIFEST）规定 5 个撒娇词
绝对禁出现在句末：呢 / 哦 / 啦 / 嘛 / 呀。

设计原则——**只删不替换**：
  · 直接 strip、不补任何字符（不会把「行呀」改成「行」+任何符号）
  · 保留标点（删 "呀" 不删后面的「。」）
  · 不动复合词中的同字（『干啥呢』里的"呢"在『嘛』『啥』『怎』之类后、不删）
"""
from __future__ import annotations

import re

# 句末撒娇词正则：
#   (?<![a-zA-Z干什怎啥么嘛吗哪那这里儿边])
#     · 英文不动
#     · 「干」+「什」+「怎」+「啥」+「么」+「嘛」+「吗」+「哪」+「那」+「这」+「里」+「儿」+「边」
#       后面的粒子受保护：这些是 colloquial 疑问 / 指代 anchor、后跟的「呢/嘛/呀/啦/哦」是疑问助词、不是撒娇
#       例：
#         · 干嘛 / 干嘛呢 / 干嘛呀          ← 干、嘛 保护
#         · 啥呢 / 啥呀 / 有啥嘛            ← 啥 保护
#         · 什么呢 / 什么嘛 / 什么呀          ← 么 保护
#         · 怎么呢 / 怎么呀                ← 怎、么 保护
#         · 哪里呢 / 哪儿呢 / 哪呢          ← 哪 保护
#         · 那呢 / 那啦                   ← 那 保护
#         · 这呢 / 这啦                   ← 这 保护
#         · 你那边呢 / 我这边呢 / 哪边呢      ← 边 保护（2026-09-12：剥呢 + 剥句点会把
#           「你那边呢。」洗成残句「你那边」，乐奈×3、立希×1 实测事故）
#         · 吗呢 (虚假 case but harmless)   ← 吗 保护
#   (?:呢~?|哦~?|啦~?|嘛~?|呀~?) 5 词 + 可选拖音
#   (?=[，。！？!?～~\s]|$)        lookahead：句末位置
_BANNED_TAIL_RE = re.compile(
    r"(?<![a-zA-Z干什怎啥么嘛吗哪那这里儿边])(?:呢~?|哦~?|啦~?|嘛~?|呀~?)(?=[，。！？!?～~\s]|$)"
)


def strip_particle_tail(text: str) -> tuple[str, int]:
    """删句末撒娇词。返 (cleaned, count)。"""
    if not text:
        return text, 0
    count = len(_BANNED_TAIL_RE.findall(text))
    if count == 0:
        return text, 0
    cleaned = _BANNED_TAIL_RE.sub("", text)
    return cleaned, count
