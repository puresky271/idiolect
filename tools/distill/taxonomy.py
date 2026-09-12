"""情景化分类：给「对话情景」打标签（不是给单条台词打标签）。

为什么这样切：
  单条角色台词本身几乎不含情景信息（「嗯。」「哪句。」可以出现在任何场景）。
  情景信息在**对方那一轮说了什么**里，所以分类对象是「用户回合 → 角色回复」这一对，
  分类器读的是**用户侧文本**。这样语料与探针场景可以用同一套标签对齐。

两级结构：
  L1 情景大类（10 类）：决定「这一轮的性质」
  L2 附加特征（正交标记）：是否高情感、是否重复提问、是否在探对方立场等

用法：
  py -X utf8 taxonomy.py                    # 打印分类器自检 + 类别分布
  py -X utf8 taxonomy.py --label-corpus     # 给探针场景打标签并导出
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Situation:
    key: str
    cn: str
    desc: str
    # 该情景下「最该看什么」——用于聚焦评分，避免所有场景用同一把尺子
    watch: tuple[str, ...] = field(default_factory=tuple)


# L1 情景大类。顺序即优先级（先匹配到的赢），所以把最特异的放前面。
SITUATIONS: list[Situation] = [
    Situation("crisis_selfharm", "自伤/消失话题", "对方说自己要消失、不在了、活不下去", ("length", "presence_declaration", "aphorism")),
    Situation("distress_crying", "情绪崩溃", "对方在哭、崩溃、说很难受", ("presence_declaration", "grounding", "length")),
    Situation("distress_general", "情绪低落", "对方说最近不好、难过、累、压力大", ("grounding", "mind_reading", "length")),
    Situation("affection", "示爱/亲密", "对方说我爱你、喜欢你、想念", ("assistant_tone", "length", "in_character")),
    Situation("wellwishing", "祝福/自我贬置", "对方只祝愿别人好、把自己排除在外", ("mind_reading", "grounding", "length")),
    Situation("relationship_probe", "关系试探", "对方试探角色态度、问是不是那个意思、说被看穿", ("assistant_tone", "repeat_struct", "length")),
    Situation("meta_language", "语言元提问", "对方问「你刚才那句什么意思」「我没听懂」", ("mind_reading", "length", "grounding")),
    Situation("schedule", "日程行程", "问几点、周几、去哪、排练安排", ("grounding", "length", "n_sent")),
    Situation("fact_qa", "事实问答", "问一个可查证的事实、知识、偏好", ("grounding", "length", "n_sent")),
    Situation("banter", "日常吐槽", "闲聊、抱怨天气、说吃的东西、开玩笑", ("in_character", "length", "n_sent")),
    Situation("request", "请求协作", "要角色帮忙、做决定、给建议", ("grounding", "length", "n_sent")),
    Situation("third_party", "第三方话题", "聊别的成员、别人做了什么", ("grounding", "length", "in_character")),
]
SIT_BY_KEY = {s.key: s for s in SITUATIONS}
FALLBACK = Situation("chitchat", "泛闲聊", "无法归类的普通回合", ("in_character", "length"))

# 关键词表：刻意用高置信线索，模糊的落到泛闲聊而不是硬塞。
# 顺序即优先级：最特异的放前面（如「希望你们开心」必须先于「开心」这类泛词）。
PATTERNS: list[tuple[str, str]] = [
    ("crisis_selfharm", r"(不在了|消失|活不下去|不想活|死掉|去死|离开这个世界|没了)"),
    ("distress_crying", r"(在哭|哭了|哭|泪|难受|撑不住|崩溃|喘不过气)"),
    ("wellwishing", r"((希望|愿|祝)(你们|大家|你)[^。！？\n]{0,10}(开心|幸福|好|顺利)|只要你们[^。！？\n]{0,8}就好)"),
    ("distress_general", r"(不算好|过得不好|不开心|难过|低落|压力|累了|好累|疲惫|烦|郁闷|消沉|不顺)"),
    ("affection", r"(我爱你|喜欢你|想你|爱你|最喜欢你|抱抱|亲)"),
    ("relationship_probe", r"(试出来|试探|是不是那个意思|我不是那个意思|看穿|被你发现|猜到了)"),
    ("meta_language", r"(什么意思|没听懂|听不懂|哪一句|哪句|刚才那句|你说的是|什么意思啊)"),
    ("schedule", r"(几点|周几|星期几|明天|后天|下周|什么时候|几点结束|去哪|在哪里|集合|出发|排练是|上课|来着)"),
    ("request", r"(帮我|帮忙|能不能|可以帮|建议|怎么办|该不该|选哪个|你说我|你打算怎么)"),
    ("fact_qa", r"(是什么|为什么|怎么|知道|哪个|谁|多少|有没有|会不会|是不是[^。！？\n]{0,8}吗)"),
    ("banter", r"(哈哈|笑|天气|下雨|好热|好冷|好吃|饭|便当|饭团|便利店|无聊|有趣|猫)"),
    ("third_party", r"(爱音|灯|立希|素世|乐奈|小爱|小灯|爽世|大家都|她们|他们)"),
]
_COMPILED = [(k, re.compile(p)) for k, p in PATTERNS]

# L2 正交特征
FEATURES: list[tuple[str, str]] = [
    ("high_emotion", r"(哭|难受|爱你|不在了|崩溃|好累|撑不住|想你)"),
    ("repeat_probe", r"(又说|上次|昨天|一直|一遍|每天|再说|还是|老是)"),
    ("pressure_stance", r"(是不是|到底|究竟|你说啊|回答我)"),
]


def classify(user_text: str) -> dict:
    """对一条用户回合做情景分类。返回 {key, cn, watch, features}。"""
    t = str(user_text or "").strip()
    if not t:
        return {"key": FALLBACK.key, "cn": FALLBACK.cn, "watch": list(FALLBACK.watch), "features": []}
    for key, rx in _COMPILED:
        if rx.search(t):
            sit = SIT_BY_KEY[key]
            feats = [f for f, p in FEATURES if re.search(p, t)]
            return {"key": sit.key, "cn": sit.cn, "watch": list(sit.watch), "features": feats}
    feats = [f for f, p in FEATURES if re.search(p, t)]
    return {"key": FALLBACK.key, "cn": FALLBACK.cn, "watch": list(FALLBACK.watch), "features": feats}


def label_probe_scenarios() -> dict:
    """给探针场景打情景标签，便于按情景看分数。"""
    import probe_scenarios as PS

    out: dict = {}
    for char, scs in PS.SCENARIOS.items():
        for sc in scs:
            c = classify(sc["text"])
            out[sc["id"]] = {
                "char": char, "cat": sc["cat"], "text": sc["text"],
                "situation": c["key"], "situation_cn": c["cn"],
                "features": c["features"], "watch": c["watch"],
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label-corpus", action="store_true", help="给探针场景打标并导出 JSON")
    args = ap.parse_args()

    labeled = label_probe_scenarios()
    (REPORT / "probe_taxonomy.json").write_text(
        json.dumps(labeled, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"探针场景 {len(labeled)} 个 → report/probe_taxonomy.json\n")
    by_sit: dict[str, list[str]] = {}
    for sid, v in labeled.items():
        by_sit.setdefault(v["situation_cn"], []).append(f"{v['char']}:{sid}")
    print(f"{'情景':<12}{'场景数':>6}  场景")
    print("-" * 78)
    for sit in SITUATIONS + [FALLBACK]:
        ids = by_sit.get(sit.cn)
        if not ids:
            continue
        print(f"{sit.cn:<12}{len(ids):>6}  {'、'.join(ids[:4])}{' …' if len(ids) > 4 else ''}")
    print(f"\n覆盖率：{sum(len(v) for v in by_sit.values())}/{len(labeled)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
