"""灯专属：清洗「XX呀，XX啊」式物件枚举和情绪词/好词尾缀。

用户收口（2026-08-17）：
  - 灯不会用「XX呀，XX啊」这种活泼重复来枚举物件；
  - 单独一句「这样啊」不算目标，后续仍走 exclamation_softener 软化；
  - 目标是物件枚举，例如「石头呀、树叶啊」应压成「石头、树叶」；
  - 情绪词 + 呀/啊也要清洗，例如「开心呀」「开心啊」应压成「开心」；
  - 好呀/好啊同样不会说，应压成「好」；
  - 同词重复如「好呀，好啊」「开心呀，开心啊」先折叠成单个词，避免变成「好，好」。

枚举策略：
  · 只处理连续、由逗号/顿号/空白分隔的多个中文短词；
  · 每个短词以「呀」或「啊」结尾，且同一枚举里至少同时出现「呀」和「啊」；
  · 至少有两个不同词，避免把同词重复误当枚举；
  · 清洗时只去掉尾缀，保留原分隔符，交给后续标点/省略号规则继续处理。

情绪词/好词策略：
  · 清洗已知情绪词和「好」直接带「呀/啊」的情况；
  · 保留「这样啊」「真的啊」等非目标确认词，继续走现有软化规则。
"""
from __future__ import annotations

import re

_ITEM_RE = re.compile(r"([一-鿿]+)([呀啊])")
_SEPARATOR_RE = re.compile(r"^[，,、\s]+$")
_SAME_WORD_PAIR_RE = re.compile(r"([一-鿿]+)呀[，,、\s]+(?:\1)啊")

_PARTICLE_WORDS = (
    "好",
    "开心", "高兴", "快乐", "难过", "伤心", "悲伤", "痛苦", "难受", "委屈",
    "生气", "害怕", "紧张", "激动", "期待", "失望", "失落", "烦躁", "孤单",
    "孤独", "安心", "感动", "羡慕", "嫉妒", "惊喜", "温暖", "轻松", "放心",
    "无奈", "平静", "兴奋", "沮丧", "不安", "害羞", "心疼", "后悔", "担心",
    "着急", "焦虑", "疲惫", "疲劳", "想哭", "心动", "烦", "累", "困",
)
_WORD_PARTICLE_RE = re.compile(
    r"([一-鿿]*)"
    r"(" + "|".join(re.escape(word) for word in sorted(_PARTICLE_WORDS, key=len, reverse=True)) + r")"
    r"([呀啊])"
)


def _runs(text: str) -> list[list[dict]]:
    """把连续枚举项分成 run；每一项记录词、尾缀和原文位置。"""
    runs: list[list[dict]] = []
    current: list[dict] = []
    previous_end = -1

    for match in _ITEM_RE.finditer(text):
        item = {
            "word": match.group(1),
            "particle": match.group(2),
            "start": match.start(),
            "end": match.end(),
        }
        if current and _SEPARATOR_RE.match(text[previous_end:match.start()]):
            current.append(item)
        else:
            if current:
                runs.append(current)
            current = [item]
        previous_end = match.end()

    if current:
        runs.append(current)
    return runs


def strip_ya_a_enumeration(text: str) -> tuple[str, int]:
    """把「石头呀、树叶啊」式物件枚举清洗为「石头、树叶」。

    Returns:
        (new_text, cleaned_count)
    """
    if not text:
        return text, 0

    edits: list[tuple[int, int, str]] = []
    for run in _runs(text):
        if len(run) < 2:
            continue
        particles = {item["particle"] for item in run}
        words = {item["word"] for item in run}
        if "呀" not in particles or "啊" not in particles:
            continue
        if len(words) < 2:
            continue
        for item in run:
            edits.append((item["start"], item["end"], item["word"]))

    if not edits:
        return text, 0

    new_text = text
    for start, end, replacement in sorted(edits, reverse=True):
        new_text = new_text[:start] + replacement + new_text[end:]
    return new_text, len(edits)


def strip_same_word_pair(text: str) -> tuple[str, int]:
    """把「好呀，好啊」「开心呀，开心啊」折叠成单个词。

    Returns:
        (new_text, collapsed_count)
    """
    if not text:
        return text, 0

    def _sub(match: re.Match) -> str:
        return match.group(1)

    new_text, collapsed_count = _SAME_WORD_PAIR_RE.subn(_sub, text)
    return new_text, collapsed_count


def strip_word_particle(text: str) -> tuple[str, int]:
    """把情绪词或「好」的尾缀「呀/啊」去掉，例如「开心呀」→「开心」。

    Returns:
        (new_text, cleaned_count)
    """
    if not text:
        return text, 0

    def _sub(match: re.Match) -> str:
        return match.group(1) + match.group(2)

    new_text, cleaned_count = _WORD_PARTICLE_RE.subn(_sub, text)
    return new_text, cleaned_count


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    fail = 0
    enum_cases = [
        # 物件枚举：去掉呀/啊，保留分隔符
        ("石头呀、树叶啊", "石头、树叶", 2),
        ("石头呀，树叶啊", "石头，树叶", 2),
        ("石头呀、树叶啊、花呀", "石头、树叶、花", 3),
        ("石头啊、树叶呀", "石头、树叶", 2),
        # 单独“这样啊”不动
        ("这样啊", "这样啊", 0),
        ("这样啊。", "这样啊。", 0),
        # 同词重复交给 strip_same_word_pair，这里不动
        ("好呀，好啊", "好呀，好啊", 0),
        ("开心呀，开心啊", "开心呀，开心啊", 0),
        # 缺呀/啊混搭或单枚举项不动
        ("石头呀、树叶呀", "石头呀、树叶呀", 0),
        ("石头呀", "石头呀", 0),
        # 无枚举不动
        ("真的吗？", "真的吗？", 0),
        ("", "", 0),
    ]
    for inp, exp_text, exp_n in enum_cases:
        out, n = strip_ya_a_enumeration(inp)
        ok = (out == exp_text) and (n == exp_n)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] enum {inp!r:30} -> {out!r:30} n={n} (exp {exp_n})")

    same_cases = [
        ("好呀，好啊", "好", 1),
        ("好呀、好啊", "好", 1),
        ("开心呀，开心啊", "开心", 1),
        ("这样啊", "这样啊", 0),
        ("石头呀、树叶啊", "石头呀、树叶啊", 0),
        ("", "", 0),
    ]
    for inp, exp_text, exp_n in same_cases:
        out, n = strip_same_word_pair(inp)
        ok = (out == exp_text) and (n == exp_n)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] same {inp!r:30} -> {out!r:30} n={n} (exp {exp_n})")

    word_cases = [
        ("好呀", "好", 1),
        ("好啊", "好", 1),
        ("很好啊", "很好", 1),
        ("开心呀", "开心", 1),
        ("开心啊", "开心", 1),
        ("好开心呀", "好开心", 1),
        ("今天很难过啊", "今天很难过", 1),
        ("不伤心呀", "不伤心", 1),
        # 非目标确认词不动
        ("这样啊", "这样啊", 0),
        ("真的啊", "真的啊", 0),
        ("石头啊", "石头啊", 0),
        ("", "", 0),
    ]
    for inp, exp_text, exp_n in word_cases:
        out, n = strip_word_particle(inp)
        ok = (out == exp_text) and (n == exp_n)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] word {inp!r:30} -> {out!r:30} n={n} (exp {exp_n})")

    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
