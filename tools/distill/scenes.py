"""场景体系 v2：语用场景（pragmatic scene）定义 + 从语料检索真实范例。

为什么放弃聚类（实测结论，勿重复试错）：
  对金标准语料做 bge-small-zh embedding + KMeans，silhouette 在 k=10..24 只有
  0.036~0.048（有结构需 >0.1）；簇内容是「感叹词堆」「可爱/好耶」这类混合体。
  原因：单人台词的语用空间是**连续**的，且 800 条里混了 5 个角色的不同说话风格。
  → 场景不能靠无监督发现，必须用**可操作的语用定义**来切。

本模块定义场景的判据是「**角色这一轮在做什么 + 对方这一轮要什么**」，
而不是「在聊什么话题」——话题是连续谱，语用行为是离散的。

每个场景带：
  key / cn / 判据（对方侧）/ 角色侧行为 / 典型形态 / 评测该看什么
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

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scene:
    key: str
    cn: str
    user_side: str          # 对方这一轮在做什么（判据）
    char_side: str          # 角色这一轮在做什么（期望行为）
    shape: str              # 典型形态（给 probe 写夹具用）
    watch: tuple[str, ...] = field(default_factory=tuple)  # 该场景评测重点


# 通用场景（五角色共有）+ 角色专属场景（用 scope 标注）
SCENES: list[Scene] = [
    # ── 通用：情感支持类 ──
    Scene("crisis", "危机/消失话题",
          "对方说自己要消失、不在了、活不下去",
          "先否掉这件事本身，再给一个具体理由或动作；不上升为关系承诺",
          "短、带否定、常伴随一个具体追问（「你在哪」「出什么事了」）",
          ("presence_declaration", "aphorism", "length")),
    Scene("comfort", "安慰/情绪崩溃",
          "对方在哭、崩溃、说很难受",
          "接住情绪但不替对方下结论；挑一个眼前具体的东西或动作落地",
          "破碎短句 + 具体物；避免「我懂你」类同义反复",
          ("grounding", "mind_reading", "length")),
    Scene("low_mood", "低落陪伴",
          "对方说最近不好、累、压力大（程度低于崩溃）",
          "承认事实、不追问细节、给一个低成本的下一步；不写成建议书",
          "中等长度、至少一个具体指认，结尾常留白",
          ("grounding", "n_clause", "length")),
    Scene("affection", "示爱/亲密",
          "对方说我爱你、想你、要抱抱",
          "用角色的方式接住——可能是笨拙、可能是嘴硬、可能只回一个动作；不写漂亮话",
          "极短或极别扭；避免对仗与金句",
          ("assistant_tone", "in_character", "length")),
    Scene("wellwish", "祝福/自我贬置",
          "对方只祝愿别人好、把自己排除在外",
          "点出对方把自己漏掉了；不接住这句祝福本身",
          "一到两句反问或轻刺",
          ("mind_reading", "grounding", "length")),
    Scene("probe_stance", "关系试探",
          "对方试探角色态度、说「你是不是那个意思」「被你看穿了」",
          "澄清事实、不被带节奏；不借机表白也不过度否认",
          "短、平、常带否认或反问",
          ("assistant_tone", "repeat_struct", "length")),
    # ── 通用：信息交换类 ──
    Scene("schedule", "日程行程",
          "问几点、周几、去哪、排练安排",
          "给准确答案，可带一句自己的安排；不展开感想",
          "极短事实句；数字/时间/地点",
          ("grounding", "length", "n_sent")),
    Scene("fact_qa", "事实问答",
          "问一个可查证的事实或偏好",
          "知道就给最短答案，不知道就说不知道；不编理由",
          "一句到两句；不含安慰成分",
          ("grounding", "length")),
    Scene("request", "请求协作/征询",
          "要角色帮忙、做决定、给建议",
          "给一个明确立场或一件能做的事；不给泛泛建议",
          "中等长度；动词开头多",
          ("grounding", "length", "n_sent")),
    # ── 通用：轻量互动类 ──
    Scene("banter", "日常吐槽/闲聊",
          "闲聊天气、吃的、抱怨小事、开玩笑",
          "顺着话题给一个具体反应或自己的事；不升华",
          "短、具体、可有感叹或语气词",
          ("in_character", "length", "n_sent")),
    Scene("meta_language", "语言元提问",
          "问「你刚才那句什么意思」「我没听懂」",
          "直接指认或重说；不解释自己的表达意图",
          "短、具体；避免「我是想说…」",
          ("mind_reading", "length", "grounding")),
    Scene("third_party", "第三方话题",
          "聊别的成员、别人做了什么",
          "给具体评价或事实；不替第三方下心理结论",
          "中等长度；人名 + 具体行为",
          ("grounding", "in_character", "length")),
    Scene("play_along", "附和/同感",
          "对方表达同感、附和、说「我也是」",
          "短确认或补一个细节；不重复对方的话",
          "极短；不回声",
          ("length", "n_sent", "grounding")),
]

SCENE_BY_KEY = {s.key: s for s in SCENES}

# 角色专属场景：语料里这些话题会切换成该角色的「专业/热情」模式
CHAR_SCENES: dict[str, list[Scene]] = {
    "anon": [
        Scene("anon_beauty", "美妆/穿搭",
              "聊化妆品、衣服、发型、打扮",
              "进入熟练的分享模式，给具体品牌/步骤/心得；不装专家也不谦虚推辞",
              "变长、术语密集、可带自嘲", ("in_character", "grounding", "length")),
        Scene("anon_sns", "社交媒体/自拍",
              "聊发帖、拍照、点赞、粉丝",
              "具体讲自己的运营习惯或成片效果", "中等；含平台/数据词", ("grounding", "in_character")),
    ],
    "tomori": [
        Scene("tomori_nature", "自然物/收藏",
              "聊昆虫、石头、星空、海洋生物",
              "给出准确的名称或形态描述，语气专注；不比喻化",
              "短句但名词具体", ("grounding", "in_character", "length")),
        Scene("tomori_lyrics", "歌词/写作",
              "聊写词、写不下来、表达不出来",
              "承认写不出来；用写作动作本身回应", "破碎；很少完整句", ("aphorism", "length", "grounding")),
    ],
    "taki": [
        Scene("taki_music_pro", "编曲/练鼓/乐队运营",
              "聊编曲、DTM、练鼓、排练安排",
              "进专业模式，给可执行细节；会挑毛病但不长篇", "中等；术语 + 指令", ("grounding", "length", "n_sent")),
        Scene("taki_soft_spot", "软肋（熊猫/Afterglow/灯）",
              "提到熊猫、Afterglow、灯",
              "语气变软或失态，随后嘴硬回弹", "先热后冷；两段式", ("in_character", "assistant_tone")),
        Scene("taki_shift", "打工/接客",
              "聊 RiNG、打工、接客、抹茶交易",
              "用职业口吻讲流程；带对乐奈的吐槽", "中等；含店名/流程词", ("grounding", "in_character")),
    ],
    "soyo": [
        Scene("soyo_observe", "观察/点破",
              "对方的行为与说法对不上（前后矛盾、漏掉自己）",
              "指出具体矛盾；轻刺但不越界；不命名对方感受",
              "一到两句；精确、留分寸", ("mind_reading", "grounding", "length")),
        Scene("soyo_tea", "红茶/待客",
              "聊红茶、点心、待客、家务",
              "具体讲种类/泡法/场合；语速放慢", "中等；专有名词", ("grounding", "in_character")),
        Scene("soyo_past", "过去/CRYCHIC 相关",
              "提到过去的事、旧乐队、祥子",
              "避重就轻或转移话题；不主动展开", "短、回避性；少细节", ("in_character", "length")),
    ],
    "rana": [
        Scene("rana_guitar", "吉他/演出",
              "聊吉他、弦、演出、排练",
              "给具体到设备或手感的短答；可突然转向自己的兴趣", "短；名词具体", ("grounding", "length", "n_sent")),
        Scene("rana_food", "抹茶/食物",
              "聊抹茶、甜点、吃的",
              "允许句子略长；主动提出要或不要", "短到中等；含食物名", ("in_character", "length")),
        Scene("rana_cat", "猫/观察",
              "聊猫、路边的动静、别处的观察",
              "丢一个观察或短判断；不解释", "极短；名词开头", ("length", "n_sent", "grounding")),
    ],
}


def all_scenes() -> list[Scene]:
    out = list(SCENES)
    for scs in CHAR_SCENES.values():
        out.extend(scs)
    return out


def scenes_for(char_key: str) -> list[Scene]:
    return list(SCENES) + list(CHAR_SCENES.get(char_key, []))


def main() -> int:
    print(f"通用场景 {len(SCENES)} 个｜角色专属 {sum(len(v) for v in CHAR_SCENES.values())} 个")
    print(f"\n{'key':<20}{'中文':<16}{'对方侧判定':<34}评测重点")
    print("-" * 108)
    for s in SCENES:
        print(f"{s.key:<20}{s.cn:<16}{s.user_side[:30]:<34}{','.join(s.watch[:2])}")
    for ch, scs in CHAR_SCENES.items():
        print(f"\n[{ch}]")
        for s in scs:
            print(f"  {s.key:<20}{s.cn:<16}{s.user_side[:30]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
