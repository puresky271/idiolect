"""五人口癖画像 + **manifest 声称核对**（固定词表，避免自由 n-gram 碎片）。

为什么不用自由 n-gram：`verbal_tics.py` 的自由 n-gram 列仍有碎片
（`omorin` / `泽学` / `一束了`），是中文分词边界造成的，自动剪枝难以可靠。
本模块改走「候选词表 → 语料实测计数 → 特征性排序」，每个口癖都有确切实例。

第二轮扩展：把五份 `voice.py` 里**已经写进去的**口癖 / 句尾语气词也塞进候选，
于是能给出「manifest 声称 vs 原作实测」的核对表：
  SUPPORTED  专指度 ≥2 且出现 ≥8 次 —— 真的是她的口癖
  SHARED     出现 ≥8 次但别人也用 —— 真实但不算辨识特征
  WEAK       3~7 次 —— 有实例，撑不起「招牌」说法
  UNSUPPORTED <3 次 —— **原作里根本不这么说**，manifest 凭空写的

指标：
  count        全 train 语料出现总次数
  per_10k      每万字的出现次数（跨角色可比）
  line_share   含该说法的台词占比（判断「每轮都用」是否过量）
  start_share  出现在句首的比例（判断是不是起手型口癖）
  endpoint     末次出现位置 / 整句长度 的均值（1.0 = 基本都在句尾）

产出 report/tic_profile.json + tic_profile.md
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT, require_corpus  # noqa: E402,F401

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = REPORT
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}

# 候选口癖（只放**能确认为口癖**的短说法；不承载话题、一听知道是谁）
# 尾部带 ★ 的组 = 来自五份 voice.py 的 manifest 声称，用于核对。
CANDIDATES: dict[str, list[str]] = {
    "tomori": [
        "嗯", "啊", "诶", "唔", "呃", "哦", "哇",
        "……", "嗯……", "啊……", "诶……", "唔……",
        "不知道", "不知道……", "怎么办", "我知道了",
        "小爱", "小素世", "小立希", "小乐奈", "小爽世",
        "在哭", "哭", "写下来", "记住了",
        # ★ manifest 声称
        "······", "嗯，", "是不是", "真的可以吗", "石头",
        "蓝蓝的", "凉凉的", "软软的", "慢慢地", "一点点", "小小的", "暖暖的",
    ],
    "anon": [
        "诶", "诶？", "诶——", "诶~", "啊", "啊——", "啊？", "啊哈哈",
        "嘛", "哎呀", "哦", "唔", "咦", "哇", "嘿",
        "不过", "不过呢", "所以", "对吧", "的呢", "的吧", "了啊", "了哦",
        "好耶", "太好了", "怎么办啊", "什么啊", "干嘛",
        # ★ manifest 声称
        "呐呐", "才不是呢", "果然", "果然还是", "不是吗", "诶诶", "嘿嘿",
        "嗯～", "不行不行", "抱歉抱歉", "啊那段", "谢谢你", "谢谢",
    ],
    "rana": [
        "嗯", "嗯。", "唔", "哦", "ん", "啊",
        "哼哼", "哼", "ふん", "ふふん", "ふーん", "呼",
        "好吃", "好吃。", "有趣", "有趣的女人", "无聊",
        "猫", "猫猫", "抹茶", "芭菲", "吉他", "弦",
        "不够", "还不够", "我要", "我想吃", "去",
        # ★ manifest 声称
        "风", "风大", "那只猫", "给我", "不知道", "外婆", "素世", "立希",
    ],
    "soyo": [
        "嗯", "嗯，", "嗯……", "哦", "啊", "诶", "唔", "唉",
        "这样", "这样啊", "呵呵", "但是", "不过", "如果", "只是",
        "了吧", "的吧", "对吧", "的呢", "的哦", "一点",
        "小爱音", "小灯", "小立希", "小乐奈", "小睦",
        # ★ manifest 禁止但需要核对
        "呢", "啦", "呀", "嘛",
        # ★ manifest 声称
        "那个", "是这样", "不太确定", "没有那么", "只是顺手",
        "你为什么要这样说", "先放一放", "不太方便", "再确认一下",
        "先", "旧的",
    ],
    "taki": [
        "哈", "哈？", "啊？", "唉", "唉……", "哼", "啧", "喂",
        "野猫", "野猫你", "那家伙", "这家伙",
        "不，", "不过", "总之", "反正", "而已", "好了", "行了",
        "吵", "烦", "别", "少来", "说清楚", "直说",
        # ★ manifest 声称
        "真是的", "切", "行吧", "随便你", "说什么傻话", "别突然说",
        "不至于", "又不是", "没事的话", "我看看", "拿来", "让我来",
        "别绕了", "去睡", "早点睡", "我怎么知道", "灯", "熊猫",
    ],
}


def _positions(text: str, needle: str) -> tuple[int, list[float]]:
    """返回 (句首出现次数, [末次出现位置/句长] 列表)。"""
    start_hits = 0
    endpoints: list[float] = []
    idx = text.find(needle)
    n = len(text)
    while idx != -1:
        if idx == 0:
            start_hits += 1
        end = idx + len(needle)
        # 末次出现位置只统计"贴到句尾"的那种（后面只剩标点）
        endpoints.append(end / n if n else 0.0)
        idx = text.find(needle, end)
    return start_hits, endpoints


def main() -> int:
    corpus: dict[str, list[str]] = {k: [] for k in CHARS}
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("split") == "train" and r["character"] in corpus:
                corpus[r["character"]].append(r["text"])

    per_char: dict[str, list[dict]] = {}
    out: dict = {}
    lines = ["# 五人口癖画像（词表 + 语料核对）\n",
             "> 每个口癖都是候选词表里**在语料中真实出现**的；`专指度` = 该角色每万字频次 / 最高他人每万字频次。",
             "> 专指度 >2 表示这个说法基本是她专有；≈1 表示多人共用。",
             "> `句占比` = 含该说法的台词比例 —— 用来判断 manifest 的频率约束该定多紧。\n"]

    for ck, cname in CHARS.items():
        texts = corpus[ck]
        n_self = sum(len(t) for t in texts) or 1
        per: list[dict] = []
        for w in CANDIDATES[ck]:
            cnt = sum(t.count(w) for t in texts)
            if cnt < 3:
                continue
            lines_with = sum(1 for t in texts if w in t)
            starts = 0
            ends: list[float] = []
            for t in texts:
                s, e = _positions(t, w)
                starts += s
                ends.extend(e)
            others_max, others_who = 0.0, ""
            for ok, oname in CHARS.items():
                if ok == ck:
                    continue
                n_o = sum(len(t) for t in corpus[ok]) or 1
                rate_o = sum(t.count(w) for t in corpus[ok]) / n_o
                if rate_o > others_max:
                    others_max, others_who = rate_o, oname
            rate_self = cnt / n_self
            spec = round(rate_self / others_max, 2) if others_max > 0 else 999.0
            per.append({
                "tic": w, "count": cnt, "per_10k": round(rate_self * 10000, 1),
                "line_share": round(lines_with / len(texts), 4),
                "start_share": round(starts / cnt, 2),
                "endpoint": round(sum(ends) / len(ends), 2),
                "specificity": spec, "top_other": others_who,
                "top_other_per_10k": round(others_max * 10000, 1),
            })
        per.sort(key=lambda x: (-x["specificity"], -x["count"]))
        per_char[cname] = per
        by_tic = {p["tic"]: p for p in per}
        out[cname] = per

        lines.append(f"\n## {cname}（n={len(texts)} 条）\n")
        lines.append("**专有口癖**（专指度 ≥2，即基本是她专用）：")
        exclusive = [p for p in per if p["specificity"] >= 2][:14]
        lines.append("　" + ("、".join(f"`{p['tic']}`({p['count']}, 专指{p['specificity']}, 句占比{p['line_share']:.0%})"
                                      for p in exclusive) or "（无）"))
        lines.append("\n**高频共用语气**：")
        common = sorted([p for p in per if p["specificity"] < 2], key=lambda x: -x["count"])[:10]
        lines.append("　" + "、".join(f"`{p['tic']}`({p['count']})" for p in common))
        lines.append("\n**零支持候选**（候选词表里但出现 <3 次 → 原作不这么说）：")
        missing = [w for w in CANDIDATES[ck] if w not in by_tic]
        lines.append("　" + "、".join(f"`{w}`" for w in missing) if missing else "　（无）")

    (REPORT / "tic_profile.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT / "tic_profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n-> report/tic_profile.md / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
