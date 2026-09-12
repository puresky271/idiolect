"""乐奈起手确认的**冗余消减**（非 prompt 手段，2026-09-12）。

问题（语料实测）：
  乐奈原作起手 **55% 是名词/体言直出**（五人最高），语气词起手只有 **8%**；
  而生产臂 93%（无 turn_logic）→ 67%（13 场景全开）的回复以「嗯。」「嗯？」开头。
  两次 prompt 侧 A/B 都是负结论（+2.04pp，z=0.30 n.s.），所以改用后处理。

规则（只在**内容已经足够长**时删掉陈述性起手）：
  · 起手是「嗯／唔／哦／啊／诶／唉／咦／哎」＋ `。，、…` 这类**陈述性**标点；
  · 去掉后剩余实质内容 ≥ `MIN_REST`（默认 4 字）——否则保留。
    → 「嗯。开心」这种**短确认＋短判断**是她有实证的形态（语料里存在），必须保留；
    → 「嗯。／雨还在下。」里的「嗯。」是冗余，删掉后「雨还在下。」同样是语料里的形态。
  · **「嗯？」（疑问起手）不动**——那是疑惑/反问的语气，删掉会丢语义。

为什么不是「清零」而是「消减」：语料本身有 8% 语气词起手。
用同一条规则跑原作语料只改到 4% 的行（分布 55% → 57%，几乎 no-op），
说明它删的是冗余、不是她的风格。

可关闭：`RANA_VOICE_CHECK_ACK_STRIP=0`。
"""
from __future__ import annotations

import os
import re

# 陈述性起手（不含 ？ —— 疑问语气单独处理：不动）
_ACK = re.compile(r"^(?:嗯|唔|哦|啊|诶|唉|咦|哎|あ|ん|え)[。．.，,、！!…]+\s*")

# 去掉起手后至少要剩这么多实质字（不含换行/空白），否则保留
MIN_REST = 4


def _enabled() -> bool:
    raw = os.environ.get("RANA_VOICE_CHECK_ACK_STRIP")
    if raw is None:
        return True
    return str(raw).strip() not in ("0", "false", "False", "off", "no", "")


def strip_redundant_ack(text: str) -> tuple[str, bool]:
    """返回 (处理后的文本, 是否改动)。无改动时原样返回。"""
    s = str(text or "")
    if not s or not _enabled():
        return s, False
    m = _ACK.match(s)
    if not m:
        return s, False
    rest = s[m.end():].lstrip("\n \t")
    if len(re.sub(r"\s", "", rest)) < MIN_REST:
        return s, False
    return rest, True
