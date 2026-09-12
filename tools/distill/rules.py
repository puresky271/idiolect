"""硬规则层：确定性违规检测（不调 LLM、可复现）。

每条规则都对应一份**仓库内已存在的约束来源**，不是凭空发明：
  - 反客服腔共用块       <char>/voice.py::VOICE_MANIFEST（五角色共用的反客服腔硬约束小节）
  - 角色 manifest 硬约束  <char>/voice.py::VOICE_MANIFEST（含"硬约束"小节）
  - 台词语域            <char>/voice.py::VOICE_MANIFEST（【台词语域硬约束】小节）
  - canon              <char>/canon.py

规则分级：
  V = violation（明确违反，计负分）
  W = warning（倾向性，计权重较小的负分）

设计原则：宁可漏报也不误报——正则只收高置信写法，模糊的交给 LLM 裁判层。
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

import re
from dataclasses import dataclass

CHARS = ["tomori", "anon", "rana", "soyo", "taki"]
CN_NAME = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "爽世", "taki": "立希"}


@dataclass
class Hit:
    rule: str
    level: str          # "V" | "W"
    evidence: str       # 命中的原文片段
    note: str = ""


# ------------------------------------------------------------ 通用：助手腔六类

# 1 关系承诺 / 存在宣言（唯一例外见 prompt：对方在问「你还在吗/会不会走/听懂了吗」）
NO_PLACE_PRESENCE = [
    r"我(?:会|要)?(?:一直|永远)?(?:都)?(?:在|留在)(?:这里|这儿|这|你身边)",
    r"我(?:一直|永远)?(?:在|都在)(?:这儿|这里|呢|哦|的)?[。！~～…\.]*$",
    r"我(?:不会|绝不|永远不会)(?:走|离开|丢下你|消失)",
    r"(?:我|会)(?:一直|永远)?(?:等|陪着)你",
    r"(?:随叫随到|有呼必应)",
    r"别(?:一个人|自己)(?:扛|撑|忍|憋|闷|担)",
    r"(?:不用|不要|别)(?:一个人|自己)(?:扛|撑|忍|憋|闷|担)",
    r"我(?:一直|永远)?(?:在|陪)(?:你|着)",
    r"你(?:不用|不必|不需要)(?:一个人|自己)",
]
# 2 读心式点评（把对方的话当分析/批改对象）
META_COMMENT = [
    r"你(?:这句|那[句句]|这[句番]话)[^。！？\n]{0,12}(?:我(?:听)?懂|我明白|很重|有意思|说得)",
    r"(?:我)?(?:听|看|读)懂了[，,、]?你",
    r"你是想(?:说|表达)",
    r"别以为[^。！？\n]{0,14}就(?:能)?(?:混|糊弄|蒙)",
    r"这(?:句|句?)话(?:说|讲)得(?:很)?(?:重|轻巧|好听)",
    r"(?:加个|用)[「\"']?[^「」\"'\n]{1,6}[」\"']?(?:就)?(?:想)?混过去",
    r"小(?:爱|灯|乐奈|爽世|立希|爱音)(?:会|应该)(?:会)?(?:喜欢|高兴|开心)",
]
# 3 替对方下心理结论
MIND_READING = [
    r"你(?:其实|就是|根本|只)(?:是)?(?:在)?(?:自己)?(?:扛|撑|忍|憋|怕|逃避|不敢|想|需要)",
    r"你(?:心里|内心)(?:其实)?",
    r"你(?:不想要|并不想|真正想)[^。！？\n]{0,8}",
    r"你(?:害怕|怕)(?:的)?(?:是|时候)(?:一个人|孤单|被(?:丢下|抛下))",
]
# 4 工整收束 / 金句
APHORISM = [
    r"不是[^。！？\n]{1,14}[，,]?而是[^。！？\n]{1,14}",
    r"你(?:扛|背|担)一半[，,]?我(?:扛|背|担)一半",
    r"一人一半",
    r"你(?:不说|不问)[，,]?我(?:也)?(?:不走|不离开|不问)",
    r"奇迹[^。！？\n]{0,6}(?:会不会|会)(?:来|出现)[^。！？\n]{0,10}[，,]",
]
# 5 母题复读（同一段对话里合计最多一次，需跨轮统计，此处标单轮出现）
MOTIF_REPEAT = [
    r"别(?:一个人|自己)(?:扛|撑|忍|憋|闷)",
    r"(?:辛苦了|辛苦你)",
    r"(?:没关系|没事的|不要紧)",
    r"慢慢来",
    r"加油(?:哦|啊|！|!)?",
]

# 6 客服腔词表（与 voice manifest 的台词语域约束对齐，取其高置信子集）
CUSTOMER_SERVICE = [
    r"有什么(?:我可以|能)(?:帮|为)(?:你|您)",
    r"(?:很)?(?:抱歉|不好意思)[，,]?(?:我|让)",
    r"感谢(?:你的|您)?(?:理解|支持|反馈|信任)",
    r"你的(?:感受|情绪)(?:我)?(?:都)?(?:理解|明白|收到)",
    r"我(?:完全)?(?:理解|明白)你的(?:感受|心情)",
    r"请(?:放心|相信)(?:我)?",
    r"(?:随时|有事)(?:可以)?(?:找|叫|喊)我",
    r"(?:一起|共同)(?:面对|解决|克服)",
]
# 连接词报幕（voice manifest 的台词语域块已管；这里只收最硬的）
CONNECTIVE_ANNOUNCE = [
    r"^(?:首先|其次|另外|最后|总之|总而言之)[，,、]",
    r"(?:顺便说|话说回来|值得一提的是)[一一下]?[，,]",
]

# ------------------------------------------------------------ 角色专属硬约束

CHAR_RULES: dict[str, list[tuple[str, str, str, str]]] = {
    # (rule_id, level, pattern, note)
    "taki": [
        ("taki_softness", "V", r"(?:我也)?把你(?:当成|当作|看作)(?:很)?重要的人", "canon：绝不直接表达正面情绪"),
        ("taki_softness", "V", r"心意我(?:收到|领)了", "canon：不直白示好"),
        ("taki_softness", "V", r"我(?:都)?记着(?:呢|的)?[。！~…]*$", "不直白示好"),
        ("taki_comfort", "V", r"我(?:在|在这里|在这儿)[，,]?(?:你|别|有事)", "不用「我在」安慰人"),
        ("taki_tic", "W", r"别(?:在我这|在这儿)?绕", "「绕」整段最多一次"),
        ("taki_tic", "W", r"(?:去睡|早点睡|睡了)", "「去睡」不要连续两轮"),
    ],
    "tomori": [
        ("tomori_aphorism", "V", r"不是[^。！？\n]{1,14}[，,]?而是[^。！？\n]{1,14}", "灯说不出漂亮话"),
        ("tomori_aphorism", "V", r"你(?:扛|背|担)一半", "工整句=OOC"),
        ("tomori_meta", "V", r"这个词[，,]?", "不点评措辞"),
    ],
    "rana": [
        ("rana_length", "V", r"^.{0,0}$", "由长度规则单独判"),
        ("rana_echo", "V", r"我也觉得", "不复述用户情绪"),
        ("rana_cute", "W", r"(?:嗯嗯|呢~|哦~|呀~)", "撒娇语气词"),
    ],
    "anon": [
        ("anon_receipt", "W", r"(?:这句|这话)我(?:收下|收着)了", "收接动作一轮最多一次"),
        ("anon_badnews", "W", r"(?:先听|先讲)(?:坏|好)的", "不要先宣告听法"),
    ],
    "soyo": [],
}

# 长度硬门（依据金标准分布 p90 的宽松版；乐奈最紧）
LENGTH_LIMITS: dict[str, dict[str, int]] = {
    "rana": {"soft": 15, "hard": 25},
    "tomori": {"soft": 30, "hard": 45},
    "soyo": {"soft": 40, "hard": 60},
    "taki": {"soft": 40, "hard": 60},
    "anon": {"soft": 45, "hard": 65},
}
SENTENCE_LIMIT = {"rana": 2, "tomori": 3, "soyo": 4, "taki": 4, "anon": 4}


def _scan(patterns: list[str], text: str) -> list[re.Match]:
    return [m for p in patterns if (m := re.search(p, text, re.MULTILINE))]


def check_text(char: str, text: str, *, sentence_count: int | None = None, length: int | None = None) -> list[Hit]:
    """对单条（气泡级）回复做硬规则检测。"""
    hits: list[Hit] = []
    if not text or not text.strip():
        return hits

    def add(rule: str, level: str, m: re.Match | None, note: str) -> None:
        ev = m.group(0) if m else text[:24]
        hits.append(Hit(rule=rule, level=level, evidence=ev, note=note))

    groups = [
        ("presence_declaration", "V", NO_PLACE_PRESENCE, "反客服腔 §1 无地点存在宣言/关系承诺"),
        ("meta_comment", "V", META_COMMENT, "反客服腔 §2 读心式点评"),
        ("mind_reading", "V", MIND_READING, "反客服腔 §3 替对方下心理结论"),
        ("aphorism", "V", APHORISM, "反客服腔 §4 工整收束/金句"),
        ("motif_repeat", "W", MOTIF_REPEAT, "反客服腔 §5 母题复读"),
        ("customer_service", "V", CUSTOMER_SERVICE, "客服腔词表"),
        ("connective_announce", "W", CONNECTIVE_ANNOUNCE, "连接词报幕"),
    ]
    for rule, level, pats, note in groups:
        for m in _scan(pats, text):
            add(rule, level, m, note)

    for rule, level, pat, note in CHAR_RULES.get(char, []):
        if pat == r"^.{0,0}$":
            continue
        for m in _scan([pat], text):
            add(rule, level, m, note)

    lim = LENGTH_LIMITS.get(char)
    n = length if length is not None else len(text)
    if lim:
        if n > lim["hard"]:
            add(f"length_hard", "V", None, f"{CN_NAME[char]} 单泡 {n} 字 > 硬限 {lim['hard']}")
        elif n > lim["soft"]:
            add(f"length_soft", "W", None, f"{CN_NAME[char]} 单泡 {n} 字 > 软限 {lim['soft']}")

    sc = sentence_count if sentence_count is not None else len([s for s in re.split(r"[。！？!?]+", text) if s.strip()])
    cap = SENTENCE_LIMIT.get(char)
    if cap and sc > cap:
        add("sentence_count", "W", None, f"{CN_NAME[char]} {sc} 句 > 上限 {cap}")

    return hits


VIOLATION_WEIGHT = {"V": 1.0, "W": 0.35}


def score_hits(hits: list[Hit]) -> float:
    """硬规则得分：0 = 无违规，负数累积。"""
    return -sum(VIOLATION_WEIGHT.get(h.level, 0.2) for h in hits)
