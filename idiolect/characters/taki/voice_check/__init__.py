"""taki.voice_check — 立希回复后处理清洗。

设计意图（对照 tomori.voice_check / anon.voice_check）：
  prompt 层规则 LLM 不一定遵守、需要 deterministic 后处理把所有偏差
  清洗到立希 canonical form。

**立希清洗器的关键原则：只删不替换**
  · 不像爱音那样把「，」换成「~」、不像灯那样把「!」改成「······」
  · 命中违禁 → 直接 strip、不补任何字符
  · 多重感叹号 / 问号连用 → 减到 1 个（这算"清理冗余"、不算"语义替换"）
  · LLM 自然产出的剩余文本保持原貌

3 个 stage（按调用顺序、全部永远跑、无 mood gate）：
  Stage 1: soft_response  -  删句首软回应起手（嗯嗯/好的呀/诶嘿/呐呐 等）—— 先吃长 phrase
  Stage 2: particle_tail  -  删句末撒娇词（呢/哦/啦/嘛/呀）—— 残留尾词
  Stage 3: decoration     -  删装饰符号（♪~——）+ 颜文字 + 多重感叹问号

API:
  clean_reply(text) -> (text, info)
"""
from __future__ import annotations

from .particle_tail import strip_particle_tail
from .decoration import strip_decorations
from .soft_response import strip_soft_response

__all__ = (
    "clean_reply",
    "strip_particle_tail",
    "strip_decorations",
    "strip_soft_response",
)


def clean_reply(text: str) -> tuple[str, dict]:
    """立希回复清洗总入口。

    Args:
        text: LLM 产出的回复

    Returns:
        (cleaned_text, info_dict)
        info_dict = {
            "violations": {stage: count, ...},   # 各 stage 实际删除数
            "ok": bool,                          # True = 无违规、False = 至少清过一处
        }
    """
    info: dict = {"violations": {}, "ok": True}
    if not text:
        return text, info

    # Stage 1: 句首软回应（先吃长 phrase、避免 phrase 内尾词被 Stage 2 误算）
    text, n1 = strip_soft_response(text)
    if n1:
        info["violations"]["soft_response"] = n1
        info["ok"] = False

    # Stage 2: 句末撒娇词
    text, n2 = strip_particle_tail(text)
    if n2:
        info["violations"]["particle_tail"] = n2
        info["ok"] = False

    # Stage 3: 装饰符号 / 颜文字 / 多重感叹问号
    text, n3 = strip_decorations(text)
    if n3:
        info["violations"]["decoration"] = n3
        info["ok"] = False

    return text, info


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    fail = 0

    cases: list[tuple[str, str, dict]] = [
        # (input, expected_output, expected_violations)
        # Stage 1: particle_tail
        ("行呀。", "行。", {"particle_tail": 1}),
        ("不知道呢，", "不知道，", {"particle_tail": 1}),
        ("哈？真是的啦！", "哈？真是的！", {"particle_tail": 1}),
        ("好啦。哦。", "好。。", {"particle_tail": 2}),
        ("你做什么呢？", "你做什么？", {"particle_tail": 1}),
        # 词内合法位置（lookbehind 保护）
        ("干啥呢", "干啥呢", {}),
        ("什么呢", "什么呢", {}),
        ("怎么啦", "怎么啦", {}),
        # Stage 2: decoration
        ("好啊♪", "好啊", {"decoration": 1}),
        ("哈哈哈~~", "哈哈哈", {"decoration": 1}),
        ("行———", "行", {"decoration": 1}),  # 3+ 连用 = 拖音、删
        ("不至于—", "不至于—", {}),  # 单 — 是合法标点、不删
        ("压力大——还能这样", "压力大——还能这样", {}),  # 双 —— 是合法中文标点、不删
        ("好啊！！！", "好啊！", {"decoration": 1}),
        ("真的吗？？？", "真的吗？", {"decoration": 1}),
        ("好啊(´∀｀)", "好啊", {"decoration": 1}),
        ("行 (＞ω＜)", "行 ", {"decoration": 1}),
        # Stage 3: soft_response
        ("嗯嗯，知道了", "知道了", {"soft_response": 1}),
        ("好的呀，那这样做", "那这样做", {"soft_response": 1}),
        ("诶嘿，这个很可爱", "这个很可爱", {"soft_response": 1}),
        ("呐呐，看看这个", "看看这个", {"soft_response": 1}),
        ("对呀对呀，就是这样", "就是这样", {"soft_response": 1}),
        ("真棒哦！这次表现", "这次表现", {"soft_response": 1}),
        # 句中「嗯」不删
        ("这个嗯有点", "这个嗯有点", {}),
        # 多 stage 复合
        ("嗯嗯，好的啦~", "好的啦", {"soft_response": 1, "decoration": 1}),
        # 立希正例不动
        ("······行吧。", "······行吧。", {}),
        ("哈？又不是没做过。", "哈？又不是没做过。", {}),
        ("那家伙、又没吃饭吧。", "那家伙、又没吃饭吧。", {}),
        ("······挺好的。", "······挺好的。", {}),
        # 空 / 边界
        ("", "", {}),
        ("！", "！", {}),  # 单 ! 不动
    ]

    for inp, exp_out, exp_v in cases:
        out, info = clean_reply(inp)
        violations = info["violations"]
        out_ok = (out == exp_out)
        v_ok = (violations == exp_v)
        if not (out_ok and v_ok):
            fail += 1
            print(f"[FAIL] {inp!r:40}")
            print(f"  expected: {exp_out!r}  violations={exp_v}")
            print(f"  got:      {out!r}  violations={violations}")
        else:
            print(f"[PASS] {inp!r:40} -> {out!r:30} v={violations}")

    print()
    print(f"OVERALL: {'PASS' if fail == 0 else f'FAIL ({fail})'}")
