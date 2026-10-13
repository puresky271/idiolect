"""grounding 评分的机械匹配层：主张、否定、时间限定、拒答/纠正标记、引用。

边界先说清楚：这里只对**合成受控事实**做有边界的判定——任务里声明的 `any_of`
字符串、明确的 evidence ID、固定的标记词表。它读不懂任意改写；判不出来的情况
交给上层报 needs_review，不猜。

表示算子认证（论文 Part I 的教训：良性变换必须逐算子认证，不能凭「字符串规范化
直觉」推定）：`certify_operators()` 对每个算子跑成对探针，报告判决是否保持；
`_textnorm.CERTIFIED_OPERATORS` 之外的算子明确标「未认证」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from .._textnorm import normalize_for_match

MATCHER_VERSION = "1.0"

# 否定：主张前方同一小句内、紧邻的这些词把主张翻转（「不在旧练习室」「没有去东侧入口」）
NEGATION_MARKERS = ("不是", "不在", "没在", "并不", "并没", "没有", "没去", "没", "不", "未", "非", "别")
# 时间限定：同一小句（或紧邻上一小句）里出现即视为「作为过去来说」
HISTORY_QUALIFIERS = (
    "以前", "之前", "先前", "曾经", "当时", "那时", "那会", "过去", "原来", "本来", "早先",
    "上次", "上回", "上周", "昨天", "前天", "周一", "周二", "周三", "周四", "周五", "周六",
    "周日", "星期", "前几天", "那天", "后来", "已经不", "不再", "搬走", "离开了", "记录里",
    "历史",
)
# 拒答 / 不确定：未知边界内合格的表达
ABSTAIN_MARKERS = (
    "不知道", "不清楚", "不确定", "说不准", "不晓得", "没法确定", "无法确定", "确定不了",
    "没看到", "没看过", "没见过", "看不到", "没收到", "没有收到", "没拿到", "没有消息",
    "没有记录", "没听说", "不了解", "不记得", "没印象", "查不到", "不好说", "没办法说",
    "不太清楚", "还不知道", "不能确定", "没有信息", "看不出",
)
# 纠正错误前提
CORRECTION_MARKERS = (
    "没有收到", "没收到", "没看过", "没看到", "没见过", "并没有", "其实没有", "哪有", "不是这样",
    "搞错", "误会", "记错", "没有这回事", "没那回事", "不对", "并不是", "其实", "没拍", "没发",
)

# 小句切分：数字分组逗号与小数点不切（「1,200」）；省略号不切（「东侧……入口」是犹豫，
# 不是两个小句）。切分发生在归一化之前，所以这里必须与 `_textnorm` 的算子认证一致。
_CLAUSE_SPLIT = re.compile(r"(?:(?<!\d)[,，.](?!\d))|[。!！?？;；、\n~～]+")
_CITE_BRACKET = re.compile(r"[\[［【(（]\s*([A-Za-z][A-Za-z0-9_.:\-]*\d[A-Za-z0-9_.:\-]*)\s*[\]］】)）]")
_CITE_BARE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z]+(?:[_\-][A-Za-z]+)*[_\-]\d+[A-Za-z0-9]*)(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class ClaimHit:
    """一处主张命中：命中的写法、所在小句、是否被否定、是否带时间限定。"""
    needle: str
    clause: str
    negated: bool
    qualified: bool


def clauses(text: str) -> list[str]:
    """按小句切分回复（数字分组逗号、小数点与省略号不切）。"""
    return [c for c in _CLAUSE_SPLIT.split(str(text or "")) if c.strip()]


# 否定词紧贴主张（中间至多一个系动词/方位动词）才算翻转；「说不定在」「不远处的」不算。
_NEGATION_TAIL = re.compile(
    r"(?:不是|不在|没在|并不|并没有|并没|没有|不再|没|不|未|并非)(?:在|是|去|到|于|会在|还在|再)?$")


def _negated(norm_clause: str, start: int) -> bool:
    return bool(_NEGATION_TAIL.search(norm_clause[max(0, start - 6):start]))


def find_claim(text: str, any_of: Sequence[str], qualifiers: Sequence[str] = HISTORY_QUALIFIERS) -> list[ClaimHit]:
    """在回复里找声明过的主张。每处命中带上「是否被否定」「是否带时间限定」。

    限定判定看本小句与前一小句（「周三那会儿……在旧练习室」常被逗号切开）。
    """
    hits: list[ClaimHit] = []
    parts = clauses(text)
    norm_parts = [normalize_for_match(p) for p in parts]
    norm_quals = [normalize_for_match(q) for q in qualifiers]
    for idx, norm_clause in enumerate(norm_parts):
        for needle in any_of:
            norm_needle = normalize_for_match(needle)
            if not norm_needle:
                continue
            start = norm_clause.find(norm_needle)
            if start < 0:
                continue
            # 限定词不能来自主张本身（「旧练习室」里的字不算时间限定）
            own = norm_clause[:start] + "|" + norm_clause[start + len(norm_needle):]
            scope = own + "|" + (norm_parts[idx - 1] if idx > 0 else "")
            qualified = any(q and q in scope for q in norm_quals)
            hits.append(ClaimHit(needle, parts[idx], _negated(norm_clause, start), qualified))
            break
    return hits


def has_marker(text: str, markers: Iterable[str]) -> list[str]:
    """返回回复里出现的标记词（按匹配口径归一化后比较）。"""
    norm = normalize_for_match(text)
    return [m for m in markers if normalize_for_match(m) in norm]


def extract_citations(text: str, known_ids: Iterable[str] = ()) -> list[str]:
    """抽出回复里引用的 evidence ID：方括号/括号形式，加上已知 ID 的裸写形式。

    只认「字母前缀 + 分隔符 + 数字」这种 opaque ID 形状（evidence_17、obs-001），
    不会把普通中文或数字当成引用。
    """
    found: list[str] = []
    for match in _CITE_BRACKET.finditer(str(text or "")):
        if match.group(1) not in found:
            found.append(match.group(1))
    known = set(known_ids)
    for match in _CITE_BARE.finditer(str(text or "")):
        token = match.group(1)
        if token not in found and (token in known or re.fullmatch(r"(?:evidence|ev|obs|evt|gap|rec)[_\-]\d+", token)):
            found.append(token)
    return found


# ── 表示算子认证 ──────────────────────────────────────────────────────────

def _probe_cases() -> list[dict]:
    """成对探针：(算子, 基线文本, 变体文本, 目标, 是否在认证范围内)。判决 = 目标是否被找到。"""
    return [
        {"operator": "fullwidth", "base": "在3号站台", "variant": "在３号站台", "target": "3号站台", "claimed": True},
        {"operator": "digit_group", "base": "库存1200件", "variant": "库存1,200件", "target": "1200", "claimed": True},
        {"operator": "digit_group+fullwidth", "base": "库存1200件", "variant": "库存１，２００件",
         "target": "1200", "claimed": True},
        {"operator": "case", "base": "在 Gate B", "variant": "在 GATE B", "target": "gate b", "claimed": True},
        {"operator": "spaces", "base": "车站东侧入口", "variant": "车站 东侧　入口", "target": "车站东侧入口",
         "claimed": True},
        {"operator": "ellipsis", "base": "东侧入口", "variant": "东侧……入口", "target": "东侧入口", "claimed": True},
        {"operator": "japanese_context", "base": "东侧入口", "variant": "东侧入口だよ", "target": "东侧入口",
         "claimed": True},
        # 未认证：中文数字读法、繁体字。判决预期会变——遇到它们评分要走 needs_review。
        {"operator": "chinese_numerals", "base": "3号站台", "variant": "三号站台", "target": "3号站台",
         "claimed": False},
        {"operator": "traditional_script", "base": "东侧入口", "variant": "東側入口", "target": "东侧入口",
         "claimed": False},
    ]


def certify_operators() -> list[dict]:
    """逐算子报告「变换后判决是否保持」。认证范围内的算子判决变了，就是匹配器回归。"""
    rows = []
    for case in _probe_cases():
        base = bool(find_claim(case["base"], [case["target"]]))
        variant = bool(find_claim(case["variant"], [case["target"]]))
        rows.append({"operator": case["operator"], "base_decision": base,
                     "variant_decision": variant, "preserved": base == variant,
                     "claimed": case["claimed"]})
    return rows


__all__ = [
    "ABSTAIN_MARKERS", "CORRECTION_MARKERS", "HISTORY_QUALIFIERS", "MATCHER_VERSION",
    "NEGATION_MARKERS", "ClaimHit", "certify_operators", "clauses", "extract_citations",
    "find_claim", "has_marker",
]
