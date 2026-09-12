"""按输入文本定种的随机源：后处理里的随机步骤要「同输入同输出」。

为什么不用全局 random：库代码抓全局随机状态会污染调用方；而完全随机又让
同一条输入每次产出不同——测试无法断言、排障无法复现。crc32 定种对进程与
平台稳定（不像内置 `hash()` 每进程加盐）。

用法：`seeded_rng(reply_text)` 传给 voice_check 里接受 rng 的清洗阶段。
"""
from __future__ import annotations

import random
import zlib


def seeded_rng(text: str) -> random.Random:
    """返回以文本 crc32 为种的独立 Random 实例。"""
    return random.Random(zlib.crc32(str(text or "").encode("utf-8")))
