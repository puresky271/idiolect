"""口癖蒸馏：从原作台词提取五人的「口癖」（短习语 / 句末 / 起手 / 固定说法）。

与已有工具的分工：
  · `style_features.logodds_signature` 抓的是**实词/话题词**（野猫、抹茶、野良猫）
  · 本模块抓的是**口癖**——不承载话题、但一听就知道是谁的短说法
    （起手词、句末语气、固定短语、口头禅式判断）

四类：
  A 起手口癖：句首 1-3 字的高频开头（如「哈？」「诶——」「……嗯」）
  B 句末口癖：句尾的终助词/固定收尾（如「……吧」「哦——」「じゃん」）
  C 短习语：1~4 字的固定说法，按「该角色占比 / 他人占比」算特征性
  D 口癖短语：2~8 字、多次重复且他人少用的说法

产出 report/verbal_tics.json + verbal_tics.md
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
from _paths import CORPUS_DIR, DATA, REPORT, ROOT, require_corpus  # noqa: E402,F401

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = REPORT
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}

PUNCT = "。！？!?…·、，,～~—「」『』（）()「」 　"

# 人名与译名相关字符串：n-gram 会把它们切碎（orin / Soy / Tom / 小爽世…），必须排除。
# 这些是**称呼**而非口癖——称呼另由 nickname 机制管（见 REPORT_nickname_alignment.md）。
NAME_TOKENS = [
    "tomori", "anon", "rana", "soyo", "taki", "soyorin", "rikki", "tomorin",
    "灯", "爱音", "楽奈", "乐奈", "素世", "爽世", "立希", "睦", "祥子",
    "初华", "彩", "海铃", "羽泽", "户山", "宇田川", "仓田", "桐谷", "学姐", "同学",
]
_NAMECHARS = set("".join(NAME_TOKENS))


def _fragment(w: str) -> bool:
    """碎片/人名判定：整段属人名，或半截英文人名，或长度 1 的单字碎片。"""
    low = w.lower()
    if any(t.lower() in low for t in NAME_TOKENS):
        return True
    # 半截英文（如 orin / Soy / Tom）
    if re.fullmatch(r"[A-Za-z]{2,5}", w):
        for t in ("soyorin", "rikki", "tomorin"):
            if w.lower() in t.lower():
                return True
    # 纯单字：口癖极少是单字（除「哈」「嗯」这类，但它们通常与标点同现，会被 strip 掉）
    if len(w) == 1:
        return True
    return False


def load() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("split") == "train":
                out[r["character"]].append(r["text"])
    return out


def strip_punct(s: str) -> str:
    return s.strip().strip(PUNCT)


def ngrams(texts: list[str], lo: int, hi: int) -> Counter:
    """字符 n-gram（去标点后），只统计完整出现。"""
    c: Counter = Counter()
    for t in texts:
        s = "".join(ch for ch in t if ch not in PUNCT)
        for n in range(lo, hi + 1):
            for i in range(len(s) - n + 1):
                c[s[i:i + n]] += 1
    return c


def logodds(target: Counter, background: Counter, n_t: int, n_b: int, prior: float = 0.5) -> dict[str, float]:
    vocab = set(target)
    out = {}
    for w in vocab:
        a = target[w] + prior
        b = background.get(w, 0) + prior
        p_t = a / (n_t + prior * len(vocab))
        p_b = b / (n_b + prior * len(vocab))
        out[w] = math.log(p_t / p_b)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=4, help="短习语最少出现次数")
    ap.add_argument("--top", type=int, default=16)
    args = ap.parse_args()

    corpus = load()
    all_texts = [t for v in corpus.values() for t in v]
    out: dict = {}
    lines = ["# 五人口癖蒸馏（来自原作台词）\n",
             "> 口癖 = 不承载话题、但一听就知道是谁的短说法。",
             "> 与 `logodds_signature`（话题词）互补：这里抓的是**说法**，不是**内容**。\n"]

    for ck, cname in CHARS.items():
        texts = corpus[ck]
        others = [t for k2, v2 in corpus.items() if k2 != ck for t in v2]

        # A 起手（句首 1-3 字，按气泡切）
        opens: Counter = Counter()
        for t in texts:
            for bub in re.split(r"[\n]", t):
                s = strip_punct(bub)
                if len(s) >= 2:
                    for n in (1, 2, 3):
                        if len(s) >= n:
                            opens[s[:n]] += 1
        # 起手特征性：只保留该角色占比高的
        o_other: Counter = Counter()
        for t in others:
            for bub in re.split(r"[\n]", t):
                s = strip_punct(bub)
                if len(s) >= 2:
                    for n in (1, 2, 3):
                        if len(s) >= n:
                            o_other[s[:n]] += 1
        od = logodds(opens, o_other, sum(opens.values()), sum(o_other.values()))
        a_rows = [(w, opens[w], round(od[w], 2)) for w, n in opens.most_common(120)
                  if n >= args.min_count and od.get(w, 0) > 0.5 and not _fragment(w)]

        # B 句末（末 1-3 字）
        tails: Counter = Counter()
        for t in texts:
            for bub in re.split(r"[\n]", t):
                s = strip_punct(bub)
                if len(s) >= 2:
                    for n in (1, 2):
                        if len(s) >= n:
                            tails[s[-n:]] += 1
        t_other: Counter = Counter()
        for t in others:
            for bub in re.split(r"[\n]", t):
                s = strip_punct(bub)
                if len(s) >= 2:
                    for n in (1, 2):
                        if len(s) >= n:
                            t_other[s[-n:]] += 1
        td = logodds(tails, t_other, sum(tails.values()), sum(t_other.values()))
        b_rows = [(w, tails[w], round(td[w], 2)) for w, n in tails.most_common(120)
                  if n >= args.min_count and td.get(w, 0) > 0.5 and not _fragment(w)]

        # C/D 短习语与固定说法（2~8 字 n-gram，跨标点）
        tg = ngrams(texts, 2, 8)
        bg = ngrams(others, 2, 8)
        ld = logodds(tg, bg, sum(tg.values()), sum(bg.values()))
        cd = [(w, tg[w], round(ld[w], 2)) for w, n in tg.items()
              if n >= args.min_count and len(w) >= 2 and ld.get(w, 0) > 1.0 and not _fragment(w)]
        cd.sort(key=lambda x: (-x[2], -x[1]))
        # 去掉被更长同类包含的短片段（保留信息量更大的）
        pruned = []
        for w, n, lo in cd:
            if any(w != w2 and w in w2 and n <= n2 * 1.2 for w2, n2, _ in cd[:60]):
                continue
            pruned.append((w, n, lo))
        c_rows = pruned[:args.top]

        out[cname] = {"opening": a_rows[:12], "ending": b_rows[:12], "phrases": c_rows}
        lines.append(f"\n## {cname}（n={len(texts)}）\n")
        lines.append("**起手口癖**（出现次数 / 特征性 log-odds）：")
        lines.append("　" + "、".join(f"`{w}`({n}, {lo})" for w, n, lo in a_rows[:10]))
        lines.append("\n**句末口癖**：")
        lines.append("　" + "、".join(f"`{w}`({n}, {lo})" for w, n, lo in b_rows[:10]))
        lines.append("\n**固定说法 / 短习语**：")
        lines.append("　" + "、".join(f"`{w}`({n}, {lo})" for w, n, lo in c_rows))

    (REPORT / "verbal_tics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT / "verbal_tics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n-> report/verbal_tics.md / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
