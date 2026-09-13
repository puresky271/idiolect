"""风格特征提取器（语料基线与探针评分共用同一份实现）。

设计原则：**同一份特征实现**同时服务
  1) 对真实台词库（金标准）算基线分布
  2) 对 LLM 生成回复算同构特征向量
否则两边指标口径会漂移，benchmark 失去意义。

特征分四组：
  A 形状    : 字数、句子数、小句数、沉默回合、最长句
  B 标点    : 各标点密度/出现率
  C 词法    : 一人称、二人称、称呼、感动词/フィラー、句末助词、笑い
  D 词汇签名: 词级 log-odds（对全体语料），抓各角色特有措辞

语言适配：jp 走 SudachiPy 词法；cn 走 jieba + 标点特征（无词法级 pos）。
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

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------- 常量

PUNCT_KEYS = ["…", "。", "！", "？", "、", "，", "—", "～", "（", "♪"]
ELLIPSIS_CHARS = "…⋯"
SENT_END = "。！？!?！？"
QUOTE_CHARS = "「」『』（）()\"'“”"

RE_SENT_SPLIT = re.compile(rf"[{re.escape(SENT_END)}]+")
RE_CLAUSE_SPLIT = re.compile(r"[、，,]")
RE_ALNUM = re.compile(r"[0-9A-Za-z]")
RE_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff々〆ヵヶ]")
RE_JP_ONLY = re.compile(r"[\u3040-\u30ff]")
# 只有标点/空白/省略号的「沉默回合」（含 ······ 写法）
RE_SILENT = re.compile(
    rf"^[\s{re.escape(ELLIPSIS_CHARS)}·・{re.escape(SENT_END)}、，,—～♪]*$"
)

# 一人称 / 二人称（jp + cn）
FIRST_PERSON = [
    "私", "わたし", "あたし", "僕", "ぼく", "俺", "おれ", "うち", "わたくし",
    "我", "咱",
]
SECOND_PERSON = ["あなた", "あんた", "君", "きみ", "お前", "おまえ", "てめえ", "てめぇ", "你", "您"]
# 称呼后缀（对同伴）——乐奈几乎不用
ADDRESS_SUFFIX = ["ちゃん", "さん", "くん", "先輩", "せんぱい", "様", "さま", "氏", "老师", "前辈"]

# 感动词 / フィラー（Sudachi 的「感動詞」另算，这里补漏 + 中文语气词）
FILLER_WORDS = [
    "あ", "あっ", "ああ", "え", "えっ", "ええ", "うん", "ううん", "はあ", "はぁ",
    "へえ", "へぇ", "おお", "おー", "わあ", "わー", "ふふ", "ふふっ", "うふふ",
    "はい", "いいえ", "ん", "んっ", "ねえ", "ねぇ", "さあ", "さぁ", "こら", "ちょっと",
    "诶", "啊", "嗯", "哦", "咦", "唉", "哎呀", "哎", "唔", "诶诶", "嘛", "诶呀",
]
LAUGH_MARKS = ["w", "ｗ", "笑", "ふふ", "ふふっ", "はは", "あはは", "うふふ", "えへへ", "哈哈", "嘿嘿", "嘻嘻"]

# jp 句末助词（终助词 / 間投助詞）
JP_SENTENCE_FINAL = ["よ", "ね", "な", "ぞ", "ぜ", "わ", "か", "の", "さ", "かな", "かよ", "じゃん", "っしょ", "だろ", "ろ"]
# jp 有标点感的记号
JP_LONG_VOWEL = ["ー", "〜", "～", "－"]


# ---------------------------------------------------------------- 分词器

_sudachi = None
_jieba = None


def _jp_tokens(text: str) -> list[tuple[str, str, str, str]]:
    """-> [(surface, pos1, pos2, dict_form)]"""
    global _sudachi
    if _sudachi is None:
        from sudachipy import SplitMode, dictionary

        _sudachi = (dictionary.Dictionary().create(), SplitMode.C)
    tokenizer, mode = _sudachi
    return [(m.surface(), m.part_of_speech()[0], m.part_of_speech()[1], m.dictionary_form()) for m in tokenizer.tokenize(text, mode)]


def _cn_tokens(text: str) -> list[tuple[str, str, str]]:
    global _jieba
    if _jieba is None:
        import jieba

        jieba.setLogLevel(60)
        _jieba = jieba
    return [(w, "", "") for w in _jieba.lcut(text) if w.strip()]


def content_tokens(text: str, lang: str) -> list[str]:
    """实词列表（供 log-odds 词汇签名用）。"""
    out: list[str] = []
    if lang == "jp":
        for surface, pos1, pos2, base in _jp_tokens(text):
            if pos1 in ("名詞", "動詞", "形容詞", "形状詞", "感動詞") and pos2 not in ("数詞",):
                out.append(base if pos1 != "感動詞" else surface)
    else:
        for w, _, _ in _cn_tokens(text):
            if not RE_CJK.search(w):
                continue
            if len(w) == 1 and w in "的了是在有和就不都很也":
                continue
            out.append(w)
    return out


def _count_ellipsis_marks(text: str) -> int:
    """省略号**组数**。三种写法算同一族：
      「……」= 2×U+2026（日文/中文惯用）
      「······」= 6×U+00B7（本项目灯 canon 的大停顿写法，实际上线主力）
      「⋯⋯」= 2×U+22EF
    统一按「一组 2 个点」折算，避免同一个语气被算成 3 倍或 0 倍。
    """
    total = 0
    for ch in ("…", "⋯"):
        total += text.count(ch) / 2.0
    for run in re.findall(r"[·・]{2,}", text):
        total += len(run) / 2.0
    return total


# ---------------------------------------------------------------- 特征

def _count_filler_tokens(text: str, lang: str) -> tuple[int, list[str]]:
    """感动词/フィラー计数。**必须词级判定**——子串计数会让「あ」命中「あなた/ある」。

    jp: Sudachi 的「感動詞」+ 明确的フィラー词表（词级精确匹配）
    cn: 词表精确匹配（jieba 分词后）
    """
    hits: list[str] = []
    if lang == "jp":
        for surface, pos1, _pos2, _base in _jp_tokens(text):
            if pos1 == "感動詞":
                hits.append(surface)
            elif surface in FILLER_WORDS:
                hits.append(surface)
    else:
        for w, _, _ in _cn_tokens(text):
            if w in FILLER_WORDS or w in FILLER_CN:
                hits.append(w)
    return len(hits), hits


FILLER_CN = {
    "诶", "啊", "嗯", "哦", "咦", "唉", "哎呀", "哎", "唔", "诶诶", "嘛", "诶呀",
    "哈哈", "嘿嘿", "嘻嘻", "呀", "哇", "嘿", "呃", "嗷", "嘞", "咯",
}


def token_freq(texts: Iterable[str], lang: str, pos1_filter: Sequence[str] | None = None) -> Counter:
    c: Counter = Counter()
    for t in texts:
        if not t or not t.strip():
            continue
        if lang == "jp":
            for surface, pos1, _p2, _b in _jp_tokens(t):
                if pos1_filter and pos1 not in pos1_filter:
                    continue
                c[surface] += 1
        else:
            for w, _, _ in _cn_tokens(t):
                c[w] += 1
    return c


@dataclass
class TurnFeatures:
    """单条回复的形状/标点特征。"""

    text: str
    length: int = 0            # 含标点字符数
    length_core: int = 0       # 去标点后字符数
    n_sent: int = 0            # 句子数（按终止符切）
    n_clause: int = 0          # 小句数（按逗号切）
    max_sent_len: int = 0
    silent: bool = False       # 纯省略号/标点回合
    punct: dict[str, int] = field(default_factory=dict)
    punct_any: dict[str, bool] = field(default_factory=dict)
    first_person: int = 0
    second_person: int = 0
    address_suffix: int = 0
    filler: int = 0
    laugh: int = 0
    sent_final_jp: int = 0
    long_vowel_jp: int = 0
    filler_hits: list[str] = field(default_factory=list)


def turn_features(text: str, lang: str = "jp") -> TurnFeatures:
    f = TurnFeatures(text=text)
    if not text:
        return f
    f.length = len(text)
    core = re.sub(rf"[\s{re.escape(SENT_END)}{re.escape(ELLIPSIS_CHARS)}、，,—～♪「」『』（）()]", "", text)
    f.length_core = len(core)
    f.silent = bool(RE_SILENT.match(text)) and len(text.strip()) > 0

    sents = [s for s in RE_SENT_SPLIT.split(text) if s.strip()]
    f.n_sent = len(sents)
    clauses = [c for c in RE_CLAUSE_SPLIT.split(text) if c.strip()]
    f.n_clause = len(clauses)
    f.max_sent_len = max((len(s) for s in sents), default=0)

    for key in PUNCT_KEYS:
        if key == "…":
            continue
        c = text.count(key)
        f.punct[key] = c
        f.punct_any[key] = c > 0
    # 省略号统一族（…… / ······ / ⋯⋯）
    f.punct["…"] = _count_ellipsis_marks(text)
    f.punct_any["…"] = f.punct["…"] > 0

    for w in FIRST_PERSON:
        f.first_person += text.count(w)
    for w in SECOND_PERSON:
        f.second_person += text.count(w)
    for w in ADDRESS_SUFFIX:
        f.address_suffix += text.count(w)
    f.filler, filler_hits = _count_filler_tokens(text, lang)
    f.filler_hits = filler_hits
    for w in LAUGH_MARKS:
        if w == "w":
            # 裸 w 只认独立的 w 串（www / ｗｗ），避免命中英文单词
            if re.search(r"(?<![A-Za-z])[wｗ]{2,}(?![A-Za-z])", text):
                f.laugh += 1
        elif w in text:
            f.laugh += 1
    if lang == "jp":
        for w in JP_LONG_VOWEL:
            f.long_vowel_jp += text.count(w)
        toks = _jp_tokens(text)
        for surface, pos1, pos2, _base in toks:
            if pos1 == "助詞" and pos2 == "終助詞":
                f.sent_final_jp += 1
        if f.sent_final_jp == 0 and toks:
            # 口语里常缺终助词，用「表面以终助词性词尾收束」兜一层
            last = text.rstrip("".join(ELLIPSIS_CHARS) + SENT_END + "、，, 　")
            for w in JP_SENTENCE_FINAL:
                if last.endswith(w):
                    f.sent_final_jp += 1
                    break
    return f


# ---------------------------------------------------------------- 分布基线

@dataclass
class Dist:
    """一个数值特征的分布摘要。"""

    n: int
    mean: float
    sd: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p99: float

    @staticmethod
    def of(values: Sequence[float]) -> "Dist":
        vals = sorted(float(v) for v in values)
        if not vals:
            return Dist(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0.0

        def q(p: float) -> float:
            if n == 1:
                return vals[0]
            idx = p * (n - 1)
            lo = int(math.floor(idx))
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            return vals[lo] * (1 - frac) + vals[hi] * frac

        return Dist(n, mean, math.sqrt(var), q(0.10), q(0.25), q(0.50), q(0.75), q(0.90), q(0.99))

    def z(self, value: float) -> float:
        return (value - self.mean) / self.sd if self.sd > 1e-9 else 0.0

    def to_dict(self) -> dict:
        return {
            "n": self.n, "mean": round(self.mean, 3), "sd": round(self.sd, 3),
            "p10": round(self.p10, 3), "p25": round(self.p25, 3), "p50": round(self.p50, 3),
            "p75": round(self.p75, 3), "p90": round(self.p90, 3), "p99": round(self.p99, 3),
        }


def profile_from_texts(texts: Iterable[str], lang: str) -> dict:
    """把一批台词（单条=一个回合）压成角色风格画像。"""
    feats = [turn_features(t, lang) for t in texts if t and t.strip()]
    feats = [f for f in feats if not f.silent]  # 沉默回合单独统计，不污染长度分布
    n = len(feats)
    if n == 0:
        return {"n": 0}

    def dens(key: str) -> list[float]:
        return [f.punct[key] / max(f.length, 1) * 100 for f in feats]

    prof: dict = {
        "n": n,
        "length": Dist.of([f.length for f in feats]).to_dict(),
        "length_core": Dist.of([f.length_core for f in feats]).to_dict(),
        "n_sent": Dist.of([f.n_sent for f in feats]).to_dict(),
        "n_clause": Dist.of([f.n_clause for f in feats]).to_dict(),
        "max_sent_len": Dist.of([f.max_sent_len for f in feats]).to_dict(),
        "punct_density": {k: Dist.of(dens(k)).to_dict() for k in ("…", "！", "？", "、", "，", "—", "～", "。")},
        "punct_rate": {k: round(sum(1 for f in feats if f.punct_any[k]) / n, 4) for k in ("…", "！", "？", "、", "，", "—", "～", "。", "♪", "（")},
        "first_person_rate": round(sum(1 for f in feats if f.first_person) / n, 4),
        "first_person_per_turn": Dist.of([f.first_person for f in feats]).to_dict(),
        "second_person_rate": round(sum(1 for f in feats if f.second_person) / n, 4),
        "address_suffix_rate": round(sum(1 for f in feats if f.address_suffix) / n, 4),
        "filler_per_turn": Dist.of([f.filler for f in feats]).to_dict(),
        "filler_rate": round(sum(1 for f in feats if f.filler) / n, 4),
        "laugh_rate": round(sum(1 for f in feats if f.laugh) / n, 4),
        "sent_final_jp_per_turn": Dist.of([f.sent_final_jp for f in feats]).to_dict(),
        "long_vowel_rate": round(sum(1 for f in feats if f.long_vowel_jp) / n, 4),
    }
    filler_counter: Counter = Counter()
    for f in feats:
        filler_counter.update(f.filler_hits)
    prof["interjection_top"] = filler_counter.most_common(12)
    prof["interjection_per_turn"] = Dist.of([f.filler for f in feats]).to_dict()
    return prof


# ---------------------------------------------------------------- 综合分

# 具体处境锚点：可指认的物件/地点/动作/专名。用于衡量「有没有真在说这件事」，
# 防止分数被「少说话」刷上去——短但空洞等于助手腔的另一种形态。
#
# 2026-09-11 扩充为**领域感知**：旧表只有通用生活词，导致「美妆/穿搭」这类场景
# 即使答得很具体（提到腮红、色号、牌子）也算 0 锚点，把场景分冤判成 51.4。
ANCHOR_WORDS = [
    # 校园 / 日程 / 交通
    "教室", "学校", "课", "上课", "午休", "放学", "排练", "RiNG", "练习", "演出", "live",
    "车站", "电车", "地铁", "路线", "几点的", "钟头", "分钟", "早上", "下午", "傍晚", "夜里",
    "校服", "书包", "桌子", "桌肚", "走廊", "中庭", "花坛", "体育馆", "音乐室",
    # 乐器 / 音乐
    "吉他", "贝斯", "鼓", "弦", "拨片", "谱", "歌", "曲", "节拍", "调音", "和弦", "音箱",
    "耳机", "唱片", "歌词", "副歌", "前奏", "独奏", "合奏",
    # 食物 / 饮品
    "抹茶", "芭菲", "布丁", "红茶", "咖啡", "伯爵", "大吉岭", "茶包", "点心", "蛋糕",
    "便当", "饭团", "面包", "拉面", "荞麦面", "冰淇淋", "玉子烧", "味噌汤", "牛奶",
    # 美妆 / 穿搭 / 社交
    "腮红", "口红", "粉底", "色号", "眼影", "指甲", "头发", "发夹", "耳环", "项链",
    "裙子", "外套", "鞋子", "香水", "柔顺剂", "相册", "照片", "自拍", "镜头", "相机",
    "点赞", "粉丝", "帖子", "头像", "手机", "充电",
    # 自然 / 天气 / 生物
    "雨", "伞", "窗", "天", "云", "风", "雪", "太阳", "叶子", "树枝", "花", "蝉",
    "石头", "星星", "海", "水族馆", "企鹅", "猫", "狗", "虫",
    # 物件 / 记忆
    "笔记本", "笔", "贴纸", "创可贴", "金平糖", "钥匙扣", "便条", "手账", "日历",
    "熊猫", "玩偶", "挂件", "礼物", "信", "卡片",
]
_ANCHOR_RX = None


def _tail_is_predicate(clause: str, lang: str) -> bool:
    """子句末尾是否为「谓语性」成分（= 完整句），否则视为体言止め。

    用**分词词性**判定，而不是标点启发式——中文常省略系动词（「雨声大」），
    只看标点或只看词尾字符都会误判。词性判据：
      谓语性：动词 / 形容词 / 形状词 / 助动词 / 系动词（是/就是/不是）/ 句末语气词
      体言  ：名词 / 代名词 / 数量词 / 接尾辞
    """
    body = clause.strip().rstrip("。！？!?…·、，, 　")
    if not body:
        return False
    if lang == "jp":
        toks = _jp_tokens(body)
        if not toks:
            return False
        # 从尾往前找第一个实词性 token
        for _surface, pos1, pos2, _base in reversed(toks):
            if pos1 in ("動詞", "形容詞", "形状詞", "助動詞"):
                return True
            if pos1 == "助詞" and pos2 in ("終助詞", "間投助詞"):
                return True
            if pos1 in ("名詞", "代名詞", "接尾辞"):
                return False
            if pos1 == "感動詞":
                return False
            if pos1 in ("補助記号", "空白"):
                continue
            return False
        return False
    # 中文走词级：末词若是名词/代词/数量词 → 体言止め；是动词/形容词/副词 → 谓语
    # （不要用字符级词尾启发式：会把「好吃」的「好」、「弦断了」的「了」误判成谓语）
    try:
        import jieba.posseg as pseg

        pairs = [p for p in pseg.cut(body) if p.word.strip()]
        if not pairs:
            return False
        flag = pairs[-1].flag
        if flag.startswith(("n", "r", "m", "q", "s", "t", "f")) and flag != "nr":
            # nr = 人名；人名收尾同样属于体言性
            return False
        if flag.startswith("nr"):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def rana_register_score(text: str, lang: str = "cn") -> dict:
    """乐奈特有语域的可测指标（2026-09-11 从语料实测得出）。

    为什么单独做：乐奈的「极简」**不是在完整句上删字**，而是换了一套语法——
      实测金标准：名词/体言直出起手 **55%**、≤6 字 **57%**、自称率仅 **16%**，
      而灯/爱音/素世/立希的名词直出只有 42/39/38/39%、自称率 27~37%
      （逐条复现：`tools/score/_noun_initial.py <批次名>` 会把原作基线与当前臂并排打出）。

    只输出**两条经实测有区分度**的指标：
      nominal_start 名词性起手率（金标准 72%，各臂 44~69%）
      self_ref      是否出现自称「我」（金标准 16% vs 其余 27~37%）

    ⚠️ **已放弃「体言止め率」**：尝试过标点启发式与末词词性两种实现，都不成立——
      中文分词把「好吃」整词判成形容词、把「去」判成动词，于是**无主语短断言
      （正是乐奈的主体）被系统性判为「完整句」**；要正确判定需要句法分析器。
      留一条会误导人的指标比没有更糟，所以移除，改用起手与自称这两条可靠的。

    返回：{nominal_start, le6, self_ref, sents}
    """
    import re as _re

    if not text or not text.strip():
        return {"nominal_start": 0.0, "le6": 0, "self_ref": 0, "sents": 0}
    body = text.strip()
    parts = [p.strip() for p in _re.split(r"[。！？!?…]+", body) if p.strip()]
    if not parts:
        return {"nominal_start": 0.0, "le6": 0, "self_ref": 0, "sents": 0}

    _non_nominal_start = _re.compile(
        r"^(?:[？?！!…·]|[嗯啊唔哦诶唉咦哎]|我|你|他|她|它|这|那|谁|哪|不|没|别)"
    )
    nom = sum(1 for p in parts if not _non_nominal_start.match(p))
    return {
        "nominal_start": round(nom / len(parts), 3),
        "le6": 1 if len(body) <= 6 else 0,
        "self_ref": 1 if "我" in body else 0,
        "sents": len(parts),
    }


def anchor_hits_chars(texts: Iterable[str]) -> tuple[int, int]:
    """锚点命中数与总字数（原始计数）。

    计数必须单独可取（2026-09-13 复审 N7）：hits 是小整数（实测每角色 2~19 次
    /21 条），只暴露密度比值会让下游误以为它是连续精确量——泊松检验需要原始计数。
    """
    import re as _re

    global _ANCHOR_RX
    if _ANCHOR_RX is None:
        _ANCHOR_RX = _re.compile("|".join(ANCHOR_WORDS))
    hits = 0
    chars = 0
    for t in texts:
        if not t or not t.strip():
            continue
        chars += len(t)
        hits += len(_ANCHOR_RX.findall(t))
    return hits, chars


def anchor_density(texts: Iterable[str]) -> float:
    """每 100 字的锚点词数。用它对标 fidelity 的「长度」维度做交叉验证。"""
    hits, chars = anchor_hits_chars(texts)
    return (hits / chars * 100) if chars else 0.0


def composite_score(gold: dict, actual: dict, texts: Iterable[str],
                    w_style: float = 0.65, w_anchor: float = 0.35,
                    anchor_ref: float | None = None) -> dict:
    """风格保真 + 内容实质 的综合分（0-100）。

    为什么需要：单看 fidelity 会奖励「短」。实测见过 fidelity 更低（58.5）
    但具体锚点率高得多（57% vs 36%）的回复——它更长、更具体，却被长度维度罚分。
    要防的病灶是**模板化/助手腔**，不是啰嗦，所以目标函数必须同时看
    「像不像这个角色」和「有没有在说具体的事」，否则优化会退化成「变冷淡」。

    anchor_ref 的取法（2026-09-11 修正；2026-09-13 定死单一来源；同日 N4 复审改为必填）：
      曾写死 4.0，但**各角色的天然锚点密度差 3 倍**（乐奈的场景基线加权值 ≈3.4、
      素世 ≈1.5），写死会把「该角色本来就不提具体物」误判成质量差。
      所以参照线是**该角色自身常态**，不跨角色比。
      anchor_ref 为 None 时**直接报错**，不做任何兜底：历史上的兜底
      （gold 字段 / 1.0）量程错误，曾让纯助手腔的 composite 排到第一
      （外部评审照库 API 默认调用第一次就踩中，且全程静默无告警）。
      生产路径用 `probe_runner.derive_anchor_ref` 的场景基线派生值（唯一口径）。

    anchor_score 有封顶（min(ad/ref, 1)）：达到该角色自身常态即满分，
    超过常态的波动不可见——这是刻意不奖励堆锚点，代价与兜底指标见
    docs/04-evaluation.md 第 2.1 节（饱和段）。
    """
    fid = style_fidelity(gold, actual)
    if anchor_ref is None:
        raise ValueError(
            "anchor_ref 必填：历史兜底（gold 字段 / 1.0）量程错误，曾让纯助手腔的 "
            "composite 静默排到第一（2026-09-13 复审 N4）。"
            "生产路径传 probe_runner.derive_anchor_ref 的场景基线派生值；"
            "测试里也要显式给参照线。")
    ad = anchor_density(texts)
    anchor_score = min(ad / anchor_ref, 1.0) * 100.0 if anchor_ref else 0.0
    total = w_style * fid["fidelity"] + w_anchor * anchor_score
    return {
        "composite": round(total, 1),
        "style": fid["fidelity"],
        "anchor_density": round(ad, 2),
        "anchor_ref": round(anchor_ref, 2),
        "anchor_score": round(anchor_score, 1),
        "rmse": fid["rmse"],
        "drift": fid["drift"],
    }


def silent_turns(texts: Iterable[str]) -> list[str]:
    """只含标点/省略号的「沉默回合」。"""
    return [t for t in texts if t and t.strip() and turn_features(t).silent]


def style_targets(prof: dict, lang: str) -> dict:
    """把金标准画像压成**给模型看的数值目标**。

    动机：现有 manifest 用「1-10 字为主」「少用感叹号」这类模糊表述，模型会当倾向。
    实测金标准后可以给出硬数字（中位/p90/出现率），让约束可检验、可复现。
    """
    if not prof.get("n"):
        return {}
    L = prof["length"]
    out = {
        "median_chars": L["p50"],
        "mean_chars": round(L["mean"], 1),
        "p90_chars": L["p90"],
        "sent_per_turn": round(prof["n_sent"]["mean"], 2),
        "clause_per_turn": round(prof["n_clause"]["mean"], 2),
        "ellipsis_rate": prof["punct_rate"]["…"],
        "exclaim_rate": prof["punct_rate"]["！"],
        "question_rate": prof["punct_rate"]["？"],
        "period_rate": prof["punct_rate"]["。"],
        "comma_rate": prof["punct_rate"]["，"],
        "dash_rate": prof["punct_rate"]["—"],
        "first_person_rate": prof["first_person_rate"],
        "filler_rate": prof["filler_rate"],
        "laugh_rate": prof["laugh_rate"],
    }
    if lang == "jp":
        out["sent_final_per_turn"] = round(prof["sent_final_jp_per_turn"]["mean"], 2)
        out["long_vowel_rate"] = prof["long_vowel_rate"]
    out["top_interjections"] = [w for w, _c in prof.get("interjection_top", [])[:6]]
    return out


def format_targets_block(char_cn: str, targets: dict, lang: str = "cn") -> str:
    """把数值目标渲染成可直接进 prompt 的紧凑块。"""
    if not targets:
        return ""
    unit = "字" if lang == "cn" else "字"
    parts = [
        f"**{char_cn} 实测台词基线**（来自官方台词库，用作你写话的尺子）：",
        f"- 长度：中位 {targets['median_chars']:.0f} {unit}，"
        f"p90 {targets['p90_chars']:.0f} {unit}——**超过 p90 就属于异常长**。",
        f"- 结构：平均 {targets['sent_per_turn']:.2f} 句 / {targets['clause_per_turn']:.2f} 个小句。"
        f"{'**一句话就够**' if targets['sent_per_turn'] < 1.3 else ''}",
        f"- 语气：省略号 {targets['ellipsis_rate'] * 100:.0f}% 的话里有、感叹号 {targets['exclaim_rate'] * 100:.0f}%、"
        f"问号 {targets['question_rate'] * 100:.0f}%、句号 {targets['period_rate'] * 100:.0f}%。",
        f"- 自称：只有 {targets['first_person_rate'] * 100:.0f}% 的话里出现「我」——"
        f"**大多数话不以「我」开头**。",
    ]
    if targets.get("top_interjections"):
        parts.append(f"- 常用语气词：{'、'.join(targets['top_interjections'][:5])}。")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- 分布漂移

# 参与漂移评分的特征名（与 profile_from_texts 的键对应）
DRIFT_FEATURES_SCALAR = [
    "length", "n_sent", "n_clause", "max_sent_len",
    "first_person_per_turn", "filler_per_turn", "sent_final_jp_per_turn",
]
DRIFT_FEATURES_RATE = [
    "punct_rate", "first_person_rate", "address_suffix_rate", "filler_rate", "laugh_rate", "long_vowel_rate",
]


def drift_scores(gold: dict, actual: dict) -> dict[str, dict]:
    """用金标准分布当参照，算 actual 每个维度的 z 偏离。

    z = (actual_mean - gold_mean) / gold_sd；|z| 越大越不像。
    sd≈0 的维度跳过（无方差 = 该角色从不这样做，任何出现都属于异常，
    由硬规则层负责，不在这里用除法放大）。
    返回 {维度: {gold, actual, z, ratio}}。
    """
    out: dict[str, dict] = {}
    if not gold.get("n") or not actual.get("n"):
        return out
    for key in DRIFT_FEATURES_SCALAR:
        g, a = gold.get(key), actual.get(key)
        if not g or not a or not g.get("sd"):
            continue
        z = (a["mean"] - g["mean"]) / g["sd"] if g["sd"] > 1e-9 else 0.0
        out[key] = {
            "gold": round(g["mean"], 3), "actual": round(a["mean"], 3),
            "z": round(z, 2), "ratio": round(a["mean"] / g["mean"], 2) if g["mean"] else None,
        }
    for key in DRIFT_FEATURES_RATE:
        g, a = gold.get(key), actual.get(key)
        if not isinstance(g, dict) or not isinstance(a, dict):
            continue
        for sub in g:
            gv, av = g.get(sub), a.get(sub)
            if gv is None or av is None:
                continue
            out[f"{key}.{sub}"] = {
                "gold": round(gv, 4), "actual": round(av, 4),
                "z": None, "ratio": round(av / gv, 2) if gv else None,
                "delta": round(av - gv, 4),
            }
    return out


def style_fidelity(gold: dict, actual: dict, weights: dict[str, float] | None = None) -> dict:
    """把漂移压成 0-100 的风格保真分（越高越像金标准）。

    权重默认：长度与句末结构最重（它们是被实测证明漂移最大的维度），
    标点/自称其次。分数只用于**相对比较**（before/after 探针），不是绝对值真理。
    """
    default_w = {
        "length": 2.0, "max_sent_len": 1.5, "n_sent": 1.5, "n_clause": 1.0,
        "first_person_per_turn": 1.5, "filler_per_turn": 0.5, "sent_final_jp_per_turn": 0.5,
        "punct_rate.…": 1.0, "punct_rate.！": 0.8, "punct_rate.。": 2.0, "punct_rate.，": 0.8,
        "first_person_rate": 1.2, "filler_rate": 1.0, "laugh_rate": 0.3,
        "address_suffix_rate": 0.5, "long_vowel_rate": 0.3,
    }
    w = {**default_w, **(weights or {})}
    drift = drift_scores(gold, actual)
    num = 0.0
    den = 0.0
    for key, d in drift.items():
        weight = w.get(key, 0.5)
        z = d.get("z")
        if z is None:
            # 率型：用 delta 归一（差 0.5 记满偏）
            z = (d.get("delta") or 0.0) / 0.5
        num += weight * min(abs(z), 4.0) ** 2
        den += weight
    rmse = math.sqrt(num / den) if den else 0.0
    return {
        "fidelity": round(max(0.0, 100.0 * (1 - rmse / 4.0)), 1),
        "rmse": round(rmse, 3),
        "drift": drift,
    }


def logodds_signature(
    target: Sequence[str],
    background: Sequence[str],
    lang: str,
    top: int = 60,
) -> list[tuple[str, float, int]]:
    """各角色特有词汇：informative Dirichlet (Monroe et al.) 近似 log-odds。

    返回 [(词, logodds, 在目标中的次数)]，降序。
    """
    tc = Counter()
    for t in target:
        tc.update(content_tokens(t, lang))
    bc = Counter()
    for t in background:
        bc.update(content_tokens(t, lang))
    n_t, n_b = sum(tc.values()), sum(bc.values())
    if n_t == 0 or n_b == 0:
        return []
    vocab = set(tc)
    prior = 0.5
    out = []
    for w in vocab:
        if tc[w] < 3:
            continue
        a = tc[w] + prior
        b = bc.get(w, 0) + prior
        p_t = a / (n_t + prior * len(vocab))
        p_b = b / (n_b + prior * len(vocab))
        out.append((w, math.log(p_t / p_b), tc[w]))
    # 并列时按词兜底排序（2026-09-13 修）：`vocab` 是 set，迭代顺序受字符串哈希随机化
    # 影响，只按 logodds 排会让「同为 2.48 的两个词谁进 top-N」随进程变化——
    # 同一份语料两次跑出的 vocab 不同，发布数据就说不清能不能重建。
    out.sort(key=lambda x: (-x[1], x[0]))
    return out[:top]
